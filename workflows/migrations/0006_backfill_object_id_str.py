from django.db import migrations

BATCH_SIZE = 1000


def _backfill_object_id_str(apps, schema_editor):
    for model_name in ("Attachment", "Notification"):
        model = apps.get_model("workflows", model_name)
        qs = model.objects.filter(object_id__isnull=False, object_id_str__isnull=True)

        to_update = []
        for obj in qs.iterator(chunk_size=BATCH_SIZE):
            obj.object_id_str = str(obj.object_id)
            to_update.append(obj)
            if len(to_update) >= BATCH_SIZE:
                model.objects.bulk_update(to_update, ["object_id_str"])
                to_update = []

        if to_update:
            model.objects.bulk_update(to_update, ["object_id_str"])


def _reverse_backfill_object_id_str(apps, schema_editor):
    for model_name in ("Attachment", "Notification"):
        model = apps.get_model("workflows", model_name)
        qs = model.objects.filter(object_id__isnull=True, object_id_str__isnull=False)

        to_update = []
        for obj in qs.iterator(chunk_size=BATCH_SIZE):
            value = (obj.object_id_str or "").strip()
            obj.object_id = int(value) if value.isdigit() else None
            to_update.append(obj)
            if len(to_update) >= BATCH_SIZE:
                model.objects.bulk_update(to_update, ["object_id"])
                to_update = []

        if to_update:
            model.objects.bulk_update(to_update, ["object_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("workflows", "0005_add_object_id_str_fields"),
    ]

    operations = [
        migrations.RunPython(_backfill_object_id_str, _reverse_backfill_object_id_str),
    ]
