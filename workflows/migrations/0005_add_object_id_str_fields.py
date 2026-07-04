from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workflows", "0004_alter_auditlog_object_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="attachment",
            name="object_id_str",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="notification",
            name="object_id_str",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddIndex(
            model_name="attachment",
            index=models.Index(
                fields=["content_type", "object_id_str"],
                name="workflows_a_ct_oidstr_idx",
            ),
        ),
    ]
