# Workflow Hierarchy Feature Documentation

## Overview

The Parliamentary Workflow Management System (PWMS) now supports hierarchical workflow relationships, allowing workflows to have parent-child relationships. This enables complex parliamentary processes like International Reports spawning multiple Resolutions that maintain their connection to the original report.

## Key Features

### Parent-Child Relationships
- Any workflow can have sub-workflows (children)
- Sub-workflows maintain a link back to their parent
- Hierarchies can be multiple levels deep
- Each relationship can have a specific type (resolution, amendment, follow-up, etc.)

### Circular Reference Prevention
- Database-level constraints prevent self-parenting
- Application-level validation prevents circular references
- Comprehensive validation ensures data integrity

### Rich API for Hierarchy Management
- Helper methods for navigating hierarchies
- Automatic inheritance of properties from parent workflows
- Convenient creation methods for sub-workflows

## Model Changes

### New Fields in `Workflow` Model

```python
# Parent-child workflow relationships
parent_workflow = models.ForeignKey(
    "self",
    on_delete=models.CASCADE,
    null=True,
    blank=True,
    related_name="sub_workflows",
    help_text="Parent workflow (e.g., International Report for Resolutions)",
)

# Optional: Add a field to indicate the relationship type
relationship_type = models.CharField(
    max_length=50,
    choices=[
        ("resolution", "Resolution"),
        ("amendment", "Amendment"),
        ("follow_up", "Follow-up Action"),
        ("supplement", "Supplementary Document"),
        ("correction", "Correction/Erratum"),
    ],
    null=True,
    blank=True,
    help_text="Type of relationship to parent workflow",
)
```

### New Methods

#### Navigation Methods
- `get_root_workflow()` - Get the top-level parent workflow
- `get_all_descendants()` - Get all descendant workflows recursively
- `get_workflow_hierarchy_path()` - Get full path from root to current workflow

#### Property Methods
- `hierarchy_level` - Depth level in hierarchy (0 for root)
- `is_root_workflow` - Check if workflow has no parent
- `has_sub_workflows` - Check if workflow has children

#### Creation and Validation
- `can_be_parent_of(workflow_type)` - Check valid parent-child relationships
- `create_sub_workflow()` - Helper method to create child workflows
- `clean()` - Validation to prevent circular references

## Usage Examples

### Creating a Sub-Workflow

```python
from workflows.models import Workflow, WorkflowType

# Get the parent workflow (e.g., International Report)
report = Workflow.objects.get(id=3)

# Get the resolution workflow type
resolution_type = WorkflowType.objects.get(name='International Resolution')

# Create a resolution as a child of the report
resolution = report.create_sub_workflow(
    workflow_type=resolution_type,
    title='Resolution R2024-001: Climate Action Framework',
    relationship_type='resolution',
    description='Resolution emanating from the International Climate Report'
)
```

### Navigating Hierarchies

```python
# Get all sub-workflows of a parent
sub_workflows = report.sub_workflows.all()

# Get the root workflow from any level
root = resolution.get_root_workflow()

# Get the full hierarchy path
path = resolution.get_workflow_hierarchy_path()

# Check hierarchy properties
print(f"Level: {resolution.hierarchy_level}")
print(f"Is root: {resolution.is_root_workflow}")
print(f"Has children: {resolution.has_sub_workflows}")
```

### Working with Relationships

```python
# Find all resolutions for a report
resolutions = report.sub_workflows.filter(relationship_type='resolution')

# Get siblings of a workflow
if workflow.parent_workflow:
    siblings = workflow.parent_workflow.sub_workflows.exclude(id=workflow.id)

# Get all descendants
all_descendants = report.get_all_descendants()
```

## Management Commands

### Show Workflow Hierarchy

Display workflow hierarchies in a tree format:

```bash
# Show all root workflows and their hierarchies
python manage.py show_workflow_hierarchy --show-all

# Show hierarchy for a specific workflow
python manage.py show_workflow_hierarchy --workflow-id 3

# Show orphan workflows (no parent or children)
python manage.py show_workflow_hierarchy --show-orphans

# Filter by workflow type
python manage.py show_workflow_hierarchy --show-all --workflow-type "International"
```

## Admin Interface

### Enhanced Admin Features
- Parent-child relationships visible in list view
- Hierarchical grouping in admin interface
- Prevents circular references in admin forms
- Relationship type filtering

### Admin Fieldsets
The admin interface is organized into logical sections:
- **Basic Information**: Type, title, description
- **Hierarchy**: Parent workflow and relationship type
- **Assignment**: Groups, owners, assignments
- **State & Priority**: Current state, priority, deadlines
- **Data**: JSON data fields
- **Timestamps**: Creation and modification dates

## Database Schema

### New Database Fields
- `parent_workflow_id`: Foreign key to parent workflow
- `relationship_type`: Type of parent-child relationship

