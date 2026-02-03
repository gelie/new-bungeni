import json

from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from mptt.models import MPTTModel, TreeForeignKey

# ============================================================================
# USER MODEL
# ============================================================================


class User(AbstractUser):
    """
    Custom User model extending Django's AbstractUser.
    Users can be MPs, staff, administrators, etc.
    """

    phone = models.CharField(max_length=20, blank=True)
    title = models.CharField(max_length=100, blank=True)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    is_active_member = models.BooleanField(default=True)
    date_joined_parliament = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.get_full_name() or self.username

    def get_groups_with_roles(self):
        """Get all groups this user belongs to with their roles"""
        return GroupMembership.objects.filter(user=self).select_related("group", "role")

    def has_role_in_group(self, role_name, group):
        """Check if user has a specific role in a group"""
        return GroupMembership.objects.filter(
            user=self, group=group, role__name=role_name, is_active=True
        ).exists()

    def can_transition_workflow(self, workflow_instance, transition):
        """Check if user can perform a specific workflow transition"""
        # Check if user has required role for this transition
        user_roles = (
            self.get_groups_with_roles()
            .filter(group=workflow_instance.group)
            .values_list("role", flat=True)
        )

        return transition.allowed_roles.filter(id__in=user_roles).exists()


# ============================================================================
# GROUP MODELS (MPTT for Hierarchical Structure)
# ============================================================================


