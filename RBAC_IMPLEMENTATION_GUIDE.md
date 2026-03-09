# RBAC Permission System Implementation Guide

## Overview

This document provides a complete implementation guide for decoupling Workflow permissions from WorkflowType groups and implementing a proper Role-Based Access Control (RBAC) system.

## Problem Statement

**Current Issue:**
- WorkflowType has a `group` field that determines ownership for ALL workflow instances
- Committee secretaries can view other committees' workflows because permissions are inherited from the template
- No way to assign workflows to multiple groups or change group ownership at instance level

## Solution: Multi-Group RBAC System

### New Models

#### 1. WorkflowGroupAccess
Defines which groups have access to a specific workflow instance.

```python
class WorkflowGroupAccess(models.Model):
    workflow = ForeignKey(Workflow, on_delete=CASCADE, related_name="group_access")
    group = ForeignKey(Group, on_delete=CASCADE, related_name="workflow_access")
    
    # Permission flags
    can_view = BooleanField(default=True)
    can_edit = BooleanField(default=False)
    can_delete = BooleanField(default=False)
    can_transition = BooleanField(default=False)
    
    # Metadata
    is_primary = BooleanField(default=False)  # Primary owning group
    inherited_from_type = BooleanField(default=False)  # From WorkflowType
    granted_by = ForeignKey(User, null=True, blank=True)
    granted_at = DateTimeField(auto_now_add=True)
    notes = TextField(blank=True)
```

#### 2. WorkflowRolePermission
Fine-grained role-based permissions within a group's access.

```python
class WorkflowRolePermission(models.Model):
    group_access = ForeignKey(WorkflowGroupAccess, on_delete=CASCADE, related_name="role_permissions")
    role = ForeignKey(Role, on_delete=CASCADE)
    
    # Override permissions for this role
    can_view = BooleanField(default=True)
    can_edit = BooleanField(default=False)
    can_delete = BooleanField(default=False)
    can_transition = BooleanField(default=False)
    
    # State-specific permissions (optional)
    allowed_states = ManyToManyField(State, blank=True)
```

### Key Features

1. **Multi-Group Access**: Workflows can be accessible to multiple groups simultaneously
2. **Instance-Level Control**: Each workflow instance can have different group access
3. **Role-Based Permissions**: Different roles within a group can have different permissions
4. **State-Specific Permissions**: Permissions can vary based on workflow state
5. **Backward Compatible**: Falls back to legacy WorkflowType.group system if no RBAC rules exist

### Implementation Steps

#### Step 1: Add Models to models.py
The new models have been added to `/home/gelie/Projects/pwms/workflows/models.py` after the WorkflowReferral model (around line 1016).

#### Step 2: Update Workflow Permission Methods
Updated methods in Workflow model:
- `_check_rbac_permission(user, permission_type)` - New method to check RBAC permissions
- `can_user_view(user)` - Updated to check RBAC first, then fall back to legacy
- `can_user_edit(user)` - Updated to check RBAC first, then fall back to legacy
- `can_user_delete(user)` - Updated to check RBAC first, then fall back to legacy
- `get_accessible_groups()` - New method to get all groups with access
- `add_group_access(...)` - Helper method to add group access

#### Step 3: Update Views
All views updated to query workflows using new RBAC system:
```python
# Old query
workflows = Workflow.objects.filter(
    Q(workflow_type__group__in=user_groups) | Q(referred_to__in=user_groups)
)

# New query (with backward compatibility)
workflows = Workflow.objects.filter(
    Q(group_access__group__in=user_groups) |  # New RBAC
    Q(workflow_type__group__in=user_groups) |  # Legacy
    Q(referred_to__in=user_groups)             # Referral
).distinct()
```

Updated views:
- `dashboard`
- `workflow_list`
- `reports_custom`
- `reports_export_csv`
- `reports_export_excel`
- `reports_recent_activity_pdf`

