from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from agenda.models import Atencion

from .models import Pago, PagoDoctor


def _sumar(registros) -> Decimal:
    return sum((registro.monto for registro in registros), Decimal("0"))


def _nombre_usuario(usuario) -> str | None:
    if usuario is None:
        return None
    return f"{usuario.first_name} {usuario.last_name}".strip() or usuario.username


def _etiqueta_atencion(atencion) -> str:
    tipos = [trabajo.tipo_trabajo.nombre for trabajo in atencion.trabajos.all()]
    trabajo = " + ".join(tipos) if tipos else atencion.tipo_trabajo.nombre
    return (
        f"{atencion.fecha} {atencion.hora_inicio:%H:%M} · "
        f"{atencion.paciente.nombres} {atencion.paciente.apellidos} · "
        f"{trabajo}"
    )


class PagoSerializer(serializers.ModelSerializer):
    atencion_etiqueta = serializers.SerializerMethodField()
    paciente_nombre = serializers.SerializerMethodField()
    sede_nombre = serializers.CharField(source="atencion.sede.nombre", read_only=True)
    tipo_trabajo_nombre = serializers.CharField(
        source="atencion.tipo_trabajo.nombre", read_only=True
    )
    doctor_nombre = serializers.SerializerMethodField()
    fecha_atencion = serializers.DateField(source="atencion.fecha", read_only=True)
    hora_inicio = serializers.TimeField(source="atencion.hora_inicio", read_only=True)
    metodo_nombre = serializers.CharField(source="get_metodo_display", read_only=True)
    registrado_por_nombre = serializers.SerializerMethodField()
    precio_paciente = serializers.DecimalField(
        source="atencion.precio_paciente", max_digits=12, decimal_places=2, read_only=True
    )
    total_pagado = serializers.SerializerMethodField()
    saldo_pendiente = serializers.SerializerMethodField()

    class Meta:
        model = Pago
        fields = [
            "id",
            "atencion",
            "atencion_etiqueta",
            "paciente_nombre",
            "sede_nombre",
            "tipo_trabajo_nombre",
            "doctor_nombre",
            "fecha_atencion",
            "hora_inicio",
            "monto",
            "metodo",
            "metodo_nombre",
            "fecha",
            "nota",
            "registrado_por",
            "registrado_por_nombre",
            "precio_paciente",
            "total_pagado",
            "saldo_pendiente",
            "creado",
        ]
        read_only_fields = [
            "id",
            "atencion_etiqueta",
            "paciente_nombre",
            "sede_nombre",
            "tipo_trabajo_nombre",
            "doctor_nombre",
            "fecha_atencion",
            "hora_inicio",
            "metodo_nombre",
            "registrado_por",
            "registrado_por_nombre",
            "precio_paciente",
            "total_pagado",
            "saldo_pendiente",
            "creado",
        ]

    def get_atencion_etiqueta(self, obj) -> str:
        return _etiqueta_atencion(obj.atencion)

    def get_paciente_nombre(self, obj) -> str:
        return f"{obj.atencion.paciente.nombres} {obj.atencion.paciente.apellidos}"

    def get_doctor_nombre(self, obj) -> str:
        return f"{obj.atencion.doctor.nombres} {obj.atencion.doctor.apellidos}"

    def get_registrado_por_nombre(self, obj) -> str | None:
        return _nombre_usuario(obj.registrado_por)

    def get_total_pagado(self, obj) -> str:
        return str(_sumar(obj.atencion.pagos.all()))

    def get_saldo_pendiente(self, obj) -> str:
        saldo = obj.atencion.precio_paciente - _sumar(obj.atencion.pagos.all())
        return str(max(saldo, Decimal("0")))

    def validate_atencion(self, atencion):
        if atencion.estado == Atencion.Estado.CANCELADA:
            raise serializers.ValidationError("No se puede cobrar una cita cancelada.")
        if atencion.precio_paciente <= 0:
            raise serializers.ValidationError(
                "Define el precio al paciente antes de registrar un abono."
            )
        return atencion

    def validate_monto(self, monto):
        if monto <= 0:
            raise serializers.ValidationError("El monto debe ser mayor que cero.")
        return monto

    def validate_fecha(self, fecha):
        if fecha > timezone.localdate():
            raise serializers.ValidationError("La fecha no puede ser futura.")
        return fecha

    def validate(self, data):
        atencion = data.get("atencion", getattr(self.instance, "atencion", None))
        monto = data.get("monto", getattr(self.instance, "monto", None))
        if atencion is None or monto is None:
            return data
        pagos = atencion.pagos.all()
        if self.instance is not None:
            pagos = pagos.exclude(pk=self.instance.pk)
        total = _sumar(pagos)
        if total + monto > atencion.precio_paciente:
            saldo = max(atencion.precio_paciente - total, Decimal("0"))
            raise serializers.ValidationError(
                {"monto": f"El abono supera el saldo pendiente de L {saldo}."}
            )
        return data

    def create(self, validated_data):
        request = self.context.get("request")
        usuario = request.user if request and request.user.is_authenticated else None
        return Pago.objects.create(registrado_por=usuario, **validated_data)


