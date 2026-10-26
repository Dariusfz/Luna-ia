import django.db.models.deletion
from django.db import migrations, models


def copiar_especialidades(apps, schema_editor):
    """Convierte cada texto de especialidad existente en una entrada del catálogo."""
    Doctor = apps.get_model("users", "Doctor")
    Especialidad = apps.get_model("servicios", "Especialidad")
    for doctor in Doctor.objects.exclude(especialidad_texto="").only("id", "especialidad_texto"):
        nombre = doctor.especialidad_texto.strip()
        if not nombre:
            continue
        esp, _ = Especialidad.objects.get_or_create(nombre=nombre)
        doctor.especialidad_catalogo = esp
        doctor.save(update_fields=["especialidad_catalogo"])


class Migration(migrations.Migration):

    dependencies = [
        ("servicios", "0002_especialidad_tipotrabajo_precio"),
        ("users", "0007_recuperacioncontrasena"),
    ]

    operations = [
        # 1. Renombrar el texto viejo para no perderlo mientras se copia.
        migrations.RenameField(
            model_name="doctor",
            old_name="especialidad",
            new_name="especialidad_texto",
        ),
        # 2. Crear la referencia nueva al catálogo.
        migrations.AddField(
            model_name="doctor",
            name="especialidad_catalogo",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="doctores_catalogo",
                to="servicios.especialidad",
            ),
        ),
        # 3. Copiar los textos existentes al catálogo.
        migrations.RunPython(copiar_especialidades, migrations.RunPython.noop),
        # 4. Quitar el texto viejo y dejar la referencia con el nombre definitivo.
        migrations.RemoveField(model_name="doctor", name="especialidad_texto"),
        migrations.RenameField(
            model_name="doctor",
            old_name="especialidad_catalogo",
            new_name="especialidad",
        ),
        migrations.AlterField(
            model_name="doctor",
            name="especialidad",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="doctores",
                to="servicios.especialidad",
            ),
        ),
    ]
