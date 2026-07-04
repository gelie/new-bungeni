from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Attachment, Group, Notification, State, Workflow, WorkflowType

User = get_user_model()


class GenericForeignKeyUUIDTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", email="owner@test.com")
        self.group = Group.objects.create(name="Parliament", group_type="legislature")
        self.workflow_type = WorkflowType.objects.create(name="Bill", group=self.group)
        self.state = State.objects.create(
            workflow_type=self.workflow_type,
            name="Draft",
            is_initial=True,
        )
        self.workflow = Workflow.objects.create(
            workflow_type=self.workflow_type,
            title="GFK UUID Test",
            current_state=self.state,
            owner=self.user,
        )

    def test_notification_content_object_round_trip_with_uuid_pk(self):
        notification = Notification.objects.create(
            user=self.user,
            verb=Notification.VERB_TRANSITION,
            title="Transition",
            message="Workflow moved",
            content_object=self.workflow,
        )

        self.assertEqual(str(notification.object_id), str(self.workflow.pk))

        fetched = Notification.objects.get(pk=notification.pk)
        self.assertEqual(fetched.object_id, str(self.workflow.pk))
        self.assertEqual(fetched.content_object, self.workflow)

    def test_attachment_content_object_round_trip_with_uuid_pk(self):
        attachment = Attachment.objects.create(
            name="Test Document.pdf",
            drive_id="drive123",
            item_id="item123",
            type="document",
            uploaded_by=self.user,
            content_object=self.workflow,
        )

        self.assertEqual(str(attachment.object_id), str(self.workflow.pk))

        fetched = Attachment.objects.get(pk=attachment.pk)
        self.assertEqual(fetched.object_id, str(self.workflow.pk))
        self.assertEqual(fetched.content_object, self.workflow)
