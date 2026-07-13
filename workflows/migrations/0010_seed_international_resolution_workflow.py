from django.db import migrations

WORKFLOW_NAME = "International Resolution"


STATE_SPECS = [
    {
        "name": "In Progress",
        "order": 1,
        "is_initial": True,
        "is_terminal": False,
        "allows_referrals": True,
        "color": "#B3995D",
        "description": "Initial state while the resolution is being processed.",
    },
    {
        "name": "Follow Up",
        "order": 2,
        "is_initial": False,
        "is_terminal": False,
        "allows_referrals": True,
        "color": "#5B8F22",
        "description": "Follow-up activities after deadline-related escalation.",
    },
    {
        "name": "Implemented",
        "order": 3,
        "is_initial": False,
        "is_terminal": True,
        "allows_referrals": False,
        "color": "#B3995D",
        "description": "Terminal state once the resolution has been implemented.",
    },
]


TRANSITION_SPECS = [
    {
        "name": "deadline",
        "from_state": "In Progress",
        "to_state": "Follow Up",
        "order": 1,
    },
    {
        "name": "action",
        "from_state": "Follow Up",
        "to_state": "Implemented",
        "order": 2,
    },
    {
        "name": "complete",
        "from_state": "In Progress",
        "to_state": "Implemented",
        "order": 3,
    },
]


def _update_instance_fields(instance, field_values):
    changed_fields = []
    for field_name, expected_value in field_values.items():
        if getattr(instance, field_name) != expected_value:
            setattr(instance, field_name, expected_value)
            changed_fields.append(field_name)
    if changed_fields:
        instance.save(update_fields=changed_fields)


def seed_international_resolution_workflow(apps, schema_editor):
    Group = apps.get_model("workflows", "Group")
    Role = apps.get_model("workflows", "Role")
    State = apps.get_model("workflows", "State")
    Transition = apps.get_model("workflows", "Transition")
    WorkflowType = apps.get_model("workflows", "WorkflowType")

    workflow_type = WorkflowType.objects.filter(name__iexact=WORKFLOW_NAME).first()

    if workflow_type is None:
        default_group = Group.objects.filter(is_active=True).order_by("name").first()
        if default_group is None:
            # No eligible group exists yet; skip safely.
            return

        workflow_type = WorkflowType.objects.create(
            name=WORKFLOW_NAME,
            description=(
                "Workflow for international resolutions from in-progress processing "
                "through follow-up to implementation."
            ),
            group=default_group,
            enabled=True,
        )

        create_roles = Role.objects.filter(can_create_workflows=True)
        if create_roles.exists():
            workflow_type.create_roles.set(create_roles)

    states_by_name = {}

    for spec in STATE_SPECS:
        state, created = State.objects.get_or_create(
            workflow_type=workflow_type,
            name=spec["name"],
            defaults={
                "description": spec["description"],
                "is_initial": spec["is_initial"],
                "is_terminal": spec["is_terminal"],
                "allows_referrals": spec["allows_referrals"],
                "order": spec["order"],
                "color": spec["color"],
            },
        )

        if not created:
            _update_instance_fields(
                state,
                {
                    "description": spec["description"],
                    "is_initial": spec["is_initial"],
                    "is_terminal": spec["is_terminal"],
                    "allows_referrals": spec["allows_referrals"],
                    "order": spec["order"],
                    "color": spec["color"],
                },
            )

        states_by_name[spec["name"]] = state

    transition_roles = list(workflow_type.create_roles.all())
    if not transition_roles:
        transition_roles = list(Role.objects.filter(can_transition_workflows=True))
    if not transition_roles:
        transition_roles = list(Role.objects.all())

    for spec in TRANSITION_SPECS:
        transition, created = Transition.objects.get_or_create(
            workflow_type=workflow_type,
            from_state=states_by_name[spec["from_state"]],
            to_state=states_by_name[spec["to_state"]],
            defaults={
                "name": spec["name"],
                "order": spec["order"],
                "requires_comment": False,
            },
        )

        if not created:
            _update_instance_fields(
                transition,
                {
                    "name": spec["name"],
                    "order": spec["order"],
                    "requires_comment": False,
                },
            )

        if transition_roles:
            transition.allowed_roles.set(transition_roles)


def noop_reverse(apps, schema_editor):
    # Intentionally non-destructive: keep seeded workflow definitions on rollback.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("workflows", "0009_alter_attachment_url_lengths"),
    ]

    operations = [
        migrations.RunPython(seed_international_resolution_workflow, noop_reverse),
    ]
