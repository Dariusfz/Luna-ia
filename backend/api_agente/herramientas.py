"""
Herramientas que el LLM puede llamar. Toda la lógica y las validaciones viven aquí o en
los serializers del ERP; el modelo solo elige la herramienta y los argumentos.

Reglas de seguridad (plan §5.2):
- Los pacientes que se muestran son solo los que tienen el número del remitente.
- El paciente nunca lo elige el modelo: sale de la conversación.
- Crear un paciente o una cita exige un borrador y una confirmación explícita del
  paciente en su último mensaje (comprobado en código, no en el prompt).
"""

import difflib
import logging
import re
import unicodedata
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

from . import notificaciones
from .cifrado import descifrar
from .models import ConversacionWhatsApp, MensajeWhatsApp, TokenServicio
from .seguridad import es_afirmativo

logger = logging.getLogger(__name__)

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
    """Devuelve el DNI solo con dígitos. Vacío si no se dio.

    Honduras usa 13 dígitos con formato DDMM-AAAA-NNNNN (departamento, municipio,
    año y secuencia). Se rechazan patrones obvios de prueba como 0000-0000-00003.
    El año del DNI no se compara con la fecha de nacimiento: puede corresponder al
    trámite (por ejemplo, un cambio de nombre hecho años después de nacer).
    """
    digitos = _digitos(str(texto or ""))
    if not digitos:
        return ""
    if len(digitos) != 13:
        raise ErrorHerramienta("El DNI debe tener 13 dígitos.")
    if len(set(digitos)) == 1 or not (1 <= int(digitos[:2]) <= 18):
        raise ErrorHerramienta("El número de identidad no es válido.")
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


