# Generated manually for adding group to WorkflowType and making Workflow.group nullable

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('workflows', '0004_workflowtype_enabled'),
    ]

    operations = [
        migrations.AddField(
            model_name='workflowtype',
            name='group',
            field=models.ForeignKey(default=1, help_text='The group that owns all workflows of this type', on_delete=django.db.models.deletion.PROTECT, related_name='workflow_types', to='workflows.group'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='workflow',
            name='group',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='workflows', to='workflows.group'),
        ),
    ]