#### Step 4: Admin Interface (NEEDS FIXING)
Admin classes created for:
- `WorkflowGroupAccessAdmin` - Manage group access to workflows
- `WorkflowRolePermissionAdmin` - Manage role-specific permissions
- `WorkflowGroupAccessInline` - Inline in Workflow admin
- `WorkflowRolePermissionInline` - Inline in WorkflowGroupAccess admin

**CURRENT ISSUE**: The inline classes have import errors. Need to fix by using lazy model references.

#### Step 5: Create Migrations
Need to run:
```bash
python manage.py makemigrations workflows --name add_rbac_permission_models
python manage.py migrate
```

#### Step 6: Data Migration
After creating tables, need a data migration to populate WorkflowGroupAccess from existing workflows:

```python
def populate_rbac_from_existing(apps, schema_editor):
    Workflow = apps.get_model('workflows', 'Workflow')
    WorkflowGroupAccess = apps.get_model('workflows', 'WorkflowGroupAccess')
    
    for workflow in Workflow.objects.all():
        # Create primary group access from WorkflowType.group
        WorkflowGroupAccess.objects.get_or_create(
            workflow=workflow,
            group=workflow.workflow_type.group,
            defaults={
                'can_view': True,
                'can_edit': True,
                'can_delete': True,
                'can_transition': True,
                'is_primary': True,
                'inherited_from_type': True,
            }
        )
```

### Usage Examples

#### Grant Access to Additional Group
```python
workflow = Workflow.objects.get(pk=123)
finance_committee = Group.objects.get(name="Finance Committee")

# Grant view-only access
workflow.add_group_access(
    group=finance_committee,
    can_view=True,
    can_edit=False,
    granted_by=request.user
)
```

#### Set Role-Specific Permissions
```python
from workflows.models import WorkflowGroupAccess, WorkflowRolePermission

access = WorkflowGroupAccess.objects.get(workflow=workflow, group=finance_committee)

# Chairperson can edit
WorkflowRolePermission.objects.create(
    group_access=access,
    role=Role.objects.get(name="Chairperson"),
    can_view=True,
    can_edit=True,
    can_transition=True
)

# Members can only view
WorkflowRolePermission.objects.create(
    group_access=access,
    role=Role.objects.get(name="Member"),
    can_view=True,
    can_edit=False,
    can_transition=False
)
```

#### Check Permissions
```python
# Automatically uses RBAC if configured, falls back to legacy
if workflow.can_user_view(request.user):
    # User can view
    pass

if workflow.can_user_edit(request.user):
    # User can edit
    pass
```

### Migration Path

1. **Phase 1**: Deploy code with new models (backward compatible)
2. **Phase 2**: Run migrations to create tables
3. **Phase 3**: Run data migration to populate from existing data
4. **Phase 4**: Gradually configure RBAC for workflows as needed
5. **Phase 5**: (Optional) Deprecate WorkflowType.group field in future

### Benefits

1. **Solves Committee Secretary Issue**: Each workflow instance can be restricted to its specific committee
2. **Multi-Group Collaboration**: Workflows can be shared across multiple groups
3. **Fine-Grained Control**: Different roles have different permissions
4. **Audit Trail**: Track who granted access and when
5. **Flexible**: Permissions can change based on workflow state
6. **Backward Compatible**: Existing workflows continue to work

### Next Steps

1. **Fix admin.py import errors** - Use string model references or lazy imports
2. **Create and run migrations**
3. **Create data migration script**
4. **Test with sample workflows**
5. **Update UI to allow managing group access**
6. **Document for end users**

## Admin Interface Fix Required

The admin.py file has NameError issues because inline classes reference models before they're fully loaded. 

**Solution**: Remove the inline admin classes temporarily and add them back after testing the basic functionality, OR use a different approach like defining them in a separate admin module.

Temporary workaround - comment out these lines in admin.py:
- Line ~270: `inlines = [WorkflowGroupAccessInline]` in WorkflowAdmin
- Line ~351: `inlines = [WorkflowRolePermissionInline]` in WorkflowGroupAccessAdmin

Then run migrations and add the inlines back later with proper lazy loading.
