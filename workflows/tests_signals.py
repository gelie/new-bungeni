from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from .models import AuditLog, Group, State, Workflow, WorkflowType

User = get_user_model()


class WorkflowAuditSignalUUIDSerializationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", email="owner@test.com")
        self.group = Group.objects.create(name="Parliament", group_type="legislature")
        self.workflow_type = WorkflowType.objects.create(name="Bill", group=self.group)

        self.state_draft = State.objects.create(
            workflow_type=self.workflow_type,
            name="Draft",
            is_initial=True,
        )
        self.state_review = State.objects.create(
            workflow_type=self.workflow_type,
            name="Review",
        )

        self.workflow = Workflow.objects.create(
            workflow_type=self.workflow_type,
            title="UUID Serialization Test",
            current_state=self.state_draft,
            owner=self.user,
        )

    def _latest_workflow_update_log(self):
        workflow_ct = ContentType.objects.get_for_model(Workflow)
        return (
            AuditLog.objects.filter(
                content_type=workflow_ct,
                object_id=self.workflow.pk,
                action="update",
            )
            .order_by("-timestamp")
            .first()
        )

    def test_workflow_state_change_audit_serializes_uuid_ids(self):
        self.workflow.current_state = self.state_review
        self.workflow.save()

        update_log = self._latest_workflow_update_log()

        self.assertIsNotNone(update_log)
        self.assertIn("current_state_id", update_log.changes)

        current_state_change = update_log.changes["current_state_id"]
        self.assertEqual(current_state_change["from"], str(self.state_draft.pk))
        self.assertEqual(current_state_change["to"], str(self.state_review.pk))
        self.assertIsInstance(current_state_change["from"], str)
        self.assertIsInstance(current_state_change["to"], str)

    def test_workflow_owner_change_audit_serializes_uuid_ids(self):
        new_owner = User.objects.create_user(
            username="new_owner", email="new_owner@test.com"
        )

        self.workflow.owner = new_owner
        self.workflow.save()

        update_log = self._latest_workflow_update_log()

        self.assertIsNotNone(update_log)
        self.assertIn("owner_id", update_log.changes)

        owner_change = update_log.changes["owner_id"]
        self.assertEqual(owner_change["from"], str(self.user.pk))
        self.assertEqual(owner_change["to"], str(new_owner.pk))
        self.assertIsInstance(owner_change["from"], str)
        self.assertIsInstance(owner_change["to"], str)

    def test_workflow_type_change_audit_serializes_uuid_ids(self):
        new_group = Group.objects.create(name="Senate", group_type="legislature")
        new_workflow_type = WorkflowType.objects.create(name="Motion", group=new_group)
        new_state = State.objects.create(
            workflow_type=new_workflow_type,
            name="New Draft",
            is_initial=True,
        )

        self.workflow.workflow_type = new_workflow_type
        self.workflow.current_state = new_state
        self.workflow.save()

        update_log = self._latest_workflow_update_log()

        self.assertIsNotNone(update_log)
        self.assertIn("workflow_type_id", update_log.changes)

        workflow_type_change = update_log.changes["workflow_type_id"]
        self.assertEqual(workflow_type_change["from"], str(self.workflow_type.pk))
        self.assertEqual(workflow_type_change["to"], str(new_workflow_type.pk))
        self.assertIsInstance(workflow_type_change["from"], str)
        self.assertIsInstance(workflow_type_change["to"], str)