class PagoDoctorSerializer(serializers.ModelSerializer):
    atencion_etiqueta = serializers.SerializerMethodField()
    paciente_nombre = serializers.SerializerMethodField()
    sede_nombre = serializers.CharField(source="atencion.sede.nombre", read_only=True)
    tipo_trabajo_nombre = serializers.CharField(
        source="atencion.tipo_trabajo.nombre", read_only=True
    )
    doctor = serializers.PrimaryKeyRelatedField(read_only=True)
    doctor_nombre = serializers.SerializerMethodField()
    doctor_tipo = serializers.CharField(source="doctor.tipo", read_only=True)
    fecha_atencion = serializers.DateField(source="atencion.fecha", read_only=True)
    hora_inicio = serializers.TimeField(source="atencion.hora_inicio", read_only=True)
    metodo_nombre = serializers.CharField(source="get_metodo_display", read_only=True)
    registrado_por_nombre = serializers.SerializerMethodField()
    honorario_doctor = serializers.DecimalField(
        source="atencion.honorario_doctor", max_digits=12, decimal_places=2, read_only=True
    )
    total_pagado = serializers.SerializerMethodField()
    saldo_pendiente = serializers.SerializerMethodField()

    class Meta:
        model = PagoDoctor
        fields = [
            "id",
            "atencion",
            "atencion_etiqueta",
            "paciente_nombre",
            "sede_nombre",
            "tipo_trabajo_nombre",
            "doctor",
            "doctor_nombre",
            "doctor_tipo",
            "fecha_atencion",
            "hora_inicio",
            "monto",
            "metodo",
            "metodo_nombre",
            "fecha",
            "nota",
            "registrado_por",
            "registrado_por_nombre",
            "honorario_doctor",
            "total_pagado",
            "saldo_pendiente",
            "creado",
        ]
        read_only_fields = [
            "id",
            "atencion_etiqueta",
            "paciente_nombre",
            "sede_nombre",
            "tipo_trabajo_nombre",
            "doctor",
            "doctor_nombre",
            "doctor_tipo",
            "fecha_atencion",
            "hora_inicio",
            "metodo_nombre",
            "registrado_por",
            "registrado_por_nombre",
            "honorario_doctor",
            "total_pagado",
            "saldo_pendiente",
            "creado",
        ]

    def get_atencion_etiqueta(self, obj) -> str:
        return _etiqueta_atencion(obj.atencion)

    def get_paciente_nombre(self, obj) -> str:
        return f"{obj.atencion.paciente.nombres} {obj.atencion.paciente.apellidos}"

    def get_doctor_nombre(self, obj) -> str:
        return f"{obj.doctor.nombres} {obj.doctor.apellidos}"

    def get_registrado_por_nombre(self, obj) -> str | None:
        return _nombre_usuario(obj.registrado_por)

    def get_total_pagado(self, obj) -> str:
        return str(_sumar(obj.atencion.pagos_doctor.all()))

    def get_saldo_pendiente(self, obj) -> str:
        saldo = obj.atencion.honorario_doctor - _sumar(obj.atencion.pagos_doctor.all())
        return str(max(saldo, Decimal("0")))

    def validate_atencion(self, atencion):
        if atencion.estado == Atencion.Estado.CANCELADA:
            raise serializers.ValidationError("No se puede pagar una cita cancelada.")
        if atencion.honorario_doctor <= 0:
            raise serializers.ValidationError(
                "Define el honorario del doctor antes de registrar un pago."
            )
        return atencion

    def validate_monto(self, monto):
        if monto <= 0:
            raise serializers.ValidationError("El monto debe ser mayor que cero.")
        return monto

    def validate_fecha(self, fecha):
        if fecha > timezone.localdate():
            raise serializers.ValidationError("La fecha no puede ser futura.")
        return fecha

    def validate(self, data):
        atencion = data.get("atencion", getattr(self.instance, "atencion", None))
        monto = data.get("monto", getattr(self.instance, "monto", None))
        if atencion is None or monto is None:
            return data
        pagos = atencion.pagos_doctor.all()
        if self.instance is not None:
            pagos = pagos.exclude(pk=self.instance.pk)
        total = _sumar(pagos)
        if total + monto > atencion.honorario_doctor:
            saldo = max(atencion.honorario_doctor - total, Decimal("0"))
            raise serializers.ValidationError(
                {"monto": f"El pago supera el saldo pendiente de L {saldo}."}
            )
        return data

    def create(self, validated_data):
        request = self.context.get("request")
        usuario = request.user if request and request.user.is_authenticated else None
        atencion = validated_data["atencion"]
        return PagoDoctor.objects.create(
            doctor=atencion.doctor,
            registrado_por=usuario,
            **validated_data,
        )
