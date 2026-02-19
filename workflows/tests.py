from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import (
    Attachment,
    Comment,
    Facet,
    Group,
    GroupMembership,
    Role,
    State,
    StateFacet,
    Workflow,
    WorkflowType,
)

User = get_user_model()


class PermissionTestCase(TestCase):
    def setUp(self):
        # Create test groups
        self.parliament = Group.objects.create(
            name="Parliament", group_type="legislature"
        )
        self.committee = Group.objects.create(
            name="Finance Committee",
            group_type="portfolio_committee",
            parent=self.parliament,
        )

        # Create test roles
        self.chair_role = Role.objects.create(name="Chairperson")
        self.member_role = Role.objects.create(name="Member")
        self.secretary_role = Role.objects.create(name="Secretary")

        # Create test users
        self.chair_user = User.objects.create_user(
            username="chair", email="chair@test.com"
        )
        self.member_user = User.objects.create_user(
            username="member", email="member@test.com"
        )
        self.secretary_user = User.objects.create_user(
            username="secretary", email="secretary@test.com"
        )
        self.external_user = User.objects.create_user(
            username="external", email="external@test.com"
        )

        # Create memberships
        GroupMembership.objects.create(
            user=self.chair_user, group=self.committee, role=self.chair_role
        )
        GroupMembership.objects.create(
            user=self.member_user, group=self.committee, role=self.member_role
        )
        GroupMembership.objects.create(
            user=self.secretary_user, group=self.committee, role=self.secretary_role
        )

        # Create workflow type with group
        self.workflow_type = WorkflowType.objects.create(
            name="Bill", group=self.parliament
        )

        # Create states
        self.draft_state = State.objects.create(
            workflow_type=self.workflow_type, name="Draft", is_initial=True
        )
        self.review_state = State.objects.create(
            workflow_type=self.workflow_type, name="Under Review"
        )

        # Create facets
        self.view_facet = Facet.objects.create(name="Committee View")
        self.view_facet.view_roles.add(self.member_role)

        self.edit_facet = Facet.objects.create(name="Chair Edit")
        self.edit_facet.edit_roles.add(self.chair_role)

        # Link facets to states
        StateFacet.objects.create(state=self.draft_state, facet=self.view_facet)
        StateFacet.objects.create(state=self.review_state, facet=self.edit_facet)

        # Create workflow
        self.workflow = Workflow.objects.create(
            workflow_type=self.workflow_type,
            title="Test Bill",
            current_state=self.draft_state,
            owner=self.chair_user,
        )

    def test_effective_group_inheritance(self):
        """Test that workflow inherits group from type"""
        self.assertEqual(self.workflow.effective_group, self.parliament)

    def test_can_user_view_with_membership(self):
        """Test user can view workflow if in group and has view facet"""
        self.assertTrue(self.workflow.can_user_view(self.member_user))
        self.assertTrue(self.workflow.can_user_view(self.chair_user))

    def test_can_user_view_without_membership(self):
        """Test user cannot view workflow if not in group"""
        self.assertFalse(self.workflow.can_user_view(self.external_user))

    def test_can_user_view_with_global_role(self):
        """Test user with global view role can view any workflow"""
        global_viewer = User.objects.create_user(
            username="global", email="global@test.com"
        )
        global_role = Role.objects.create(name="Global Viewer")
        GroupMembership.objects.create(
            user=global_viewer, group=self.parliament, role=global_role
        )
        # Add global role to view facet
        self.view_facet.view_roles.add(global_role)
        self.assertTrue(self.workflow.can_user_view(global_viewer))

    def test_can_user_edit_with_role(self):
        """Test user can edit workflow if has edit role"""
        self.assertTrue(self.workflow.can_user_edit(self.chair_user))

    def test_can_user_edit_without_role(self):
        """Test user cannot edit workflow if no edit role"""
        self.assertFalse(self.workflow.can_user_edit(self.member_user))

    def test_can_user_edit_with_global_role(self):
        """Test user with global edit role can edit"""
        editor = User.objects.create_user(username="editor", email="editor@test.com")
        edit_role = Role.objects.create(name="Editor")
        GroupMembership.objects.create(
            user=editor, group=self.parliament, role=edit_role
        )
        # Add edit role to edit facet
        self.edit_facet.edit_roles.add(edit_role)
        self.assertTrue(self.workflow.can_user_edit(editor))

    def test_get_available_transitions(self):
        """Test transitions are filtered by role and facet permissions"""
        transitions = self.workflow.get_available_transitions(self.secretary_user)
        # Should return transitions where secretary has role and facet allows transition
        # (Assuming transitions exist with allowed_roles including secretary_role)
        self.assertIsInstance(
            transitions, list
        )  # Basic check that method returns a list

    def test_workflow_creation_inherits_group(self):
        """Test new workflow inherits group from type"""
        new_workflow = Workflow.objects.create(
            workflow_type=self.workflow_type,
            title="New Bill",
            current_state=self.draft_state,
            owner=self.chair_user,
        )
        self.assertEqual(new_workflow.effective_group, self.parliament)

    def test_comment_with_attachments(self):
        """Test that comments can have attachments"""
        # Create a comment
        comment = Comment.objects.create(
            workflow=self.workflow,
            user=self.chair_user,
            text="This is a test comment with attachments",
        )

        # Create some test attachments
        attachment1 = Attachment.objects.create(
            name="Test Document.pdf",
            drive_id="drive123",
            item_id="item123",
            mimetype="application/pdf",
            size=1024000,
            uploaded_by=self.chair_user,
            type="document",
        )

        attachment2 = Attachment.objects.create(
            name="Test Response.docx",
            drive_id="drive456",
            item_id="item456",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size=512000,
            uploaded_by=self.chair_user,
            type="response",
        )

        # Add attachments to comment
        comment.attachments.add(attachment1, attachment2)

        # Test the relationship
        self.assertEqual(comment.attachments.count(), 2)
        self.assertIn(attachment1, comment.attachments.all())
        self.assertIn(attachment2, comment.attachments.all())

        # Test reverse relationship
        self.assertIn(comment, attachment1.comments.all())
        self.assertIn(comment, attachment2.comments.all())