class GroupType(models.Model):
    """
    Types of groups: Legislature, Chamber, Committee, Office, Party,
    Administration, Ministry, etc.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Group(MPTTModel):
    """
    Hierarchical group structure using MPTT.
    Examples:
    - Parliament of SA (root)
      - National Assembly (chamber)
        - Portfolio Committee on Finance (committee)
      - National Council of Provinces (chamber)
      - Joint Assembly (virtual chamber)
      - Administration (staff)
    - Executive (root)
      - Presidency
      - Ministries
    """

    name = models.CharField(max_length=255)
    short_name = models.CharField(max_length=100, blank=True)
    group_type = models.ForeignKey(GroupType, on_delete=models.PROTECT)
    parent = TreeForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    # Additional metadata
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    location = models.CharField(max_length=255, blank=True)

    class MPTTMeta:
        order_insertion_by = ["name"]

    class Meta:
        ordering = ["name"]
        unique_together = [["name", "parent"]]

    def __str__(self):
        return self.name

    def get_full_path(self):
        """Get full hierarchical path"""
        ancestors = self.get_ancestors(include_self=True)
        return " > ".join([g.name for g in ancestors])

    def get_active_members(self):
        """Get all active members of this group"""
        return User.objects.filter(
            memberships__group=self, memberships__is_active=True
        ).distinct()


# ============================================================================
# ROLE & MEMBERSHIP MODELS
# ============================================================================


class Role(models.Model):
    """
    Roles that users can have within groups.
    Examples: Chairperson, Secretary, Member, Speaker, Minister, etc.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    # Permission flags
    can_create_workflows = models.BooleanField(default=False)
    can_edit_workflows = models.BooleanField(default=False)
    can_delete_workflows = models.BooleanField(default=False)
    can_view_all_workflows = models.BooleanField(default=False)
    can_manage_members = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class GroupMembership(models.Model):
    """
    Links users to groups with specific roles.
    A user can have multiple roles in multiple groups.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT)

    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date"]
        unique_together = [["user", "group", "role", "start_date"]]

    def __str__(self):
        return f"{self.user} - {self.role} in {self.group}"


# ============================================================================
# WORKFLOW ENGINE MODELS
# ============================================================================


class WorkflowType(models.Model):
    """
    Types of workflows: Bill, Motion, Question, Report, Event, etc.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    # JSON schema for workflow-specific fields
    json_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON schema defining additional fields for this workflow type",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class State(models.Model):
    """
    Workflow states: Draft, Submitted, Under Review, Approved, Rejected, etc.
    """

    workflow_type = models.ForeignKey(
        WorkflowType, on_delete=models.CASCADE, related_name="states"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    # State properties
    is_initial = models.BooleanField(
        default=False, help_text="Is this the initial state?"
    )
    is_terminal = models.BooleanField(default=False, help_text="Is this a final state?")

    # Ordering for display
    order = models.IntegerField(default=0)

    # Visual properties
    color = models.CharField(
        max_length=7, default="#6B7280", help_text="Hex color code"
    )

    class Meta:
        ordering = ["workflow_type", "order", "name"]
        unique_together = [["workflow_type", "name"]]

    def __str__(self):
        return f"{self.workflow_type.name} - {self.name}"


class Transition(models.Model):
    """
    Defines allowed transitions between workflow states.
    """

    workflow_type = models.ForeignKey(
        WorkflowType, on_delete=models.CASCADE, related_name="transitions"
    )
    name = models.CharField(max_length=100)
    from_state = models.ForeignKey(
        State, on_delete=models.CASCADE, related_name="transitions_from"
    )
    to_state = models.ForeignKey(
        State, on_delete=models.CASCADE, related_name="transitions_to"
    )

    # Permissions
    allowed_roles = models.ManyToManyField(Role, related_name="allowed_transitions")

    # Transition properties
    requires_comment = models.BooleanField(default=False)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["workflow_type", "order", "name"]
        unique_together = [["workflow_type", "from_state", "to_state"]]

    def __str__(self):
        return f"{self.name}: {self.from_state.name} → {self.to_state.name}"


class Facet(models.Model):
    """
    Facets define bundled permissions for workflow states.
    They control visibility and actions based on state.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    # Permissions
    allowed_roles = models.ManyToManyField(Role, related_name="facets")

    # What can be done with this facet
    can_view = models.BooleanField(default=True)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class StateFacet(models.Model):
    """
    Links states to facets - defines who can see/interact with workflows in specific states.
    """

    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="facets")
    facet = models.ForeignKey(Facet, on_delete=models.CASCADE)

    class Meta:
        unique_together = [["state", "facet"]]

    def __str__(self):
        return f"{self.state} - {self.facet}"


class Workflow(models.Model):
    """
    Generic workflow instance.
    Can represent Bills, Motions, Questions, Events, etc.
    """

    workflow_type = models.ForeignKey(WorkflowType, on_delete=models.PROTECT)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)

    # Current state
    current_state = models.ForeignKey(
        State, on_delete=models.PROTECT, related_name="workflows"
    )

    # Ownership and assignment
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="workflows")
    owner = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="owned_workflows"
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_workflows",
    )

    # Referral system
    referred_to = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referred_workflows",
        help_text="Group this workflow is referred to",
    )

    # Workflow-specific data stored as JSON
    data = models.JSONField(
        default=dict, blank=True, help_text="Workflow-specific attributes"
    )

    # Deadlines and monitoring
    deadline = models.DateTimeField(null=True, blank=True)
    priority = models.CharField(
        max_length=20,
        choices=[
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("urgent", "Urgent"),
        ],
        default="medium",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workflow_type", "current_state"]),
            models.Index(fields=["group", "current_state"]),
            models.Index(fields=["deadline"]),
        ]

    def __str__(self):
        return f"{self.workflow_type.name}: {self.title}"

    def get_available_transitions(self, user):
        """Get transitions available to a user from current state"""
        # Get user's roles in the workflow's group
        user_roles = user.memberships.filter(
            group=self.group, is_active=True
        ).values_list("role", flat=True)

        # Also check referred_to group if exists
        if self.referred_to:
            referred_roles = user.memberships.filter(
                group=self.referred_to, is_active=True
            ).values_list("role", flat=True)
            user_roles = list(user_roles) + list(referred_roles)

        # Get transitions from current state that user can perform
        return Transition.objects.filter(
            workflow_type=self.workflow_type,
            from_state=self.current_state,
            allowed_roles__in=user_roles,
        ).distinct()

    def can_user_view(self, user):
        """Check if user can view this workflow"""
        # Check if user is in the workflow's group or referred group
        user_groups = user.memberships.filter(is_active=True).values_list(
            "group", flat=True
        )

        if self.group_id in user_groups or (
            self.referred_to_id and self.referred_to_id in user_groups
        ):
            # Check facet permissions for current state
            state_facets = self.current_state.facets.all()
            if not state_facets.exists():
                return True  # No facets = visible to all group members

            user_roles = user.memberships.filter(
                group__in=[self.group_id, self.referred_to_id], is_active=True
            ).values_list("role", flat=True)

            return state_facets.filter(
                facet__allowed_roles__in=user_roles, facet__can_view=True
            ).exists()

        return False

    def is_overdue(self):
        """Check if workflow is past deadline"""
        if self.deadline:
            return timezone.now() > self.deadline
        return False


# ============================================================================
# AUDIT & HISTORY MODELS
# ============================================================================


class WorkflowTransitionLog(models.Model):
    """
    Audit log for workflow state transitions.
    """

    workflow = models.ForeignKey(
        Workflow, on_delete=models.CASCADE, related_name="transition_logs"
    )
    transition = models.ForeignKey(Transition, on_delete=models.PROTECT)
    from_state = models.ForeignKey(
        State, on_delete=models.PROTECT, related_name="transition_logs_from"
    )
    to_state = models.ForeignKey(
        State, on_delete=models.PROTECT, related_name="transition_logs_to"
    )

    user = models.ForeignKey(User, on_delete=models.PROTECT)
    comment = models.TextField(blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.workflow} - {self.transition.name} by {self.user} at {self.timestamp}"


class AuditLog(models.Model):
    """
    Generic audit log for CRUD operations on any model.
    """

    ACTION_CHOICES = [
        ("create", "Create"),
        ("update", "Update"),
        ("delete", "Delete"),
        ("view", "View"),
    ]

    # Generic foreign key to any model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    # What changed
    changes = models.JSONField(default=dict, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["user", "timestamp"]),
        ]

    def __str__(self):
        return (
            f"{self.action} on {self.content_type} by {self.user} at {self.timestamp}"
        )


# ============================================================================
# EVENT MANAGEMENT MODELS
# ============================================================================


class EventType(models.Model):
    """
    Types of events: Plenary, Committee Meeting, Briefing, etc.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Venue(models.Model):
    """
    Venues where events take place.
    """

    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    capacity = models.IntegerField(null=True, blank=True)
    facilities = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Event(models.Model):
    """
    Events as workflows - Plenary sessions, meetings, briefings, etc.
    """

    # Link to workflow system
    workflow = models.OneToOneField(
        Workflow, on_delete=models.CASCADE, related_name="event", null=True, blank=True
    )

    event_type = models.ForeignKey(EventType, on_delete=models.PROTECT)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)

    # Event details
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="events")
    venue = models.ForeignKey(Venue, on_delete=models.PROTECT, null=True, blank=True)

    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()

    # Event status
    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("postponed", "Postponed"),
    ]
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="scheduled"
    )

    # Organizer
    organizer = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="organized_events"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_datetime"]

    def __str__(self):
        return f"{self.event_type.name}: {self.title}"


class EventAttendance(models.Model):
    """
    Track attendance for events.
    """

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="attendances"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="event_attendances"
    )

    ATTENDANCE_CHOICES = [
        ("invited", "Invited"),
        ("confirmed", "Confirmed"),
        ("attended", "Attended"),
        ("absent", "Absent"),
        ("apology", "Apology"),
    ]
    status = models.CharField(
        max_length=20, choices=ATTENDANCE_CHOICES, default="invited"
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["event", "user"]]
        ordering = ["event", "user"]

    def __str__(self):
        return f"{self.user} - {self.event} ({self.status})"


# ============================================================================
# NOTIFICATION & COMMENT MODELS (Optional)
# ============================================================================


class Notification(models.Model):
    """
    Notifications for users about workflow changes, deadlines, etc.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )

    title = models.CharField(max_length=255)
    message = models.TextField()

    # Link to related object
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification for {self.user}: {self.title}"


class Comment(models.Model):
    """
    Comments on workflows.
    """

    workflow = models.ForeignKey(
        Workflow, on_delete=models.CASCADE, related_name="comments"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    text = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.user} on {self.workflow}"
