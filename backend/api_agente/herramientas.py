"""
Herramientas que el LLM puede llamar. Toda la lógica y las validaciones viven aquí o en
los serializers del ERP; el modelo solo elige la herramienta y los argumentos.

Reglas de seguridad (plan §5.2):
- Los pacientes que se muestran son solo los que tienen el número del remitente.
- El paciente nunca lo elige el modelo: sale de la conversación.
- Crear un paciente o una cita exige un borrador y una confirmación explícita del
  paciente en su último mensaje (comprobado en código, no en el prompt).
"""

import re
from datetime import datetime, timedelta
from types import SimpleNamespace

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime, parse_time

from agenda.horarios import generar_huecos, intervalos_abiertos, motivo_cierre
from agenda.models import Atencion
from agenda.serializers import ESTADOS_QUE_OCUPAN, AtencionSerializer
from pacientes.models import Paciente
from pacientes.serializers import PacienteSerializer
from sedes.models import Sede
from servicios.models import TipoTrabajo
from users.models import Doctor

from .cifrado import descifrar
from .models import ConversacionWhatsApp, MensajeWhatsApp, TokenServicio
from .seguridad import es_afirmativo

DURACION_CITA_MINUTOS = 20
EDAD_ADULTO = 18
FORMATOS_NACIMIENTO = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y")


EXPIRA_BORRADOR = timedelta(minutes=10)


class ErrorHerramienta(Exception):
    """Error que se devuelve al modelo para que se lo explique al paciente."""


def _digitos(telefono: str) -> str:
    return "".join(c for c in telefono if c.isdigit())


def _formato_telefono_erp(telefono: str) -> str:
    """Forma en la que el ERP guarda un teléfono: '+504 9999-9999'."""
    d = _digitos(telefono)[-8:]
    return f"+504 {d[:4]}-{d[4:]}"