### Indexes
- Index on `parent_workflow` for efficient hierarchy queries
- Composite indexes for common query patterns

### Constraints
- Check constraint prevents workflows from being their own parent
- Foreign key constraint ensures referential integrity

## Use Cases

### International Reports → Resolutions
```
📁 International Report: Climate Change Assessment 2024
  ├─ International Resolution: R2024-001: Carbon Reduction Framework (resolution)
  ├─ International Resolution: R2024-002: Green Technology Initiative (resolution)
  └─ International Resolution: R2024-003: Environmental Standards Update (resolution)
```

### Bills → Amendments
```
📁 Bill: Environmental Protection Act 2024
  ├─ Amendment: A2024-001: Industrial Emissions (amendment)
  ├─ Amendment: A2024-002: Renewable Energy Targets (amendment)
  └─ Follow-up Action: Implementation Timeline (follow_up)
```

### Complex Hierarchies
```
📁 Motion: Parliamentary Reform Initiative
  ├─ Sub-Motion: Committee Structure Reform (resolution)
  │   ├─ Amendment: A2024-010: Committee Size Limits (amendment)
  │   └─ Amendment: A2024-011: Committee Powers (amendment)
  ├─ Sub-Motion: Voting Procedures Update (resolution)
  └─ Follow-up Action: Implementation Plan (follow_up)
```

## API Integration

### View Enhancements
The `workflow_detail` view now includes hierarchy context:

```python
context = {
    "workflow": workflow,
    "hierarchy_path": workflow.get_workflow_hierarchy_path(),
    "sub_workflows": workflow.sub_workflows.all(),
    "sibling_workflows": sibling_workflows,
    "root_workflow": workflow.get_root_workflow(),
    "is_root": workflow.is_root_workflow,
    "has_children": workflow.has_sub_workflows,
    "hierarchy_level": workflow.hierarchy_level,
}
```

### Template Usage
In templates, you can now display workflow hierarchies:

```html
<!-- Show hierarchy path -->
<nav aria-label="breadcrumb">
  <ol class="breadcrumb">
    {% for workflow in hierarchy_path %}
      <li class="breadcrumb-item">
        <a href="{% url 'workflow_detail' workflow.id %}">{{ workflow.title }}</a>
      </li>
    {% endfor %}
  </ol>
</nav>

<!-- Show sub-workflows -->
{% if sub_workflows %}
  <div class="sub-workflows">
    <h4>Related {{ workflow.workflow_type.name }}s</h4>
    {% for sub in sub_workflows %}
      <div class="sub-workflow">
        <a href="{% url 'workflow_detail' sub.id %}">{{ sub.title }}</a>
        {% if sub.relationship_type %}({{ sub.get_relationship_type_display }}){% endif %}
      </div>
    {% endfor %}
  </div>
{% endif %}
```

## Best Practices

### Relationship Design
1. **Define Clear Relationships**: Use the `can_be_parent_of()` method to enforce valid parent-child relationships
2. **Consistent Naming**: Use descriptive titles that indicate the relationship
3. **Proper Types**: Always specify the `relationship_type` for clarity

### Performance Considerations
1. **Use Select Related**: Always use `select_related()` when querying hierarchies
2. **Limit Depth**: Consider the performance impact of very deep hierarchies
3. **Batch Operations**: Use bulk operations for creating multiple sub-workflows

### Data Integrity
1. **Validation**: Always call `clean()` or use the `create_sub_workflow()` helper
2. **Cascading Deletes**: Understand that deleting a parent workflow deletes all children
3. **Backup Strategy**: Implement proper backup procedures for hierarchical data

## Migration Information

The hierarchy feature was added in migration `0007_add_workflow_hierarchy.py`, which:
- Adds `parent_workflow` foreign key field
- Adds `relationship_type` choice field  
- Creates database index on `parent_workflow`
- Adds constraint to prevent self-parenting

## Future Enhancements

Potential future improvements could include:
- Workflow templates for common parent-child patterns
- Bulk operations for managing hierarchies
- Visual hierarchy editor in the admin interface
- Workflow dependency tracking beyond parent-child relationships
- Import/export functionality for complex hierarchies

## Troubleshooting

### Common Issues

**Circular Reference Error**
```
Cannot set parent workflow: this would create a circular reference.
```
*Solution*: Ensure you're not trying to make a workflow a child of its own descendant.

**Invalid Parent-Child Relationship**
```
International Resolution cannot be parent of International Report
```
*Solution*: Check the `can_be_parent_of()` rules and ensure valid relationship types.

**Performance Issues with Deep Hierarchies**
*Solution*: Use `select_related()` in queries and consider flattening very deep structures.

For additional support or questions, refer to the main PWMS documentation or contact the development team.
