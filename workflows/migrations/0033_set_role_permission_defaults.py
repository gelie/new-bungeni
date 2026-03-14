# Data migration to set sensible default workflow permissions for existing roles

from django.db import migrations


def set_role_permission_defaults(apps, schema_editor):
    """
    Set sensible default workflow permissions based on common role names.
    
    Permission hierarchy (most common):
    - Chairperson/Chair: Full permissions including manage
    - Secretary: Create, edit, transition, assign
    - Vice Chair/Deputy: Edit, transition, assign
    - Member: View and transition
    - Observer/Guest: View only
    """
    Role = apps.get_model('workflows', 'Role')
    
    # Define permission templates based on role name patterns
    permission_templates = {
        # Full access roles
        'chairperson': {
            'can_view_workflows': True,
            'can_edit_workflows': True,
            'can_delete_workflows': True,
            'can_transition_workflows': True,
            'can_create_workflows': True,
            'can_assign_workflows': True,
            'can_manage_permissions': True,
        },
        'chair': {
            'can_view_workflows': True,
            'can_edit_workflows': True,
            'can_delete_workflows': True,
            'can_transition_workflows': True,
            'can_create_workflows': True,
            'can_assign_workflows': True,
            'can_manage_permissions': True,
        },
        # Secretary roles - can create and manage workflows
        'secretary': {
            'can_view_workflows': True,
            'can_edit_workflows': True,
            'can_delete_workflows': False,
            'can_transition_workflows': True,
            'can_create_workflows': True,
            'can_assign_workflows': True,
            'can_manage_permissions': False,
        },
        'clerk': {
            'can_view_workflows': True,
            'can_edit_workflows': True,
            'can_delete_workflows': False,
            'can_transition_workflows': True,
            'can_create_workflows': True,
            'can_assign_workflows': True,
            'can_manage_permissions': False,
        },
        # Deputy/Vice roles
        'vice': {
            'can_view_workflows': True,
            'can_edit_workflows': True,
            'can_delete_workflows': False,
            'can_transition_workflows': True,
            'can_create_workflows': False,
            'can_assign_workflows': True,
            'can_manage_permissions': False,
        },
        'deputy': {
            'can_view_workflows': True,
            'can_edit_workflows': True,
            'can_delete_workflows': False,
            'can_transition_workflows': True,
            'can_create_workflows': False,
            'can_assign_workflows': True,
            'can_manage_permissions': False,
        },
        # Regular members - can participate
        'member': {
            'can_view_workflows': True,
            'can_edit_workflows': False,
            'can_delete_workflows': False,
            'can_transition_workflows': True,
            'can_create_workflows': False,
            'can_assign_workflows': False,
            'can_manage_permissions': False,
        },
        # Read-only roles
        'observer': {
            'can_view_workflows': True,
            'can_edit_workflows': False,
            'can_delete_workflows': False,
            'can_transition_workflows': False,
            'can_create_workflows': False,
            'can_assign_workflows': False,
            'can_manage_permissions': False,
        },
        'guest': {
            'can_view_workflows': True,
            'can_edit_workflows': False,
            'can_delete_workflows': False,
            'can_transition_workflows': False,
            'can_create_workflows': False,
            'can_assign_workflows': False,
            'can_manage_permissions': False,
        },
    }
    
    updated_count = 0
    for role in Role.objects.all():
        role_name_lower = role.name.lower()
        
        # Find matching template
        matched_template = None
        for pattern, template in permission_templates.items():
            if pattern in role_name_lower:
                matched_template = template
                break
        
        # Apply template or default to view-only
        if matched_template:
            for field, value in matched_template.items():
                setattr(role, field, value)
            role.save()
            updated_count += 1
            print(f"Set permissions for role '{role.name}' based on pattern")
        else:
            # Default: view and transition only (safe default for unknown roles)
            role.can_view_workflows = True
            role.can_edit_workflows = False
            role.can_delete_workflows = False
            role.can_transition_workflows = True
            role.can_create_workflows = False
            role.can_assign_workflows = False
            role.can_manage_permissions = False
            role.save()
            updated_count += 1
            print(f"Set default permissions for role '{role.name}'")
    
    print(f"Updated permissions for {updated_count} roles")


def reverse_permissions(apps, schema_editor):
    """Reset all role permissions to defaults."""
    Role = apps.get_model('workflows', 'Role')
    
    Role.objects.all().update(
        can_view_workflows=True,
        can_edit_workflows=False,
        can_delete_workflows=False,
        can_transition_workflows=False,
        can_create_workflows=False,
        can_assign_workflows=False,
        can_manage_permissions=False,
    )
    print("Reset all role permissions to defaults")


class Migration(migrations.Migration):

    dependencies = [
        ('workflows', '0032_role_based_permissions'),
    ]

    operations = [
        migrations.RunPython(set_role_permission_defaults, reverse_permissions),
    ]
