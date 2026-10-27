from django.db import migrations, models


def copiar_especialidad(apps, schema_editor):
    """Cada especialidad única del doctor pasa a la nueva relación múltiple."""
    Doctor = apps.get_model("users", "Doctor")
    for doctor in Doctor.objects.exclude(especialidad__isnull=True).only(
        "id", "especialidad_id"
    ):
        doctor.especialidades.add(doctor.especialidad_id)


def restaurar_especialidad(apps, schema_editor):
    """Al revertir, conserva la primera especialidad en el campo único."""
    Doctor = apps.get_model("users", "Doctor")
    for doctor in Doctor.objects.all():
        primera = doctor.especialidades.order_by("pk").first()
        if primera is not None:
            doctor.especialidad = primera
            doctor.save(update_fields=["especialidad"])


class Migration(migrations.Migration):

    dependencies = [
        ("servicios", "0003_alter_tipotrabajo_precio"),
        ("users", "0008_doctor_especialidad_catalogo"),
    ]

    operations = [
        migrations.AddField(
            model_name="doctor",
            name="especialidades",
            field=models.ManyToManyField(
                blank=True, related_name="doctores", to="servicios.especialidad"
            ),
        ),
        migrations.RunPython(copiar_especialidad, restaurar_especialidad),
        migrations.RemoveField(model_name="doctor", name="especialidad"),
    ]