def _sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def _tratamiento_mencionado(textos, nombre: str) -> bool:
    """True si el paciente nombró alguna palabra significativa del tratamiento, tolerando
    errores de escritura ('estraccion' para 'Extraccion'). Evita elegir uno que no pidió."""
    palabras = [p for p in re.findall(r"[a-zñ]+", _sin_acentos(nombre)) if len(p) >= 5]
    if not palabras:
        return True
    dichas = re.findall(r"[a-zñ]+", _sin_acentos(" ".join(textos)))
    for palabra in palabras:
        for dicha in dichas:
            if len(dicha) < 4:
                continue
            if palabra.startswith(dicha) or difflib.SequenceMatcher(None, palabra, dicha).ratio() >= 0.8:
                return True
    return False


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

    def _paciente_de_la_conversacion(self) -> Paciente:
        """Paciente del hilo. Si no está elegido y el número solo tiene uno, lo toma solo.

        Evita que el agente se quede sin responder cuando el paciente pregunta por
        su cita y el hilo no tenía un paciente seleccionado explícitamente.
        """
        if self.conversacion.paciente_id:
            return self.conversacion.paciente
        pacientes = list(self._pacientes_del_remitente()[:2])
        if len(pacientes) == 1:
            self.conversacion.paciente = pacientes[0]
            self.conversacion.save(update_fields=["paciente", "ultima_actividad"])
            return pacientes[0]
        if not pacientes:
            raise ErrorHerramienta(
                "No hay pacientes registrados con este número. Pregunta si desea registrar uno nuevo "
                "(preparar_paciente)."
            )
        raise ErrorHerramienta(
            "Hay varios pacientes registrados con este número. Pregunta para cuál es la consulta y usa "
            "consultar_mis_pacientes y seleccionar_paciente."
        )

    def _citas_activas_del_paciente(self):
        """Citas futuras y activas del paciente de esta conversación (nunca de otro)."""
        paciente = self._paciente_de_la_conversacion()
        return Atencion.objects.filter(
            paciente=paciente,
            fecha__gte=timezone.localdate(),
            estado__in=ESTADOS_QUE_OCUPAN,
        ).select_related("sede", "doctor", "tipo_trabajo")

    def _cita_del_paciente(self, cita_id) -> Atencion:
        cita_id = self._entero(cita_id)
        cita = (
            self._citas_activas_del_paciente().filter(pk=cita_id).first()
            if cita_id else None
        )
        if cita is None:
            raise ErrorHerramienta(
                "Esa cita no existe, ya pasó o no pertenece al paciente. Consulta listar_mis_citas."
            )
        return cita

    def _ultimo_mensaje_paciente(self):
        """Último mensaje del paciente (objeto), o None. Se usa para validar la confirmación."""
        return (
            MensajeWhatsApp.objects.filter(
                conversacion=self.conversacion, rol=MensajeWhatsApp.Rol.PACIENTE
            )
            .order_by("-creado", "-pk")
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
        ultimo = self._ultimo_mensaje_paciente()
        self.conversacion.borrador = {
            "tipo": tipo,
            "datos": datos,
            "resumen": resumen,
            "creado": timezone.now().isoformat(),
            # Id del último mensaje al preparar: la confirmación debe ser uno posterior.
            # El id es más fiable que la hora (relojes con poca resolución).
            "ultimo_mensaje_id": ultimo.pk if ultimo else None,
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

    def consultar_tratamientos(self, args):
        """Catálogo activo con precio de referencia. Si no hay coincidencia, el modelo debe
        decir que consultará con el administrador (solicitar_revision_administrador)."""
        texto = str(args.get("texto") or "").strip()
        tratamientos = TipoTrabajo.objects.filter(activo=True).order_by("nombre")
        if texto:
            # Sin depender de tildes ni de la ortografía exacta ("extracción" -> "Extraccion").
            tratamientos = [t for t in tratamientos if _tratamiento_mencionado([texto], t.nombre)]
        return [
            {
                "tratamiento": t.nombre,
                "precio_referencia_hnl": f"{t.precio:,.2f}",
                "descripcion": t.descripcion,
            }
            for t in list(tratamientos)[:50]
        ]

    def solicitar_revision_administrador(self, args):
        """Avisa al administrador que el paciente pide un tratamiento que no está en el catálogo."""
        motivo = str(args.get("motivo") or "").strip()[:300]
        logger.warning(
            "Revisión de precios pendiente (conversación %s): %s", self.conversacion.pk, motivo
        )
        notificaciones.notificar_tratamiento_no_disponible(self.conversacion, motivo)
        return {"registrado": True}

    def consultar_mis_pacientes(self, args):
        return [
            {"id": p.pk, "nombre": f"{p.nombres} {p.apellidos}", "sede_origen": p.sede_origen.nombre if p.sede_origen else None}
            for p in self._pacientes_del_remitente()
        ]

    def listar_mis_citas(self, args):
        citas = self._citas_activas_del_paciente().order_by("fecha", "hora_inicio")
        return [
            {"id": c.pk, "fecha": c.fecha.isoformat(), "hora": c.hora_inicio.strftime("%H:%M"),
             "sede": c.sede.nombre, "doctor": f"{c.doctor.nombres} {c.doctor.apellidos}",
             "tratamiento": c.tipo_trabajo.nombre, "estado": c.estado}
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
        # Un mismo número puede tener varios pacientes (familiares). No se bloquea
        # el alta por el hecho de que ya exista otro paciente con ese teléfono.

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
        if identidad:
            if Paciente.objects.filter(identidad=identidad).exists():
                raise ErrorHerramienta(
                    "Ese DNI ya está registrado. Si es el mismo paciente, usa "
                    "consultar_mis_pacientes y seleccionar_paciente; si no, verifica el "
                    "número de identidad."
                )
        elif self._pacientes_del_remitente().filter(
            nombres__iexact=limpio["nombres"],
            apellidos__iexact=limpio["apellidos"],
            fecha_nacimiento=nacimiento,
        ).exists():
            raise ErrorHerramienta(
                "Ya existe un paciente con ese nombre y fecha de nacimiento en este número. "
                "Usa consultar_mis_pacientes y seleccionar_paciente."
            )

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

    @staticmethod
    def _tratamiento_nombrado(textos):
        """Tratamiento activo que el paciente nombró en esos mensajes; el más reciente primero."""
        catalogo = list(TipoTrabajo.objects.filter(activo=True))
        for texto in reversed(textos):
            for tipo in catalogo:
                if _tratamiento_mencionado([texto], tipo.nombre):
                    return tipo
        return None

    def _doctor_libre(self, sede, fecha, inicio, fin, excluir_cita_id=None):
        """Primer doctor activo de la sede sin otra cita que se cruce con ese horario."""
        for doctor in Doctor.objects.filter(activo=True, sedes=sede).order_by("nombres", "apellidos"):
            cruce = Atencion.objects.filter(
                doctor=doctor, fecha=fecha, estado__in=ESTADOS_QUE_OCUPAN,
                hora_inicio__lt=fin, hora_fin__gt=inicio,
            )
            if excluir_cita_id is not None:
                cruce = cruce.exclude(pk=excluir_cita_id)
            if not cruce.exists():
                return doctor
        return None

    def preparar_cita(self, args):
        borrador = self.conversacion.borrador or {}
        if (
            self.conversacion.estado == ConversacionWhatsApp.Estado.ESPERANDO_CONFIRMACION
            and borrador.get("tipo") == "paciente"
        ):
            raise ErrorHerramienta(
                "Hay un alta de paciente pendiente de confirmar. Primero confirma el alta y "
                "después prepara la cita."
            )
        paciente = self._paciente_de_la_conversacion()
        sede = self._sede(args.get("sede_id"))
        # El tratamiento puede haberse dicho al inicio del flujo (p. ej. "Extraccion")
        # y luego el paciente solo eligió sede, día y hora. Se valida contra toda la
        # conversación para no perder ese dato; el más reciente tiene prioridad.
        textos = self._textos_paciente()
        recientes = textos[-3:]
        tipo = TipoTrabajo.objects.filter(
            pk=self._entero(args.get("tipo_trabajo_id")), activo=True
        ).first()
        if tipo is None or not _tratamiento_mencionado(textos, tipo.nombre):
            # El modelo suele equivocar el id. Se usa el tratamiento que el paciente nombró.
            tipo = self._tratamiento_nombrado(recientes) or self._tratamiento_nombrado(textos)
        if tipo is None:
            raise ErrorHerramienta(
                "El paciente no ha nombrado un tratamiento del catálogo. Pregúntale qué tratamiento "
                "quiere (consultar_tratamientos); si no está disponible, llama "
                "solicitar_revision_administrador."
            )
        fecha = self._fecha(args.get("fecha"))
        inicio = parse_time(args.get("hora_inicio") or "")
        if inicio is None:
            raise ErrorHerramienta("La hora debe tener formato HH:MM.")
        fin = (datetime.combine(fecha, inicio) + timedelta(minutes=DURACION_CITA_MINUTOS)).time()

        # Sin doctor concreto (el paciente dijo "cualquiera"): se elige uno libre en esa hora.
        doctor_id = self._entero(args.get("doctor_id"))
        if doctor_id is None:
            doctor = self._doctor_libre(sede, fecha, inicio, fin)
            if doctor is None:
                raise ErrorHerramienta(
                    "No hay doctores libres en esa sede a esa hora. Consulta consultar_disponibilidad."
                )
        else:
            doctor = Doctor.objects.filter(pk=doctor_id, activo=True, sedes=sede).first()
            if doctor is None:
                raise ErrorHerramienta("Ese doctor no atiende en esa sede. Consulta consultar_disponibilidad.")

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
            f"({tipo.nombre}, precio de referencia L {tipo.precio:,.2f})"
        )
        self._guardar_borrador("cita", datos, resumen)
        return {"pendiente_confirmacion": resumen}

    def preparar_cancelacion_cita(self, args):
        cita = self._cita_del_paciente(args.get("cita_id"))
        resumen = (
            f"Cancelar la cita de {cita.tipo_trabajo.nombre} del {cita.fecha.isoformat()} "
            f"a las {cita.hora_inicio.strftime('%H:%M')} en {cita.sede.nombre} "
            f"con {cita.doctor.nombres} {cita.doctor.apellidos}"
        )
        self._guardar_borrador("cancelar_cita", {"cita_id": cita.pk}, resumen)
        return {"pendiente_confirmacion": resumen}

    def preparar_modificacion_cita(self, args):
        cita = self._cita_del_paciente(args.get("cita_id"))

        sede = self._sede(args.get("sede_id")) if args.get("sede_id") else cita.sede
        fecha = self._fecha(args["fecha"]) if args.get("fecha") else cita.fecha
        if args.get("hora_inicio"):
            inicio = parse_time(args["hora_inicio"])
            if inicio is None:
                raise ErrorHerramienta("La hora debe tener formato HH:MM.")
        else:
            inicio = cita.hora_inicio
        fin = (datetime.combine(fecha, inicio) + timedelta(minutes=DURACION_CITA_MINUTOS)).time()

        cambios = {}
        if sede.pk != cita.sede_id:
            cambios["sede"] = sede.pk
        if fecha != cita.fecha:
            cambios["fecha"] = fecha.isoformat()
        if inicio != cita.hora_inicio:
            cambios["hora_inicio"] = inicio.strftime("%H:%M")
            cambios["hora_fin"] = fin.strftime("%H:%M")

        doctor_id = self._entero(args.get("doctor_id"))
        if doctor_id is not None:
            doctor = Doctor.objects.filter(pk=doctor_id, activo=True, sedes=sede).first()
            if doctor is None:
                raise ErrorHerramienta(
                    "Ese doctor no atiende en esa sede. Consulta consultar_disponibilidad."
                )
        elif "sede" in cambios:
            # Cambia de sede sin decir doctor: se conserva el actual si atiende ahí,
            # o se asigna uno libre en el nuevo horario.
            doctor = self._doctor_libre(
                sede, fecha, inicio, fin, excluir_cita_id=cita.pk
            )
            if doctor is None:
                raise ErrorHerramienta(
                    "No hay doctores libres en esa sede a esa hora. Consulta consultar_disponibilidad."
                )
        else:
            doctor = cita.doctor
        if doctor.pk != cita.doctor_id:
            cambios["doctor"] = doctor.pk

        tipo_id = self._entero(args.get("tipo_trabajo_id"))
        if tipo_id is not None and tipo_id != cita.tipo_trabajo_id:
            textos = self._textos_paciente()
            recientes = textos[-3:]
            tipo = TipoTrabajo.objects.filter(pk=tipo_id, activo=True).first()
            if tipo is None or not _tratamiento_mencionado(textos, tipo.nombre):
                # El modelo suele equivocar el id: se usa el tratamiento que el paciente nombró.
                tipo = self._tratamiento_nombrado(recientes) or self._tratamiento_nombrado(textos)
            if tipo is None:
                raise ErrorHerramienta(
                    "El paciente no nombró un tratamiento del catálogo. Pregúntale qué tratamiento "
                    "quiere (consultar_tratamientos); si no está disponible, llama "
                    "solicitar_revision_administrador."
                )
            if tipo.pk != cita.tipo_trabajo_id:
                cambios["tipo_trabajo"] = tipo.pk

        if not cambios:
            raise ErrorHerramienta(
                "No se indicó ningún cambio. Pregunta al paciente qué desea cambiar: fecha, hora, "
                "sede, doctor o tratamiento."
            )

        serializer = AtencionSerializer(
            instance=cita, data=cambios, partial=True, context={"request": self.request}
        )
        if not serializer.is_valid():
            raise ErrorHerramienta(self._errores(serializer))

        partes = []
        if "fecha" in cambios:
            partes.append(f"fecha {fecha.strftime('%d/%m/%Y')}")
        if "hora_inicio" in cambios:
            partes.append(f"hora {inicio.strftime('%H:%M')}")
        if "sede" in cambios:
            partes.append(f"sede {sede.nombre}")
        if "doctor" in cambios:
            partes.append(f"doctor {doctor.nombres} {doctor.apellidos}")
        if "tipo_trabajo" in cambios:
            partes.append(f"tratamiento {tipo.nombre}")
        resumen = (
            f"Cambiar la cita del {cita.fecha.isoformat()} a las "
            f"{cita.hora_inicio.strftime('%H:%M')}: " + ", ".join(partes)
        )
        self._guardar_borrador(
            "modificar_cita", {"cita_id": cita.pk, "cambios": cambios}, resumen
        )
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
        if ultimo is None or not es_afirmativo(descifrar(ultimo.contenido_cifrado)):
            raise ErrorHerramienta(
                "El último mensaje del paciente no es una confirmación clara (sí o no). "
                "No lo interpretes: pregunta de nuevo '¿Confirma la cita? Responda sí o no'."
            )
        ultimo_id_borrador = borrador.get("ultimo_mensaje_id")
        if ultimo_id_borrador is not None:
            if ultimo.pk <= ultimo_id_borrador:
                raise ErrorHerramienta(
                    "El mensaje de confirmación debe ser posterior al resumen. Pregunta de nuevo "
                    "'¿Confirma? Responda sí o no'."
                )
        elif ultimo.creado <= creado:
            # Borradores antiguos (sin id): se conserva la comprobación por hora.
            raise ErrorHerramienta(
                "El último mensaje del paciente no es una confirmación clara (sí o no). "
                "No lo interpretes: pregunta de nuevo '¿Confirma la cita? Responda sí o no'."
            )

        datos = borrador["datos"]
        tipo = borrador.get("tipo")
        cita_creada = cita_cancelada = cita_modificada = None

        # 3. Se revalida y se guarda todo junto: o se aplica, o no cambia nada.
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
                cita_creada = serializer.save()
                # Sin el id de la cita: el modelo no debe verlo ni repetirlo.
                resultado = {
                    "cita_creada": True,
                    "fecha": cita_creada.fecha.isoformat(),
                    "hora": cita_creada.hora_inicio.strftime("%H:%M"),
                }
            elif tipo == "cancelar_cita":
                cita = self._cita_del_paciente(datos.get("cita_id"))
                cita.estado = Atencion.Estado.CANCELADA
                cita.save(update_fields=["estado", "actualizada"])
                cita_cancelada = cita
                resultado = {
                    "cita_cancelada": True,
                    "fecha": cita.fecha.isoformat(),
                    "hora": cita.hora_inicio.strftime("%H:%M"),
                }
            elif tipo == "modificar_cita":
                cita = self._cita_del_paciente(datos.get("cita_id"))
                cambios = datos.get("cambios") or {}
                serializer = AtencionSerializer(
                    instance=cita, data=cambios, partial=True,
                    context={"request": self.request},
                )
                if not serializer.is_valid():
                    raise ErrorHerramienta(self._errores(serializer))
                cita = serializer.save()
                cita_modificada = cita
                resultado = {
                    "cita_modificada": True,
                    "fecha": cita.fecha.isoformat(),
                    "hora": cita.hora_inicio.strftime("%H:%M"),
                }
            else:
                raise ErrorHerramienta("Acción pendiente desconocida.")

        self._limpiar_borrador()
        # El aviso es informativo y nunca debe romper la confirmación del paciente.
        if cita_creada is not None:
            notificaciones.notificar_cita_creada(cita_creada)
        elif cita_cancelada is not None:
            notificaciones.notificar_cita_cancelada(cita_cancelada)
        elif cita_modificada is not None:
            notificaciones.notificar_cita_modificada(
                cita_modificada, borrador.get("resumen", "")
            )
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
    "preparar_cita", "preparar_cancelacion_cita", "preparar_modificacion_cita",
    "confirmar_accion", "cancelar_accion",
    "consultar_tratamientos", "solicitar_revision_administrador",
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
        "se usa la de la sede. Sirve también para registrar familiares aunque el número ya tenga "
        "otro paciente.",
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
        "Prepara una cita para el paciente seleccionado, para confirmación. Duración fija de 20 minutos. "
        "Si el paciente no elige doctor ('cualquiera'), omite doctor_id: la herramienta asigna uno libre.",
        {
            "sede_id": ENTERO, "doctor_id": {**ENTERO, "description": "Opcional; omitir si no hay preferencia"},
            "tipo_trabajo_id": ENTERO,
            "fecha": {**TEXTO, "description": "AAAA-MM-DD"},
            "hora_inicio": {**TEXTO, "description": "HH:MM"},
        },
        ["sede_id", "tipo_trabajo_id", "fecha", "hora_inicio"],
    ),
    _herramienta(
        "preparar_cancelacion_cita",
        "Prepara la cancelación de una cita del paciente, para confirmación. Usa el id que "
        "devuelve listar_mis_citas. Solo se pueden cancelar citas futuras del propio paciente.",
        {"cita_id": ENTERO},
        ["cita_id"],
    ),
    _herramienta(
        "preparar_modificacion_cita",
        "Prepara el cambio de fecha, hora, sede, doctor o tratamiento de una cita del paciente, "
        "para confirmación. Indica solo lo que el paciente pidió cambiar.",
        {
            "cita_id": ENTERO,
            "sede_id": ENTERO,
            "doctor_id": {**ENTERO, "description": "Opcional; omitir si no hay preferencia"},
            "tipo_trabajo_id": ENTERO,
            "fecha": {**TEXTO, "description": "AAAA-MM-DD"},
            "hora_inicio": {**TEXTO, "description": "HH:MM"},
        },
        ["cita_id"],
    ),
    _herramienta(
        "confirmar_accion",
        "Guarda la cita, el alta del paciente, la cancelación o el cambio preparados. Solo llámala "
        "cuando el paciente haya confirmado el resumen.",
    ),
    _herramienta("cancelar_accion", "Descarta la acción pendiente si el paciente no la quiere."),
    _herramienta(
        "consultar_tratamientos",
        "Tratamientos activos con su precio de referencia en lempiras (L). Úsala cuando el paciente "
        "pregunte cuánto cuesta algo o qué tratamientos hay. Con 'texto' filtra por nombre.",
        {"texto": {**TEXTO, "description": "Parte del nombre del tratamiento (opcional)"}},
    ),
    _herramienta(
        "solicitar_revision_administrador",
        "Avisa al administrador que el paciente pide un tratamiento que NO aparece en "
        "consultar_tratamientos. Llámala y dile al paciente que ese tratamiento no está disponible "
        "por ahora y que alguien de la clínica se comunicará con él.",
        {"motivo": {**TEXTO, "description": "Qué tratamiento o precio pidió el paciente"}},
        ["motivo"],
    ),
]
