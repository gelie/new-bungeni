# Role-Based Workflow Permissions System

## Overview

The workflow permission system has been refactored to use **Role-based permissions** where permissions are explicitly defined on the `Role` model rather than configured per-workflow instance. This provides a more scalable, maintainable, and intuitive RBAC (Role-Based Access Control) system.

## Key Concepts

### 1. Permissions are Defined by Role

Each `Role` now has explicit workflow permission fields:

- **`can_view_workflows`** - Can view workflows in their groups
- **`can_edit_workflows`** - Can edit workflow details
- **`can_delete_workflows`** - Can delete workflows
- **`can_transition_workflows`** - Can perform state transitions
- **`can_create_workflows`** - Can create new workflows
- **`can_assign_workflows`** - Can assign workflows to other users
- **`can_manage_permissions`** - Can grant/revoke group access to workflows

### 2. Group Access vs Permissions

**`WorkflowGroupAccess`** now only tracks **WHICH** groups have access to a workflow, not **WHAT** they can do.

- Simplified model - just tracks group membership
- Permissions come from the user's Role within that group
- Multiple groups can access the same workflow

### 3. Permission Hierarchy

When checking permissions, the system follows this hierarchy:

1. **Workflow Owner** - Always has full permissions (except `manage_permissions`)
2. **WorkflowRolePermission Overrides** - Workflow-specific role permission overrides (if configured)
3. **Role Default Permissions** - The role's default workflow permissions
4. **Superuser** - Always has all permissions

## How It Works

### Permission Check Flow

```python
user = request.user
workflow = Workflow.objects.get(pk=123)

# Check if user can edit
if workflow.can_user_edit(user):
    # User can edit
    pass
```

**Behind the scenes:**

1. Is user a superuser? → **Yes** = Allow
2. Is user the workflow owner? → **Yes** = Allow (except manage_permissions)
3. Does user have a membership in a group with access to this workflow?
   - Get user's role in that group
   - Check if WorkflowRolePermission override exists for this workflow+role
     - **Yes** → Use override permissions
     - **No** → Use Role's default `can_edit_workflows` permission

### Example Scenario

**Setup:**
- Role: "Secretary" has `can_edit_workflows=True`
- Role: "Member" has `can_edit_workflows=False`
- Workflow: "Budget Report 2024"
- Group: "Finance Committee" has access to the workflow

**Users:**
- Alice is a "Secretary" in Finance Committee → **Can edit** (role permission)
- Bob is a "Member" in Finance Committee → **Cannot edit** (role permission)
- Charlie is the workflow owner → **Can edit** (owner privilege)

## Managing Permissions

### 1. Configure Role Permissions (Admin)

Navigate to **Admin → Roles → [Role Name]**

Set the default workflow permissions for this role:

```
✓ Can view workflows
✓ Can edit workflows
✗ Can delete workflows
✓ Can transition workflows
✓ Can create workflows
✗ Can assign workflows
✗ Can manage permissions
```

**Common Role Configurations:**

| Role | View | Edit | Delete | Transition | Create | Assign | Manage |
|------|------|------|--------|------------|--------|--------|--------|
| Chairperson | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Secretary | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✗ |
| Member | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ |
| Observer | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

### 2. Grant Group Access to Workflow

**Via Admin Interface:**
1. Go to **Workflow → [Workflow Name]**
2. Scroll to **"Group Access"** section
3. Add a group
4. Mark as "Primary" if this is the owning group

**Programmatically:**
```python
workflow.add_group_access(
    group=finance_committee,
    is_primary=True,
    granted_by=request.user,
    notes="Shared with Finance for budget review"
)
```

### 3. Override Role Permissions for Specific Workflows (Optional)

If you need to give a specific role different permissions for ONE workflow:

1. Go to **Admin → Workflow Group Access → [Select Access Record]**
2. Add **Workflow Role Permission** inline
3. Select the role and set custom permissions

**Example:**
- Normally "Members" cannot edit workflows
- But for "Annual Report 2024", Members CAN edit
- Create WorkflowRolePermission: Member → can_edit=True (only for this workflow)

## Workflow Creation

When creating a workflow, users now:

