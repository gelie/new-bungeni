# Generated manually for adding permission fields to Role and Facet

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('workflows', '0005_add_group_to_workflowtype'),
    ]

    operations = [
        migrations.AddField(
            model_name='facet',
            name='can_create',
            field=models.BooleanField(default=False, help_text='Can create workflows in this state'),
        ),
        migrations.AddField(
            model_name='facet',
            name='can_transition',
            field=models.BooleanField(default=False, help_text='Can transition workflows from this state'),
        ),
        migrations.AddField(
            model_name='role',
            name='can_create_subworkflows',
            field=models.BooleanField(default=False, help_text='Can create sub-workflows'),
        ),
        migrations.AddField(
            model_name='role',
            name='can_transition_workflows',
            field=models.BooleanField(default=False, help_text='Can transition workflows'),
        ),
        migrations.AddField(
            model_name='role',
            name='can_manage_workflow_types',
            field=models.BooleanField(default=False, help_text='Can manage workflow types'),
        ),
        migrations.AddField(
            model_name='role',
            name='can_manage_states',
            field=models.BooleanField(default=False, help_text='Can manage states'),
        ),
    ]