def calcular_edad(fecha_nacimiento, hoy=None) -> int:
    hoy = hoy or timezone.localdate()
    return hoy.year - fecha_nacimiento.year - (
        (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
    )


def _fecha_nacimiento(texto):
    """Acepta AAAA-MM-DD y las formas habituales en Honduras (DD/MM/AAAA)."""
    texto = str(texto or "").strip()
    for formato in FORMATOS_NACIMIENTO:
        try:
            fecha = datetime.strptime(texto, formato).date()
        except ValueError:
            continue
        if fecha > timezone.localdate() or fecha.year < 1900 or calcular_edad(fecha) > 120:
            raise ErrorHerramienta("La fecha de nacimiento no es válida.")
        return fecha
    raise ErrorHerramienta("La fecha de nacimiento debe tener formato AAAA-MM-DD.")


def _identidad(texto) -> str:
    """Devuelve el DNI solo con dígitos. Vacío si no se dio."""
    digitos = _digitos(str(texto or ""))
    if not digitos:
        return ""
    if len(digitos) != 13:
        raise ErrorHerramienta("El DNI debe tener 13 dígitos.")
    return digitos


MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def _fecha_mencionada(textos, fecha) -> bool:
    """True si el paciente escribió esa fecha. Evita que el modelo invente datos."""
    dia, mes, anio = fecha.day, fecha.month, fecha.year
    variantes = {
        fecha.isoformat(),
        f"{dia:02d}/{mes:02d}/{anio}", f"{dia}/{mes}/{anio}",
        f"{dia:02d}-{mes:02d}-{anio}", f"{dia}-{mes}-{anio}",
        f"{anio}-{mes:02d}-{dia:02d}",
    }
    nombres_mes = [n for n, numero in MESES_ES.items() if numero == mes]
    for texto in textos:
        if any(variante in texto for variante in variantes):
            return True
        bajo = texto.lower()
        if (
            str(anio) in texto
            and any(nombre in bajo for nombre in nombres_mes)
            and re.search(rf"(?<!\d)0?{dia}(?!\d)", texto)
        ):
            return True
    return False


def _identidad_mencionada(textos, identidad) -> bool:
    return any(identidad in _digitos(texto) for texto in textos)


class Herramientas:
    def __init__(self, conversacion: ConversacionWhatsApp):
        self.conversacion = conversacion
        # El agente no es un usuario del panel: opera sobre todas las sedes activas.
        self.usuario = TokenServicio(nombre="agente-whatsapp")
        self.request = SimpleNamespace(user=self.usuario)

    # ---- utilidades -------------------------------------------------------

    @staticmethod
    def _entero(valor):
        try:
            return int(valor)
        except (TypeError, ValueError):
            return None

    def _sede(self, sede_id) -> Sede:
        sede_id = self._entero(sede_id)
        sede = Sede.objects.filter(pk=sede_id, activa=True).first() if sede_id else None
        if sede is None:
            raise ErrorHerramienta("La sede no existe. Consulta listar_sedes.")
        return sede

    @staticmethod
    def _fecha(texto):
        fecha = parse_date(texto or "")
        if fecha is None:
            raise ErrorHerramienta("La fecha debe tener formato AAAA-MM-DD.")
        if fecha < timezone.localdate():
            raise ErrorHerramienta("No se puede agendar en una fecha pasada.")
        return fecha

    def _textos_paciente(self) -> list[str]:
        return [
            descifrar(mensaje.contenido_cifrado)
            for mensaje in MensajeWhatsApp.objects.filter(
                conversacion=self.conversacion, rol=MensajeWhatsApp.Rol.PACIENTE
            ).order_by("creado")
        ]

    def _pacientes_del_remitente(self):
        return Paciente.objects.filter(
            telefono=_formato_telefono_erp(self.conversacion.telefono), activo=True
        )

    def _ultimo_mensaje_paciente(self):
        """Último mensaje del paciente (objeto), o None. Se usa para validar la confirmación."""
        return (
            MensajeWhatsApp.objects.filter(
                conversacion=self.conversacion, rol=MensajeWhatsApp.Rol.PACIENTE
            )
            .order_by("-creado")
            .first()
        )

    def _guardar_parcial(self, datos: dict):
        """Guarda datos de alta sin pasar a espera de confirmación (faltan campos)."""
        self.conversacion.borrador = {"tipo": "paciente_incompleto", "datos": datos}
        self.conversacion.save(update_fields=["borrador", "ultima_actividad"])

    def _datos_paciente_parciales(self) -> dict:
        borrador = self.conversacion.borrador or {}
        if borrador.get("tipo") not in ("paciente_incompleto", "paciente"):
            return {}
        datos = dict(borrador.get("datos") or {})
        # Un borrador ya validado guarda "sede_origen"; al volver a prepararlo se usa como sede.
        if datos.get("sede_id") is None and datos.get("sede_origen"):
            datos["sede_id"] = datos["sede_origen"]
        return datos

    def _guardar_borrador(self, tipo: str, datos: dict, resumen: str):
        self.conversacion.borrador = {
            "tipo": tipo,
            "datos": datos,
            "resumen": resumen,
            "creado": timezone.now().isoformat(),
        }
        self.conversacion.estado = ConversacionWhatsApp.Estado.ESPERANDO_CONFIRMACION
        self.conversacion.save(update_fields=["borrador", "estado", "ultima_actividad"])

    def _limpiar_borrador(self):
        self.conversacion.borrador = {}
        self.conversacion.estado = ConversacionWhatsApp.Estado.INICIO
        # Incluye "paciente": al confirmar un alta, la conversación queda vinculada a él.
        self.conversacion.save(
            update_fields=["borrador", "estado", "paciente", "ultima_actividad"]
        )

    @staticmethod
    def _errores(serializer) -> str:
        partes = []
        for campo, mensajes in serializer.errors.items():
            texto = " ".join(str(m) for m in mensajes)
            partes.append(texto if campo == "non_field_errors" else f"{campo}: {texto}")
        return "; ".join(partes)

    # ---- consultas --------------------------------------------------------

    def listar_sedes(self, args):
        return [
            {"id": s.pk, "nombre": s.nombre, "direccion": s.direccion, "telefono": s.telefono}
            for s in Sede.objects.filter(activa=True).order_by("nombre")
        ]

    def consultar_disponibilidad(self, args):
        sede = self._sede(args.get("sede_id"))
        fecha = self._fecha(args.get("fecha"))
        abiertos = intervalos_abiertos(sede, fecha)
        if abiertos is not None and not abiertos:
            return {"sede": sede.nombre, "fecha": fecha.isoformat(), "abierta": False,
                    "motivo": motivo_cierre(sede, fecha)}
        doctores = []
        for doctor in Doctor.objects.filter(activo=True, sedes=sede).order_by("nombres"):
            ocupadas = list(
                Atencion.objects.filter(
                    doctor=doctor, fecha=fecha, estado__in=ESTADOS_QUE_OCUPAN
                ).order_by("hora_inicio")
            )
            huecos = (
                generar_huecos(abiertos, ocupadas, fecha, DURACION_CITA_MINUTOS)
                if abiertos is not None
                else []
            )
            doctores.append({
                "doctor_id": doctor.pk,
                "doctor": f"{doctor.nombres} {doctor.apellidos}",
                "horas_libres": huecos,
            })
        return {
            "sede": sede.nombre,
            "fecha": fecha.isoformat(),
            "duracion_minutos": DURACION_CITA_MINUTOS,
            "doctores": doctores,
        }

    def consultar_mis_pacientes(self, args):
        return [
            {"id": p.pk, "nombre": f"{p.nombres} {p.apellidos}", "sede_origen": p.sede_origen.nombre if p.sede_origen else None}
            for p in self._pacientes_del_remitente()
        ]

    def listar_mis_citas(self, args):
        paciente = self.conversacion.paciente
        if paciente is None:
            raise ErrorHerramienta("Primero hay que identificar al paciente (seleccionar_paciente).")
        citas = Atencion.objects.filter(
            paciente=paciente, fecha__gte=timezone.localdate(), estado__in=ESTADOS_QUE_OCUPAN
        ).select_related("sede", "doctor").order_by("fecha", "hora_inicio")
        return [
            {"id": c.pk, "fecha": c.fecha.isoformat(), "hora": c.hora_inicio.strftime("%H:%M"),
             "sede": c.sede.nombre, "doctor": f"{c.doctor.nombres} {c.doctor.apellidos}",
             "estado": c.estado}
            for c in citas
        ]

    # ---- selección y borradores ------------------------------------------

    def seleccionar_paciente(self, args):
        paciente_id = self._entero(args.get("paciente_id"))
        paciente = (
            self._pacientes_del_remitente().filter(pk=paciente_id).first()
            if paciente_id else None
        )
        if paciente is None:
            raise ErrorHerramienta("Ese paciente no está registrado con este número.")
        self.conversacion.paciente = paciente
        self.conversacion.save(update_fields=["paciente", "ultima_actividad"])
        return {"paciente_seleccionado": f"{paciente.nombres} {paciente.apellidos}"}

    def preparar_paciente(self, args):
        if self._pacientes_del_remitente().exists():
            raise ErrorHerramienta(
                "Ya hay pacientes registrados con este número. Pregunta cuál es el "
                "paciente (consultar_mis_pacientes) o pide que contacten a recepción."
            )

        # Los datos pueden llegar en varios mensajes: se mezcla lo nuevo con lo ya guardado.
        datos = self._datos_paciente_parciales()
        datos.update({k: v for k, v in (args or {}).items() if v not in (None, "")})

        sede = self._sede(datos["sede_id"]) if datos.get("sede_id") else None
        nacimiento = (
            _fecha_nacimiento(datos["fecha_nacimiento"]) if datos.get("fecha_nacimiento") else None
        )
        identidad = _identidad(datos.get("identidad"))
        edad = calcular_edad(nacimiento) if nacimiento else None

        # El modelo no puede rellenar datos que el paciente no dio: se descartan y se piden.
        textos = self._textos_paciente()
        if nacimiento and not _fecha_mencionada(textos, nacimiento):
            nacimiento = None
            datos.pop("fecha_nacimiento", None)
        if identidad and not _identidad_mencionada(textos, identidad):
            identidad = ""
            datos.pop("identidad", None)
        edad = calcular_edad(nacimiento) if nacimiento else None

        faltan = []
        if not str(datos.get("nombres") or "").strip():
            faltan.append("nombres")
        if not str(datos.get("apellidos") or "").strip():
            faltan.append("apellidos")
        if sede is None:
            faltan.append("sede")
        if nacimiento is None:
            faltan.append("fecha_nacimiento")
        elif edad >= EDAD_ADULTO and not identidad:
            faltan.append("identidad")

        if faltan:
            self._guardar_parcial(datos)
            return {
                "faltan": faltan,
                "edad": edad,
                "datos_recibidos": {
                    "nombres": datos.get("nombres") or "",
                    "apellidos": datos.get("apellidos") or "",
                    "sede": sede.nombre if sede else "",
                    "fecha_nacimiento": nacimiento.isoformat() if nacimiento else "",
                    "identidad": identidad,
                },
            }

        direccion = str(datos.get("direccion") or "").strip() or sede.direccion
        limpio = {
            "nombres": str(datos["nombres"]).strip(),
            "apellidos": str(datos["apellidos"]).strip(),
            "sede_origen": sede.pk,
            "telefono": self.conversacion.telefono,
            "direccion": direccion,
            "identidad": identidad,
            "fecha_nacimiento": nacimiento.isoformat(),
            "sexo": datos.get("sexo") or "",
            "email": str(datos.get("email") or "").strip(),
        }
        serializer = PacienteSerializer(data=limpio, context={"request": self.request})
        if not serializer.is_valid():
            raise ErrorHerramienta(self._errores(serializer))

        dni = f", DNI {identidad}" if identidad else ""
        resumen = (
            f"Registrar a {limpio['nombres']} {limpio['apellidos']}, {edad} años{dni}, "
            f"en {sede.nombre}, dirección: {direccion}"
        )
        self._guardar_borrador("paciente", limpio, resumen)
        return {"pendiente_confirmacion": resumen, "edad": edad}

    def preparar_cita(self, args):
        paciente = self.conversacion.paciente
        if paciente is None:
            raise ErrorHerramienta("Primero hay que identificar al paciente (seleccionar_paciente).")
        sede = self._sede(args.get("sede_id"))
        doctor = Doctor.objects.filter(
            pk=self._entero(args.get("doctor_id")), activo=True, sedes=sede
        ).first()
        if doctor is None:
            raise ErrorHerramienta("Ese doctor no atiende en esa sede. Consulta consultar_disponibilidad.")
        tipo = TipoTrabajo.objects.filter(
            pk=self._entero(args.get("tipo_trabajo_id")), activo=True
        ).first()
        if tipo is None:
            raise ErrorHerramienta("Ese tipo de trabajo no existe.")
        fecha = self._fecha(args.get("fecha"))
        inicio = parse_time(args.get("hora_inicio") or "")
        if inicio is None:
            raise ErrorHerramienta("La hora debe tener formato HH:MM.")
        fin = (datetime.combine(fecha, inicio) + timedelta(minutes=DURACION_CITA_MINUTOS)).time()

        datos = {
            "sede": sede.pk,
            "doctor": doctor.pk,
            "paciente": paciente.pk,
            "tipo_trabajo": tipo.pk,
            "fecha": fecha.isoformat(),
            "hora_inicio": inicio.strftime("%H:%M"),
            "hora_fin": fin.strftime("%H:%M"),
            "honorario_doctor": "0",
        }
        serializer = AtencionSerializer(
            data=datos, context={"request": self.request, "origen": Atencion.Origen.AGENTE_WHATSAPP}
        )
        if not serializer.is_valid():
            raise ErrorHerramienta(self._errores(serializer))
        resumen = (
            f"Cita para {paciente.nombres} {paciente.apellidos}: {fecha.isoformat()} a las "
            f"{inicio.strftime('%H:%M')} en {sede.nombre} con {doctor.nombres} {doctor.apellidos} "
            f"({tipo.nombre})"
        )
        self._guardar_borrador("cita", datos, resumen)
        return {"pendiente_confirmacion": resumen}

    def confirmar_accion(self, args):
        conv = self.conversacion
        if conv.estado != ConversacionWhatsApp.Estado.ESPERANDO_CONFIRMACION or not conv.borrador:
            raise ErrorHerramienta("No hay ninguna acción pendiente de confirmar.")

        borrador = conv.borrador

        # 1. El borrador no debe estar vencido.
        creado = parse_datetime(borrador.get("creado") or "")
        if creado is None or timezone.now() - creado > EXPIRA_BORRADOR:
            self._limpiar_borrador()
            raise ErrorHerramienta("La solicitud expiró. Hay que prepararla de nuevo.")

        # 2. La confirmación debe ser un mensaje POSTERIOR al borrador y una afirmación limpia.
        ultimo = self._ultimo_mensaje_paciente()
        if (
            ultimo is None
            or ultimo.creado <= creado
            or not es_afirmativo(descifrar(ultimo.contenido_cifrado))
        ):
            raise ErrorHerramienta(
                "El paciente todavía no ha confirmado. Muestra el resumen y pregunta si es correcto."
            )

        datos = borrador["datos"]
        tipo = borrador.get("tipo")

        # 3. Se revalida y se guarda todo junto: o se crea, o no se crea nada.
        with transaction.atomic():
            if tipo == "paciente":
                serializer = PacienteSerializer(data=datos, context={"request": self.request})
                if not serializer.is_valid():
                    raise ErrorHerramienta(self._errores(serializer))
                paciente = serializer.save()
                conv.paciente = paciente
                resultado = {"paciente_creado": f"{paciente.nombres} {paciente.apellidos}"}
            elif tipo == "cita":
                serializer = AtencionSerializer(
                    data=datos,
                    context={"request": self.request, "origen": Atencion.Origen.AGENTE_WHATSAPP},
                )
                if not serializer.is_valid():
                    raise ErrorHerramienta(self._errores(serializer))
                cita = serializer.save()
                # Sin el id de la cita: el modelo no debe verlo ni repetirlo.
                resultado = {
                    "cita_creada": True,
                    "fecha": cita.fecha.isoformat(),
                    "hora": cita.hora_inicio.strftime("%H:%M"),
                }
            else:
                raise ErrorHerramienta("Acción pendiente desconocida.")

        self._limpiar_borrador()
        return {"confirmado": True, **resultado}

    def cancelar_accion(self, args):
        if not self.conversacion.borrador:
            return {"cancelado": False, "motivo": "No había nada pendiente."}
        self._limpiar_borrador()
        return {"cancelado": True}

    # ---- despacho ---------------------------------------------------------

    def ejecutar(self, nombre: str, argumentos: dict) -> dict:
        metodo = getattr(self, nombre, None) if nombre in NOMBRES_HERRAMIENTAS else None
        if metodo is None:
            return {"error": f"Herramienta desconocida: {nombre}"}
        try:
            return {"resultado": metodo(argumentos or {})}
        except ErrorHerramienta as error:
            return {"error": str(error)}


NOMBRES_HERRAMIENTAS = {
    "listar_sedes", "consultar_disponibilidad", "consultar_mis_pacientes",
    "listar_mis_citas", "seleccionar_paciente", "preparar_paciente",
    "preparar_cita", "confirmar_accion", "cancelar_accion",
}


def _herramienta(nombre, descripcion, propiedades=None, requeridas=None):
    return {
        "type": "function",
        "function": {
            "name": nombre,
            "description": descripcion,
            "parameters": {
                "type": "object",
                "properties": propiedades or {},
                "required": requeridas or [],
            },
        },
    }


ENTERO = {"type": "integer"}
TEXTO = {"type": "string"}

DEFINICIONES = [
    _herramienta("listar_sedes", "Lista las sedes de la clínica con su id, nombre y dirección."),
    _herramienta(
        "consultar_disponibilidad",
        "Horas libres de los doctores de una sede en una fecha. Úsala antes de proponer horarios.",
        {"sede_id": ENTERO, "fecha": {**TEXTO, "description": "AAAA-MM-DD"}},
        ["sede_id", "fecha"],
    ),
    _herramienta("consultar_mis_pacientes", "Pacientes registrados con el número de WhatsApp de esta conversación."),
    _herramienta("listar_mis_citas", "Citas próximas del paciente seleccionado."),
    _herramienta(
        "seleccionar_paciente",
        "Elige cuál de los pacientes del número es el que va a agendar.",
        {"paciente_id": ENTERO},
        ["paciente_id"],
    ),
    _herramienta(
        "preparar_paciente",
        "Prepara el alta de un paciente nuevo para confirmación. Se puede llamar varias veces con "
        "datos parciales: la respuesta dice en 'faltan' qué pedir. Requiere nombres, apellidos, sede, "
        "fecha de nacimiento y, para mayores de 18 años, el DNI. La dirección es opcional: si falta "
        "se usa la de la sede.",
        {
            "nombres": TEXTO, "apellidos": TEXTO, "sede_id": ENTERO, "direccion": TEXTO,
            "identidad": {**TEXTO, "description": "DNI de 13 dígitos; obligatorio para mayores de 18"},
            "fecha_nacimiento": {**TEXTO, "description": "AAAA-MM-DD"},
            "sexo": {"type": "string", "enum": ["F", "M", "O"]},
            "email": TEXTO,
        },
        ["nombres", "apellidos", "sede_id"],
    ),
    _herramienta(
        "preparar_cita",
        "Prepara una cita para el paciente seleccionado, para confirmación. Duración fija de 20 minutos.",
        {
            "sede_id": ENTERO, "doctor_id": ENTERO, "tipo_trabajo_id": ENTERO,
            "fecha": {**TEXTO, "description": "AAAA-MM-DD"},
            "hora_inicio": {**TEXTO, "description": "HH:MM"},
        },
        ["sede_id", "doctor_id", "tipo_trabajo_id", "fecha", "hora_inicio"],
    ),
    _herramienta(
        "confirmar_accion",
        "Guarda la cita o el paciente preparados. Solo llámala cuando el paciente haya confirmado el resumen.",
    ),
    _herramienta("cancelar_accion", "Descarta la acción pendiente si el paciente no la quiere."),
]
