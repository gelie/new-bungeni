from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Attachment, Comment, Group, State, Workflow, WorkflowType

User = get_user_model()


class WorkflowDetailCommentAttachmentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="admin",
            email="admin@test.com",
            is_superuser=True,
            is_staff=True,
        )
        self.client.force_login(self.user)

        self.group = Group.objects.create(name="Parliament", group_type="legislature")
        self.workflow_type = WorkflowType.objects.create(name="Bill", group=self.group)
        self.state = State.objects.create(
            workflow_type=self.workflow_type,
            name="Draft",
            is_initial=True,
        )
        self.workflow = Workflow.objects.create(
            workflow_type=self.workflow_type,
            title="Comment Attachment Test",
            current_state=self.state,
            owner=self.user,
        )

    def test_comment_without_attachment_does_not_raise_uuid_error(self):
        response = self.client.post(
            reverse("workflow_detail", args=[str(self.workflow.pk)]),
            {"comment": "Plain comment", "attachment_ids": ""},
        )

        self.assertEqual(response.status_code, 302)
        comment = Comment.objects.get(workflow=self.workflow, text="Plain comment")
        self.assertEqual(comment.attachments.count(), 0)

    def test_comment_with_invalid_attachment_id_is_ignored(self):
        response = self.client.post(
            reverse("workflow_detail", args=[str(self.workflow.pk)]),
            {"comment": "Comment with invalid ID", "attachment_ids": "not-a-uuid"},
        )

        self.assertEqual(response.status_code, 302)
        comment = Comment.objects.get(
            workflow=self.workflow, text="Comment with invalid ID"
        )
        self.assertEqual(comment.attachments.count(), 0)

    def test_comment_with_csv_attachment_ids_attaches_files(self):
        attachment1 = Attachment.objects.create(
            name="Doc 1.pdf",
            drive_id="drive-1",
            item_id="item-1",
            type="document",
            uploaded_by=self.user,
        )
        attachment2 = Attachment.objects.create(
            name="Doc 2.pdf",
            drive_id="drive-2",
            item_id="item-2",
            type="document",
            uploaded_by=self.user,
        )

        response = self.client.post(
            reverse("workflow_detail", args=[str(self.workflow.pk)]),
            {
                "comment": "Comment with attachments",
                "attachment_ids": f"{attachment1.pk},{attachment2.pk}",
            },
        )

        self.assertEqual(response.status_code, 302)
        comment = Comment.objects.get(
            workflow=self.workflow, text="Comment with attachments"
        )
        self.assertEqual(comment.attachments.count(), 2)
        self.assertIn(attachment1, comment.attachments.all())
        self.assertIn(attachment2, comment.attachments.all())

    def test_comment_with_attachment_ids_array_style_empty_value(self):
        response = self.client.post(
            reverse("workflow_detail", args=[str(self.workflow.pk)]),
            {"comment": "Array style empty", "attachment_ids[]": ""},
        )

        self.assertEqual(response.status_code, 302)
        comment = Comment.objects.get(workflow=self.workflow, text="Array style empty")
        self.assertEqual(comment.attachments.count(), 0)

    def test_workflow_detail_get_ignores_invalid_delegate_user_id(self):
        self.workflow.data = {
            "delegate_group": [{"user_id": "", "delegation_role": "Delegate"}]
        }
        self.workflow.save()

        response = self.client.get(
            reverse("workflow_detail", args=[str(self.workflow.pk)])
        )

        self.assertEqual(response.status_code, 200)