1. **Select Workflow Type** - Determines available states/transitions
2. **Select Owning Group** - Which group owns this workflow (from user's groups)
3. **Fill in details** - Title, description, priority, etc.

The system automatically:
- Creates `WorkflowGroupAccess` for the selected group
- Marks it as `is_primary=True`
- Permissions are determined by user's Role in that group

## Migration Path

### Existing Workflows

The migration `0031_populate_rbac_from_existing` populated `WorkflowGroupAccess` from existing `WorkflowType.group` assignments.

All existing workflows now have:
- Group access record for their original `WorkflowType.group`
- Marked as `inherited_from_type=True`
- Marked as `is_primary=True`

### Existing Roles

The migration `0033_set_role_permission_defaults` set sensible defaults based on role names:

- **Chairperson/Chair** → Full permissions
- **Secretary/Clerk** → Create, edit, transition, assign
- **Vice/Deputy** → Edit, transition, assign
- **Member** → View and transition
- **Observer/Guest** → View only
- **Unknown roles** → View and transition (safe default)

**Review and adjust these in Admin as needed!**

## Benefits

### ✅ Explicit Permissions
- No guessing what a role can do
- Clear permission matrix in admin
- Easy to audit and understand

### ✅ Centralized Management
- Configure role permissions once
- Applies to all workflows automatically
- No per-workflow permission configuration needed

### ✅ Scalable
- Add new roles easily
- Permissions are consistent across all workflows
- Override when needed for specific cases

### ✅ Flexible
- Multi-group access still supported
- Workflow-specific overrides available
- Owner always maintains control

### ✅ Maintainable
- Simpler data model
- Fewer permission records to manage
- Clear separation: Access vs Permissions

## API Reference

### Workflow Model Methods

```python
# Check permissions
workflow.can_user_view(user) → bool
workflow.can_user_edit(user) → bool
workflow.can_user_delete(user) → bool
workflow.can_user_assign(user) → bool  # NEW
workflow.can_user_manage_permissions(user) → bool  # NEW

# Manage group access
workflow.add_group_access(group, is_primary=False, granted_by=None, notes="")
workflow.get_accessible_groups() → QuerySet[Group]
```

### Role Model Methods

```python
# Get permission dictionary
role.get_workflow_permissions() → dict
# Returns: {
#   'can_view': True,
#   'can_edit': False,
#   'can_delete': False,
#   'can_transition': True,
#   'can_create': False,
#   'can_assign': False,
#   'can_manage_permissions': False,
# }
```

### WorkflowGroupAccess Model Methods

```python
# Get role permission summary for this access
group_access.get_role_permissions_summary() → dict
# Returns: {
#   'Secretary': ['view', 'edit', 'transition'],
#   'Member': ['view'],
# }
```

## Troubleshooting

### User Can't See Workflows

**Check:**
1. Is user a member of a group with access? (`WorkflowGroupAccess` exists)
2. Does user's role have `can_view_workflows=True`?
3. Is the group membership active? (`GroupMembership.is_active=True`)

### User Can't Edit Workflows

**Check:**
1. Is user the workflow owner? (owners can always edit)
2. Does user's role have `can_edit_workflows=True`?
3. Is there a WorkflowRolePermission override blocking them?
4. Check state permissions (legacy system may still apply)

### Permission Changes Not Taking Effect

**Remember:**
- Role permission changes apply immediately
- No need to update existing workflows
- Clear browser cache if using cached data
- Check for WorkflowRolePermission overrides

## Best Practices

1. **Define Roles Carefully** - Think about your organization's structure
2. **Use Descriptive Role Names** - "Committee Secretary" vs "Secretary"
3. **Start Restrictive** - Give minimum permissions, add more as needed
4. **Document Custom Overrides** - Use the `notes` field in WorkflowRolePermission
5. **Regular Audits** - Review role permissions quarterly
6. **Test Permission Changes** - Use test users before applying to production roles

## Future Enhancements

Potential future improvements:

- **Permission Groups** - Bundle permissions into reusable sets
- **Time-based Permissions** - Temporary elevated access
- **Conditional Permissions** - Based on workflow data/state
- **Permission Templates** - Quick-apply common configurations
- **Audit Logging** - Track permission changes over time

---

**Questions or Issues?** Contact the system administrator or refer to the Django admin documentation.
