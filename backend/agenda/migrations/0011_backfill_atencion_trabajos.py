from django.db import migrations


def crear_trabajos(apps, schema_editor):
    Atencion = apps.get_model("agenda", "Atencion")
    AtencionTrabajo = apps.get_model("agenda", "AtencionTrabajo")

    for atencion in Atencion.objects.select_related("tipo_trabajo").iterator():
        if AtencionTrabajo.objects.filter(atencion_id=atencion.pk).exists():
            continue
        precio = atencion.precio_paciente or atencion.tipo_trabajo.precio
        AtencionTrabajo.objects.create(
            atencion_id=atencion.pk,
            tipo_trabajo_id=atencion.tipo_trabajo_id,
            precio=precio,
            orden=0,
        )
        if atencion.precio_paciente != precio:
            Atencion.objects.filter(pk=atencion.pk).update(precio_paciente=precio)


def borrar_trabajos(apps, schema_editor):
    AtencionTrabajo = apps.get_model("agenda", "AtencionTrabajo")
    AtencionTrabajo.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("agenda", "0010_atencion_trabajos"),
    ]

    operations = [
        migrations.RunPython(crear_trabajos, borrar_trabajos),
    ]
