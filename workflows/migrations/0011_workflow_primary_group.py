import django.db.models.deletion
from django.db import migrations, models


def backfill_primary_group(apps, schema_editor):
    Workflow = apps.get_model("workflows", "Workflow")
    WorkflowGroupAccess = apps.get_model("workflows", "WorkflowGroupAccess")

    db_alias = schema_editor.connection.alias

    workflows = (
        Workflow.objects.using(db_alias)
        .select_related("workflow_type__group")
        .order_by("created_at", "id")
    )

    for workflow in workflows.iterator():
        accesses = list(
            WorkflowGroupAccess.objects.using(db_alias)
            .filter(workflow_id=workflow.id)
            .order_by("granted_at", "id")
        )
        access_by_group_id = {access.group_id: access for access in accesses}

        chosen = None

        # If primary_group is already set (manual pre-population), honor it and ensure access exists.
        if workflow.primary_group_id:
            chosen = access_by_group_id.get(workflow.primary_group_id)
            if chosen is None:
                chosen = WorkflowGroupAccess.objects.using(db_alias).create(
                    workflow_id=workflow.id,
                    group_id=workflow.primary_group_id,
                    is_primary=True,
                    inherited_from_type=False,
                    notes="Auto-created during migration 0011 to align with Workflow.primary_group",
                )

        if chosen is None:
            primary_accesses = [access for access in accesses if access.is_primary]

            if primary_accesses:
                # Deterministic: earliest granted primary access
                chosen = primary_accesses[0]
            elif accesses:
                # Deterministic fallback: earliest access
                chosen = accesses[0]
            else:
                # Legacy fallback for workflows with no access rows at all
                chosen = WorkflowGroupAccess.objects.using(db_alias).create(
                    workflow_id=workflow.id,
                    group_id=workflow.workflow_type.group_id,
                    is_primary=True,
                    inherited_from_type=True,
                    notes="Auto-created during migration 0011 from WorkflowType.group",
                )

        # Ensure Workflow.primary_group is populated from the chosen access
        if workflow.primary_group_id != chosen.group_id:
            Workflow.objects.using(db_alias).filter(id=workflow.id).update(
                primary_group_id=chosen.group_id
            )

        # Normalize to exactly one primary access per workflow
        WorkflowGroupAccess.objects.using(db_alias).filter(
            workflow_id=workflow.id, is_primary=True
        ).exclude(id=chosen.id).update(is_primary=False)

        if not chosen.is_primary:
            WorkflowGroupAccess.objects.using(db_alias).filter(id=chosen.id).update(
                is_primary=True
            )


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("workflows", "0010_seed_international_resolution_workflow"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflow",
            name="primary_group",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="primary_workflows",
                to="workflows.group",
                help_text="Primary owning group for this workflow instance",
            ),
        ),
        migrations.RunPython(backfill_primary_group, noop_reverse),
    ]
