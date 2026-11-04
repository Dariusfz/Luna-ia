from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from config.validadores import MENSAJE_MONTO_MAXIMO, MONTO_MAXIMO
from pacientes.querysets import pacientes_visibles
from servicios.models import TipoTrabajo
from users.models import Doctor
from users.permisos import puede_usar_sede

from .horarios import error_horario
from .models import Atencion, AtencionTrabajo, JornadaExterna, ListaEspera

# Estados que reservan el horario del doctor y del paciente.
ESTADOS_QUE_OCUPAN = (Atencion.Estado.PENDIENTE, Atencion.Estado.CONFIRMADA)


class AtencionTrabajoSerializer(serializers.ModelSerializer):
    tipo_trabajo_nombre = serializers.CharField(
        source="tipo_trabajo.nombre", read_only=True
    )

    class Meta:
        model = AtencionTrabajo
        fields = ["id", "tipo_trabajo", "tipo_trabajo_nombre", "precio"]


class AtencionSerializer(serializers.ModelSerializer):
    # Nombres legibles para las tablas (solo lectura).
    sede_nombre = serializers.SerializerMethodField()
    doctor_nombre = serializers.SerializerMethodField()
    doctor_tipo = serializers.CharField(source="doctor.tipo", read_only=True)
    paciente_nombre = serializers.SerializerMethodField()
    tipo_trabajo_nombre = serializers.SerializerMethodField()
    origen_nombre = serializers.CharField(source="get_origen_display", read_only=True)
    creado_por_nombre = serializers.SerializerMethodField()
    total_pagado = serializers.SerializerMethodField()
    saldo_pendiente = serializers.SerializerMethodField()
    total_pagado_doctor = serializers.SerializerMethodField()
    saldo_doctor = serializers.SerializerMethodField()
    trabajos = AtencionTrabajoSerializer(many=True, read_only=True)
    tipos_trabajo = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=TipoTrabajo.objects.all(),
        required=False,
        write_only=True,
    )
    tipo_trabajo = serializers.PrimaryKeyRelatedField(
        queryset=TipoTrabajo.objects.all(),
        required=False,
    )

    class Meta:
        model = Atencion
        fields = [
            "id",
            "sede",
            "sede_nombre",
            "doctor",
            "doctor_nombre",
            "doctor_tipo",
            "paciente",
            "paciente_nombre",
            "tipo_trabajo",
            "tipo_trabajo_nombre",
            "tipos_trabajo",
            "trabajos",
            "estado",
            "origen",
            "origen_nombre",
            "creado_por",
            "creado_por_nombre",
            "fecha",
            "hora_inicio",
            "hora_fin",
            "procedimiento",
            "precio_paciente",
            "honorario_doctor",
            "total_pagado",
            "saldo_pendiente",
            "total_pagado_doctor",
            "saldo_doctor",
            "observaciones",
            "creada",
            "actualizada",
        ]
        read_only_fields = [
            "id",
            "origen",
            "creado_por",
            "precio_paciente",
            "total_pagado",
            "saldo_pendiente",
            "total_pagado_doctor",
            "saldo_doctor",
            "creada",
            "actualizada",
        ]

    def get_sede_nombre(self, obj) -> str:
        return obj.sede.nombre

    def get_doctor_nombre(self, obj) -> str:
        return f"{obj.doctor.nombres} {obj.doctor.apellidos}"

    def get_paciente_nombre(self, obj) -> str:
        return f"{obj.paciente.nombres} {obj.paciente.apellidos}"

    def get_tipo_trabajo_nombre(self, obj) -> str:
        nombres = [trabajo.tipo_trabajo.nombre for trabajo in obj.trabajos.all()]
        return " + ".join(nombres) if nombres else obj.tipo_trabajo.nombre

    def get_creado_por_nombre(self, obj) -> str | None:
        if not obj.creado_por_id:
            return None
        nombre = f"{obj.creado_por.first_name} {obj.creado_por.last_name}".strip()
        return nombre or obj.creado_por.username

    @staticmethod
    def _sumar(registros) -> Decimal:
        return sum((registro.monto for registro in registros), Decimal("0"))

    def get_total_pagado(self, obj) -> str:
        return str(self._sumar(obj.pagos.all()))

    def get_saldo_pendiente(self, obj) -> str:
        saldo = obj.precio_paciente - self._sumar(obj.pagos.all())
        return str(max(saldo, Decimal("0")))

    def get_total_pagado_doctor(self, obj) -> str:
        return str(self._sumar(obj.pagos_doctor.all()))

    def get_saldo_doctor(self, obj) -> str:
        saldo = obj.honorario_doctor - self._sumar(obj.pagos_doctor.all())
        return str(max(saldo, Decimal("0")))

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get("request")
        origen = self.context.get("origen", Atencion.Origen.PANEL)
        if "creado_por" in self.context:
            creado_por = self.context["creado_por"]
        elif origen == Atencion.Origen.PANEL and request and request.user.is_authenticated:
            creado_por = request.user
        else:
            creado_por = None

        tipos = validated_data.pop("tipos_trabajo", None)
        tipo_principal = validated_data.pop("tipo_trabajo", None)
        if tipos is None:
            tipos = [tipo_principal] if tipo_principal else []
        if not tipos:
            raise serializers.ValidationError(
                {"tipos_trabajo": "Selecciona al menos un tipo de trabajo."}
            )

        validated_data["tipo_trabajo"] = tipos[0]
        validated_data["precio_paciente"] = sum(
            (tipo.precio for tipo in tipos), Decimal("0")
        )
        atencion = Atencion.objects.create(
            origen=origen, creado_por=creado_por, **validated_data
        )
        for indice, tipo in enumerate(tipos):
            AtencionTrabajo.objects.create(
                atencion=atencion,
                tipo_trabajo=tipo,
                precio=tipo.precio,
                orden=indice,
            )
        return atencion

    @transaction.atomic
    def update(self, instance, validated_data):
        tipos = validated_data.pop("tipos_trabajo", None)
        tipo_principal = validated_data.pop("tipo_trabajo", None)
        if tipos is None and tipo_principal is not None:
            tipos = [tipo_principal]
        if tipos is not None:
            if not tipos:
                raise serializers.ValidationError(
                    {"tipos_trabajo": "Selecciona al menos un tipo de trabajo."}
                )
            validated_data["tipo_trabajo"] = tipos[0]
            validated_data["precio_paciente"] = sum(
                (tipo.precio for tipo in tipos), Decimal("0")
            )

        atencion = super().update(instance, validated_data)
        if tipos is not None:
            for trabajo in atencion.trabajos.all():
                trabajo.delete()
            for indice, tipo in enumerate(tipos):
                AtencionTrabajo.objects.create(
                    atencion=atencion,
                    tipo_trabajo=tipo,
                    precio=tipo.precio,
                    orden=indice,
                )
        return atencion

    def validate_sede(self, sede):
        if not puede_usar_sede(self.context["request"].user, sede):
            raise serializers.ValidationError("No puedes registrar atenciones en esa sede.")
        return sede

    def validate_paciente(self, paciente):
        if not pacientes_visibles(self.context["request"].user).filter(pk=paciente.pk).exists():
            raise serializers.ValidationError("El paciente no existe o no está disponible para tu sede.")
        if not paciente.activo:
            raise serializers.ValidationError("El paciente está inactivo.")
        return paciente

    def validate_doctor(self, doctor):
        if not Doctor.objects.filter(pk=doctor.pk, activo=True).exists():
            raise serializers.ValidationError("El doctor está inactivo.")
        return doctor

    def validate_tipo_trabajo(self, tipo):
        if not tipo.activo:
            raise serializers.ValidationError("Este tipo de trabajo está inactivo.")
        return tipo

    def validate_tipos_trabajo(self, tipos):
        if not tipos:
            raise serializers.ValidationError(
                "Selecciona al menos un tipo de trabajo."
            )
        vistos = set()
        for tipo in tipos:
            if tipo.pk in vistos:
                raise serializers.ValidationError(
                    "No repitas el mismo tipo de trabajo."
                )
            if not tipo.activo:
                raise serializers.ValidationError(
                    f"El tipo de trabajo «{tipo.nombre}» está inactivo."
                )
            vistos.add(tipo.pk)
        return tipos

    def validate_honorario_doctor(self, valor):
        if valor < 0:
            raise serializers.ValidationError("El honorario no puede ser negativo.")
        if valor > MONTO_MAXIMO:
            raise serializers.ValidationError(MENSAJE_MONTO_MAXIMO)
        return valor

    def validate(self, data):
        tipos = data.get("tipos_trabajo")
        tipo = data.get("tipo_trabajo")
        if self.instance is None and not tipos and not tipo:
            raise serializers.ValidationError(
                {"tipos_trabajo": "Selecciona al menos un tipo de trabajo."}
            )
        if tipos:
            total = sum((item.precio for item in tipos), Decimal("0"))
            if total > MONTO_MAXIMO:
                raise serializers.ValidationError(
                    {"tipos_trabajo": MENSAJE_MONTO_MAXIMO}
                )

        inicio = data.get("hora_inicio", getattr(self.instance, "hora_inicio", None))
        fin = data.get("hora_fin", getattr(self.instance, "hora_fin", None))
        if inicio and fin and fin <= inicio:
            raise serializers.ValidationError(
                {"hora_fin": "La hora de fin debe ser posterior a la de inicio."}
            )
        # Un doctor solo atiende en las sedes que tiene asignadas.
        sede = data.get("sede", getattr(self.instance, "sede", None))
        doctor = data.get("doctor", getattr(self.instance, "doctor", None))
        if sede and doctor and not doctor.sedes.filter(pk=sede.pk).exists():
            raise serializers.ValidationError(
                {"doctor": "Este doctor no tiene asignada la sede seleccionada."}
            )
        paciente = data.get("paciente", getattr(self.instance, "paciente", None))
        estado = data.get("estado", getattr(self.instance, "estado", Atencion.Estado.PENDIENTE))
        fecha = data.get("fecha", getattr(self.instance, "fecha", None))
        # Una cita futura no puede marcarse como completada antes de ocurrir.
        if estado == Atencion.Estado.COMPLETADA and fecha and fecha > timezone.localdate():
            raise serializers.ValidationError(
                {"estado": "No puedes completar una cita con fecha futura."}
            )
        # Una cita nueva nace siempre pendiente; el estado se cambia al editarla.
        if self.instance is None and estado != Atencion.Estado.PENDIENTE:
            raise serializers.ValidationError(
                {"estado": "Una cita nueva se crea siempre como pendiente."}
            )
        # Solo se agendan citas para hoy o fechas futuras. Las citas existentes
        # se pueden seguir editando aunque su fecha ya haya pasado.
        if self.instance is None and fecha and fecha < timezone.localdate():
            raise serializers.ValidationError(
                {"fecha": "No puedes crear una cita en una fecha pasada."}
            )
        # La cita debe caber en un turno abierto de la sede y no caer en feriado.
        # Se valida al crear o cuando cambia sede, fecha u horas.
        campos_horario = {"sede", "fecha", "hora_inicio", "hora_fin"}
        if (
            estado in ESTADOS_QUE_OCUPAN
            and sede
            and fecha
            and inicio
            and fin
            and (self.instance is None or campos_horario & set(data.keys()))
        ):
            error = error_horario(sede, fecha, inicio, fin)
            if error:
                raise serializers.ValidationError({"hora_inicio": error})
        # Un doctor no puede tener dos citas activas que se solapen, ni en sedes distintas.
        # Un paciente tampoco puede estar en dos citas activas a la vez.
        if estado in ESTADOS_QUE_OCUPAN and doctor and paciente and fecha and inicio and fin:
            choques_doctor = Atencion.objects.filter(
                doctor=doctor,
                fecha=fecha,
                estado__in=ESTADOS_QUE_OCUPAN,
                hora_inicio__lt=fin,
                hora_fin__gt=inicio,
            )
            choques_paciente = Atencion.objects.filter(
                paciente=paciente,
                fecha=fecha,
                estado__in=ESTADOS_QUE_OCUPAN,
                hora_inicio__lt=fin,
                hora_fin__gt=inicio,
            )
            if self.instance is not None:
                choques_doctor = choques_doctor.exclude(pk=self.instance.pk)
                choques_paciente = choques_paciente.exclude(pk=self.instance.pk)
            if choques_doctor.exists():
                raise serializers.ValidationError(
                    {"hora_inicio": "El doctor ya tiene una cita en ese horario."}
                )
            if choques_paciente.exists():
                raise serializers.ValidationError(
                    {"hora_inicio": "El paciente ya tiene una cita en ese horario."}
                )
        return data


