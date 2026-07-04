from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workflows", "0006_backfill_object_id_str"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="attachment",
            name="workflows_a_content_e23568_idx",
        ),
        migrations.RemoveIndex(
            model_name="attachment",
            name="workflows_a_ct_oidstr_idx",
        ),
        migrations.RenameField(
            model_name="attachment",
            old_name="object_id",
            new_name="object_id_int_legacy",
        ),
        migrations.RenameField(
            model_name="notification",
            old_name="object_id",
            new_name="object_id_int_legacy",
        ),
        migrations.RenameField(
            model_name="attachment",
            old_name="object_id_str",
            new_name="object_id",
        ),
        migrations.RenameField(
            model_name="notification",
            old_name="object_id_str",
            new_name="object_id",
        ),
        migrations.AlterField(
            model_name="attachment",
            name="object_id",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AlterField(
            model_name="notification",
            name="object_id",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.RemoveField(
            model_name="attachment",
            name="object_id_int_legacy",
        ),
        migrations.RemoveField(
            model_name="notification",
            name="object_id_int_legacy",
        ),
        migrations.AddIndex(
            model_name="attachment",
            index=models.Index(
                fields=["content_type", "object_id"],
                name="workflows_a_content_e23568_idx",
            ),
        ),
    ]
