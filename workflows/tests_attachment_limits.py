from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Attachment, Group, State, Workflow, WorkflowType

User = get_user_model()


class AttachmentFieldLengthTests(TestCase):
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
            title="Attachment length test",
            current_state=self.state,
            owner=self.user,
        )

    def test_attachment_supports_long_sharepoint_identifiers(self):
        long_name = "N" * 300
        long_drive_id = "D" * 300
        long_item_id = "I" * 300
        long_mimetype = "application/" + ("vnd.long." * 30)

        attachment = Attachment.objects.create(
            name=long_name,
            drive_id=long_drive_id,
            item_id=long_item_id,
            mimetype=long_mimetype,
            type="document",
            uploaded_by=self.user,
            related_workflow=self.workflow,
        )

        self.assertEqual(attachment.name, long_name)
        self.assertEqual(attachment.drive_id, long_drive_id)
        self.assertEqual(attachment.item_id, long_item_id)
        self.assertEqual(attachment.mimetype, long_mimetype)

    def test_attachment_supports_long_sharepoint_urls(self):
        long_download_url = "https://example.com/download?" + ("token=" + "a" * 1900)
        long_web_url = "https://example.com/view/" + ("b" * 1900)

        attachment = Attachment.objects.create(
            name="Long URL file",
            drive_id="drive-short",
            item_id="item-short",
            type="document",
            uploaded_by=self.user,
            related_workflow=self.workflow,
            download_url=long_download_url,
            sharepoint_web_url=long_web_url,
        )

        self.assertEqual(attachment.download_url, long_download_url)
        self.assertEqual(attachment.sharepoint_web_url, long_web_url)