class JornadaExternaSerializer(serializers.ModelSerializer):
    class Meta:
        model = JornadaExterna
        fields = [
            "id",
            "doctor",
            "lugar",
            "tipo_trabajo",
            "fecha",
            "hora_inicio",
            "hora_fin",
            "monto_cobrado",
            "observaciones",
            "creada",
        ]
        read_only_fields = ["id", "creada"]

    def validate(self, data):
        inicio = data.get("hora_inicio", getattr(self.instance, "hora_inicio", None))
        fin = data.get("hora_fin", getattr(self.instance, "hora_fin", None))
        if inicio and fin and fin <= inicio:
            raise serializers.ValidationError(
                {"hora_fin": "La hora de fin debe ser posterior a la de inicio."}
            )
        return data


class ListaEsperaSerializer(serializers.ModelSerializer):
    sede_nombre = serializers.CharField(source="sede.nombre", read_only=True)
    paciente_nombre = serializers.SerializerMethodField()
    doctor_nombre = serializers.SerializerMethodField()
    tipo_trabajo_nombre = serializers.SerializerMethodField()
    prioridad_nombre = serializers.CharField(source="get_prioridad_display", read_only=True)
    estado_nombre = serializers.CharField(source="get_estado_display", read_only=True)
    atencion_fecha = serializers.DateField(source="atencion.fecha", read_only=True)
    atencion_hora_inicio = serializers.TimeField(
        source="atencion.hora_inicio", read_only=True
    )

    class Meta:
        model = ListaEspera
        fields = [
            "id",
            "sede",
            "sede_nombre",
            "paciente",
            "paciente_nombre",
            "doctor",
            "doctor_nombre",
            "tipo_trabajo",
            "tipo_trabajo_nombre",
            "prioridad",
            "prioridad_nombre",
            "estado",
            "estado_nombre",
            "fecha_deseada",
            "motivo",
            "atencion",
            "atencion_fecha",
            "atencion_hora_inicio",
            "creada",
            "actualizada",
        ]
        read_only_fields = ["id", "creada", "actualizada", "atencion"]

    def get_paciente_nombre(self, obj) -> str:
        return f"{obj.paciente.nombres} {obj.paciente.apellidos}"

    def get_doctor_nombre(self, obj) -> str | None:
        if not obj.doctor_id:
            return None
        return f"{obj.doctor.nombres} {obj.doctor.apellidos}"

    def get_tipo_trabajo_nombre(self, obj) -> str | None:
        return obj.tipo_trabajo.nombre if obj.tipo_trabajo_id else None

    def validate_sede(self, sede):
        if not puede_usar_sede(self.context["request"].user, sede):
            raise serializers.ValidationError("No puedes usar esa sede.")
        return sede

    def validate_paciente(self, paciente):
        if not pacientes_visibles(self.context["request"].user).filter(pk=paciente.pk).exists():
            raise serializers.ValidationError(
                "El paciente no existe o no está disponible para tu sede."
            )
        if not paciente.activo:
            raise serializers.ValidationError("El paciente está inactivo.")
        return paciente

    def validate_doctor(self, doctor):
        if not Doctor.objects.filter(pk=doctor.pk, activo=True).exists():
            raise serializers.ValidationError("El doctor está inactivo.")
        return doctor

    def validate_tipo_trabajo(self, tipo):
        if not tipo.activo:
            raise serializers.ValidationError("Este tipo de trabajo está inactivo.")
        return tipo

    def validate(self, data):
        sede = data.get("sede", getattr(self.instance, "sede", None))
        doctor = data.get("doctor", getattr(self.instance, "doctor", None))
        if sede and doctor and not doctor.sedes.filter(pk=sede.pk).exists():
            raise serializers.ValidationError(
                {"doctor": "Este doctor no tiene asignada la sede seleccionada."}
            )
        estado = data.get(
            "estado", getattr(self.instance, "estado", ListaEspera.Estado.ESPERANDO)
        )
        if self.instance is None and estado != ListaEspera.Estado.ESPERANDO:
            raise serializers.ValidationError(
                {"estado": "Una espera nueva se crea siempre en espera."}
            )
        if (
            self.instance is not None
            and estado == ListaEspera.Estado.AGENDADO
            and not self.instance.atencion_id
        ):
            raise serializers.ValidationError(
                {"estado": "Usa la acción Agendar para convertir la espera en cita."}
            )
        return data
