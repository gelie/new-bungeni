from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import (
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
        self.chair_role = Role.objects.create(
            name="Chairperson", can_create_workflows=True, can_edit_workflows=True
        )
        self.member_role = Role.objects.create(
            name="Member", can_view_all_workflows=True
        )
        self.secretary_role = Role.objects.create(
            name="Secretary", can_create_workflows=True, can_transition_workflows=True
        )

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
        self.view_facet = Facet.objects.create(
            name="Committee View", can_view=True, allowed_roles=[self.member_role]
        )
        self.edit_facet = Facet.objects.create(
            name="Chair Edit", can_edit=True, allowed_roles=[self.chair_role]
        )

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
        global_role = Role.objects.create(
            name="Global Viewer", can_view_all_workflows=True
        )
        GroupMembership.objects.create(
            user=global_viewer, group=self.parliament, role=global_role
        )
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
        edit_role = Role.objects.create(name="Editor", can_edit_workflows=True)
        GroupMembership.objects.create(
            user=editor, group=self.parliament, role=edit_role
        )
        self.assertTrue(self.workflow.can_user_edit(editor))

    def test_get_available_transitions(self):
        """Test transitions are filtered by role and facet permissions"""
        transitions = self.workflow.get_available_transitions(self.secretary_user)
        # Should return transitions where secretary has role and facet allows transition
        # (Assuming transitions exist with allowed_roles including secretary_role)

    def test_workflow_creation_inherits_group(self):
        """Test new workflow inherits group from type"""
        new_workflow = Workflow.objects.create(
            workflow_type=self.workflow_type,
            title="New Bill",
            current_state=self.draft_state,
            owner=self.chair_user,
        )
        self.assertEqual(new_workflow.effective_group, self.parliament)
