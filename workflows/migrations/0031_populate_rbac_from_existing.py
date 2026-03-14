# Generated data migration to populate RBAC tables from existing workflows

from django.db import migrations


def populate_rbac_permissions(apps, schema_editor):
    """
    Populate WorkflowGroupAccess from existing workflows.
    Each workflow gets a primary group access record based on its WorkflowType.group
    """
    Workflow = apps.get_model('workflows', 'Workflow')
    WorkflowGroupAccess = apps.get_model('workflows', 'WorkflowGroupAccess')
    
    workflows = Workflow.objects.select_related('workflow_type', 'workflow_type__group').all()
    
    access_records = []
    for workflow in workflows:
        # Create primary group access from WorkflowType.group
        access_records.append(
            WorkflowGroupAccess(
                workflow=workflow,
                group=workflow.workflow_type.group,
                can_view=True,
                can_edit=True,
                can_delete=True,
                can_transition=True,
                is_primary=True,
                inherited_from_type=True,
                granted_by=None,
                notes="Auto-populated from WorkflowType.group during RBAC migration"
            )
        )
    
    # Bulk create for efficiency
    WorkflowGroupAccess.objects.bulk_create(access_records, ignore_conflicts=True)
    
    print(f"Created {len(access_records)} WorkflowGroupAccess records")


def reverse_populate(apps, schema_editor):
    """
    Reverse migration: delete all auto-populated RBAC records
    """
    WorkflowGroupAccess = apps.get_model('workflows', 'WorkflowGroupAccess')
    deleted_count = WorkflowGroupAccess.objects.filter(inherited_from_type=True).delete()[0]
    print(f"Deleted {deleted_count} auto-populated WorkflowGroupAccess records")


class Migration(migrations.Migration):

    dependencies = [
        ('workflows', '0030_add_rbac_permission_models'),
    ]

    operations = [
        migrations.RunPython(populate_rbac_permissions, reverse_populate),
    ]
