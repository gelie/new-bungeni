import base64
import datetime
import hashlib
import hmac
import logging
import uuid
from typing import Optional

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_extensions.db.fields import AutoSlugField
from mptt.models import MPTTModel, TreeForeignKey

logger = logging.getLogger(__name__)

# ============================================================================
# USER MODEL
# ============================================================================


class User(AbstractUser):
    """
    Custom User model extending Django's AbstractUser.
    Users can be MPs, staff, administrators, etc.
    """

    TITLE_CHOICES = [
        ("mr", _("Mr.")),
        ("ms", _("Ms.")),
        ("mrs", _("Mrs.")),
        ("dr", _("Dr.")),
        ("prof", _("Prof.")),
        ("hon", _("Hon.")),
        ("rt_hon", _("Rt. Hon.")),
    ]

    EMPLOYEE_TYPE_CHOICES = [
        ("staff", _("Staff")),
        ("member", _("Member")),
        ("graduate", _("Graduate")),
    ]

    GENDER_CHOICES = [
        ("male", _("Male")),
        ("female", _("Female")),
        ("other", _("Other")),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    title = models.CharField(max_length=30, choices=TITLE_CHOICES, blank=True)
    middle_name = models.CharField(max_length=100, blank=True)
    employee_type = models.CharField(
        max_length=10, choices=EMPLOYEE_TYPE_CHOICES, blank=True
    )
    positiondesc = models.CharField(max_length=100, blank=True)
    supervisor = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True
    )
    department = models.ForeignKey(
        "Group", on_delete=models.SET_NULL, null=True, blank=True
    )
    date_of_birth = models.DateField(null=True, blank=True)
    idno_encrypted = models.TextField(blank=True)
    idno_hmac = models.CharField(
        max_length=64, unique=True, db_index=True, blank=True, null=True
    )
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    is_mp = models.BooleanField(
        default=False, help_text=_("Is this user a Member of Parliament?")
    )
    is_staff_member = models.BooleanField(
        default=False, help_text=_("Is this user a staff member?")
    )
    constituency = models.CharField(max_length=200, blank=True)
    party_affiliation = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    date_joined_parliament = models.DateField(null=True, blank=True)
    termination_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)  # type: ignore

    class Meta:
        ordering = ["last_name", "first_name"]

    # --- ID number security helpers ---

    @staticmethod
    def _compute_idno_hmac(plain_id: str) -> Optional[str]:
        """Return hex-encoded HMAC-SHA256 of the ID using settings.IDNO_HMAC_KEY."""
        key = getattr(settings, "IDNO_HMAC_KEY", None)
        if not plain_id or not key:
            return None
        if isinstance(key, str):
            key_bytes = key.encode("utf-8")
        else:
            key_bytes = key
        msg = plain_id.encode("utf-8")
        return hmac.new(key_bytes, msg, hashlib.sha256).hexdigest()

    @staticmethod
    def _encrypt_idno(plain_id: str) -> Optional[str]:
        """Encrypt the ID number using Fernet if IDNO_ENC_KEY is configured. Returns base64 text or None."""
        key = getattr(settings, "IDNO_ENC_KEY", None)
        if not plain_id or not key:
            return None
        try:
            # Lazy import to avoid hard dependency during migrations that don't need encryption
            from cryptography.fernet import Fernet

            # Expect key as urlsafe base64 32-byte string; if provided as raw, try to base64-encode
            k = key
            try:
                # Validate length by attempting to construct Fernet
                f = Fernet(k)
            except Exception:
                # Try to base64-url encode raw key
                k = base64.urlsafe_b64encode(key.encode("utf-8"))
                f = Fernet(k)
            token = f.encrypt(plain_id.encode("utf-8"))
            return token.decode("utf-8")
        except Exception:
            # If encryption fails, do not block save; simply skip encryption
            return None

    @staticmethod
    def _decrypt_idno(ciphertext: str) -> Optional[str]:
        key = getattr(settings, "IDNO_ENC_KEY", None)
        if not ciphertext or not key:
            return None
        try:
            from cryptography.fernet import Fernet

            k = key
            try:
                f = Fernet(k)
            except Exception:
                k = base64.urlsafe_b64encode(key.encode("utf-8"))
                f = Fernet(k)
            plain = f.decrypt(ciphertext.encode("utf-8"))
            return plain.decode("utf-8")
        except Exception:
            return None

    def set_idno(self, plain_id: Optional[str]) -> None:
        """Set the user's ID number, computing HMAC and encryption (no plaintext stored)."""
        # HMAC for deterministic lookup/indexing
        h = self._compute_idno_hmac(plain_id or "")
        if h:
            self.idno_hmac = h
        # Encrypted for retrieval when authorized
        enc = self._encrypt_idno(plain_id or "")
        if enc:
            self.idno_encrypted = enc

    def get_idno(self) -> str:
        """Return decrypted ID number if available; otherwise empty string."""
        dec = (
            self._decrypt_idno(self.idno_encrypted)
            if getattr(self, "idno_encrypted", None)
            else None
        )
        if dec:
            return dec
        return ""

    def __str__(self):
        full_name = f"{self.title.title()} {self.first_name} {self.last_name}".strip()
        return full_name if full_name else self.username

    def get_full_name_with_title(self):
        parts = [self.title.title(), self.first_name, self.middle_name, self.last_name]
        return " ".join(part for part in parts if part)

    def get_absolute_url(self):
        return reverse("bungeni:user_detail", kwargs={"pk": self.pk})

    def clean(self):
        if self.date_of_birth and self.date_of_birth > datetime.date.today():
            raise ValidationError(
                {"date_of_birth": "Date of birth cannot be in the future."}
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def get_groups_with_roles(self):
        """Get all groups this user belongs to with their roles"""
        return GroupMembership.objects.filter(user=self).select_related("group", "role")

    def has_role_in_group(self, role_name, group):
        """Check if user has a specific role in a group"""
        return GroupMembership.objects.filter(
            user=self, group=group, role__name=role_name, is_active=True
        ).exists()

    def can_manage_permissions(self):
        """Check if user has manage permissions"""
        return GroupMembership.objects.filter(
            user=self, role__can_manage_permissions=True, is_active=True
        ).exists()
        # user_roles = self.memberships.filter(is_active=True).values_list(
        #     "role", flat=True
        # )
        # roles_with_perm = Role.objects.filter(
        #     id__in=user_roles, can_manage_permissions=True
        # )
        # return roles_with_perm.exists()

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

    GROUP_TYPE_CHOICES = [
        ("legislature", _("Legislature")),
        ("house", _("House")),
        ("portfolio_committee", _("Portfolio Committee")),
        ("select_committee", _("Select Committee")),
        ("special_committee", _("Special Committee")),
        ("public_accounts_committee", _("Public Accounts Committee")),
        ("internal_committee", _("Internal Committee")),
        ("ad_hoc_committee", _("Ad Hoc Committee")),
        ("joint_committee", _("Joint Committee")),
        ("administration", _("Administration")),
        ("office", _("Office")),
        ("division", _("Division")),
        ("section", _("Section")),
        ("business_unit", _("Business Unit")),
        ("party", _("Party")),
        ("executive", _("Executive")),
        ("presidency", _("Presidency")),
        ("ministry", _("Ministry")),
        ("department", _("Department")),
        ("province", _("Province")),
        ("premier", _("Premier")),
        ("delegation", _("Delegation")),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    name = models.CharField(max_length=255)
    slug = AutoSlugField(populate_from="name", unique=True, editable=False)
    short_name = models.CharField(max_length=50, blank=True)
    group_type = models.CharField(max_length=50, choices=GROUP_TYPE_CHOICES)
    parent = TreeForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)  # type: ignore

    # Additional metadata
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    location = models.CharField(max_length=255, blank=True)

    class MPTTMeta:
        order_insertion_by = ["name"]

    class Meta:  # type: ignore
        ordering = ["name"]
        unique_together = [["name", "parent"]]

    def __str__(self):
        return str(self.name)

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

    Workflow Permissions:
    Note: CRUD permissions (view, edit, delete) are now determined by State permissions,
    not Role. This model only retains permissions that are not state-dependent:
    - can_transition_workflows: Default transition permission (overridden by State/Transition)
    - can_create_workflows: Who can create new workflows
    - can_assign_workflows: Who can assign workflows to others
    - can_manage_permissions: Who can manage group access
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = AutoSlugField(populate_from="name", unique=True, db_index=True)
    description = models.TextField(blank=True)

    # Workflow permissions - define what users with this role can do
    # Note: CRUD permissions are now determined by State, not Role
    can_transition_workflows = models.BooleanField(
        default=False,
        help_text="Users with this role can perform state transitions on workflows",
    )
    can_create_workflows = models.BooleanField(
        default=False,
        help_text="Users with this role can create new workflows for their groups",
    )
    can_assign_workflows = models.BooleanField(
        default=False,
        help_text="Users with this role can assign workflows to other users",
    )
    can_manage_permissions = models.BooleanField(
        default=False,
        help_text="Users with this role can grant/revoke workflow access to other groups",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return str(self.name)

    def get_absolute_url(self):
        return reverse("bungeni:role_detail", kwargs={"slug": self.slug})

    def get_workflow_permissions(self):
        """Return a dictionary of workflow permissions for this role."""
        return {
            "can_transition": self.can_transition_workflows,
            "can_create": self.can_create_workflows,
            "can_assign": self.can_assign_workflows,
            "can_manage_permissions": self.can_manage_permissions,
        }


class GroupMembership(models.Model):
    """
    Links users to groups with specific roles.
    A user can have multiple roles in multiple groups.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="members")
    role = models.ForeignKey(Role, on_delete=models.PROTECT)

    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)  # type: ignore

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date"]
        unique_together = [["user", "group", "role", "start_date"]]

    def __str__(self):
        return f"{self.user} - {self.role} in {self.group}"

    def clean(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError("End date cannot be before start date.")


# ============================================================================
# WORKFLOW ENGINE MODELS
# ============================================================================


class WorkflowType(models.Model):
    """
    Types of workflows: Bill, Motion, Question, Report, Event, etc.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = AutoSlugField(populate_from="name", unique=True, db_index=True)
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)

    # Group ownership - all workflows of this type belong to this group
    group = models.ForeignKey(
        Group,
        on_delete=models.PROTECT,
        related_name="workflow_types",
        help_text="The group that owns all workflows of this type",
    )

    create_roles = models.ManyToManyField(Role, related_name="create_workflow_types")

    # JSON schema for workflow-specific fields
    json_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON schema defining additional fields for this workflow type",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return str(self.name)

    def clean(self):
        if self.pk and not self.create_roles.exists():
            raise ValidationError("Create roles cannot be empty.")

        # Validate that create_roles are in group owner roles
        if self.pk:  # Only validate if instance exists
            group_roles = set(self.group_owner_roles())
            create_role_ids = set(self.create_roles.values_list("id", flat=True))
            if not create_role_ids.issubset(group_roles):
                raise ValidationError(
                    "Create roles must be from roles available in the group."
                )

    def group_owner_roles(self):
        return self.group.members.values_list("role", flat=True).distinct()


class State(models.Model):
    """
    Workflow states: Draft, Submitted, Under Review, Approved, Rejected, etc.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    workflow_type = models.ForeignKey(
        WorkflowType, on_delete=models.CASCADE, related_name="states"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    # State properties
    is_initial = models.BooleanField(
        default=False,
        help_text="Is this the initial state?",  # ignore
    )  # type: ignore
    is_terminal = models.BooleanField(default=False, help_text="Is this a final state?")  # type: ignore
    allows_referrals = models.BooleanField(
        default=True,
        help_text="Can workflows in this state be referred to other groups?",
    )  # type: ignore

    # Ordering for display
    order = models.IntegerField(default=0)  # type: ignore

    # Visual properties
    color = models.CharField(
        max_length=7, default="#5b8f22", help_text="Hex color code"
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

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
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

    # Email alert roles - members with these roles will be notified on this transition
    notify_roles = models.ManyToManyField(
        Role,
        related_name="notified_transitions",
        blank=True,
        help_text="Group members with these roles will receive an email alert when this transition occurs",
    )

    # Transition properties
    requires_comment = models.BooleanField(default=False)  # type: ignore
    order = models.IntegerField(default=0)  # type: ignore

    class Meta:
        ordering = ["workflow_type", "order", "name"]
        unique_together = [["workflow_type", "from_state", "to_state"]]

    def __str__(self):
        return f"{self.name}: {self.from_state.name} → {self.to_state.name}"


class WorkflowTypeChildConfig(models.Model):
    """
    Declares which child WorkflowTypes are allowed under a parent WorkflowType,
    and what the relationship is called. Replaces the hardcoded can_be_parent_of dict.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    parent_type = models.ForeignKey(
        WorkflowType,
        on_delete=models.CASCADE,
        related_name="allowed_child_configs",
    )
    child_type = models.ForeignKey(
        WorkflowType,
        on_delete=models.CASCADE,
        related_name="allowed_as_child_of",
    )
    relationship_label = models.CharField(
        max_length=100,
        help_text="Human-readable label for this relationship (e.g. 'Resolution', 'Amendment')",
    )
    relationship_key = AutoSlugField(
        populate_from="relationship_label",
        unique=True,
        editable=False,
        help_text="Slug-like key stored on the child Workflow instance (e.g. 'resolution')",
    )

    class Meta:
        ordering = ["parent_type", "relationship_label"]
        unique_together = [["parent_type", "child_type"]]

    def __str__(self):
        return f"{self.parent_type.name} → {self.child_type.name} ({self.relationship_label})"


class StatePermission(models.Model):
    """
    Direct per-state role permissions. Replaces the Facet/StateFacet indirection.
    One row per state with multiple roles controls what those roles can do in that state.
    Transition permission is handled by both this model and Transition.allowed_roles.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    state = models.ForeignKey(
        State, on_delete=models.CASCADE, related_name="permissions"
    )
    roles = models.ManyToManyField(Role, related_name="state_permissions")
    can_view = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    can_transition = models.BooleanField(
        default=False,
        help_text="Can perform transitions from this state (overrides Transition.allowed_roles if set)",
    )

    class Meta:
        ordering = ["state"]

    def __str__(self):
        perms = ", ".join(
            p
            for p, v in [
                ("view", self.can_view),
                ("edit", self.can_edit),
                ("delete", self.can_delete),
                ("transition", self.can_transition),
            ]
            if v
        )
        return f"{self.state} | {', '.join(role.name for role in self.roles.all())} | [{perms or 'none'}]"


class Workflow(models.Model):
    """
    Generic workflow instance.
    Can represent Bills, Motions, Questions, Events, etc.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    workflow_type = models.ForeignKey(WorkflowType, on_delete=models.PROTECT)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)

    # Current state
    current_state = models.ForeignKey(
        State, on_delete=models.PROTECT, related_name="workflows"
    )

    # Ownership and assignment
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

    # Referral system - now supports multiple referrals
    referred_to_groups = models.ManyToManyField(
        Group,
        blank=True,
        related_name="referred_workflows",
        help_text="Groups this workflow is referred to",
    )

    # Parent-child workflow relationships
    parent_workflow = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sub_workflows",
        help_text="Parent workflow (e.g., International Report for Resolutions)",
    )

    # FK to the predefined child config that describes this relationship
    relationship_type = models.ForeignKey(
        "WorkflowTypeChildConfig",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_instances",
        help_text="Predefined relationship type to parent workflow",
    )

    # Event association
    event = models.ForeignKey(
        "Event",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="workflows",
        help_text="Event this workflow is associated with",
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
    attachments = models.ManyToManyField("Attachment", blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workflow_type", "current_state"]),
            models.Index(fields=["deadline"]),
            models.Index(fields=["parent_workflow"]),
        ]
        constraints = [
            # Prevent workflows from being their own parent (direct or indirect)
            models.CheckConstraint(
                condition=~models.Q(id=models.F("parent_workflow_id")),
                name="workflow_not_self_parent",
            ),
        ]

    def __str__(self):
        if self.parent_workflow:
            prefix = "  " * self.hierarchy_level
            relationship = (
                f" ({self.relationship_type.relationship_label})"
                if self.relationship_type
                else ""
            )
            return f"{prefix}└─ {self.workflow_type.name}: {self.title}{relationship}"
        return f"{self.workflow_type.name}: {self.title}"

    @property
    def is_overdue(self):
        """Check if workflow is past deadline"""
        if self.deadline:
            return timezone.now() > self.deadline
        return False

    def clean(self):
        """Validate workflow to prevent circular references"""
        from django.core.exceptions import ValidationError

        super().clean()

        if self.parent_workflow:
            # Prevent workflow from being its own ancestor
            if self._would_create_circular_reference(self.parent_workflow):
                raise ValidationError(
                    "Circular reference detected in workflow hierarchy."
                )

    def _would_create_circular_reference(self, potential_parent):
        """Check if setting potential_parent would create a circular reference"""
        if not potential_parent:
            return False

        # Check if potential parent is self (compare objects, not IDs)
        if self.pk and potential_parent.pk and self.pk == potential_parent.pk:
            return True

        # Check if potential parent is already a descendant (only for saved instances)
        if self.pk:
            descendants = self.get_all_descendants()
            return potential_parent in descendants

        return False
        # if not potential_parent:
        #     return False

        # # Check if potential parent is self
        # if potential_parent.id == self.id:
        #     return True

        # # Check if potential parent is already a descendant (only for saved instances)
        # if self.pk:
        #     descendants = self.get_all_descendants()
        #     return potential_parent in descendants

        # return False

    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.clean()
        super().save(*args, **kwargs)

    def get_root_workflow(self):
        """Get the root parent workflow (top of the hierarchy)"""
        current = self
        while current.parent_workflow:
            current = current.parent_workflow
        return current

    def get_all_descendants(self):
        """Get all descendant workflows recursively"""
        descendants = []
        for sub_workflow in self.sub_workflows.all():
            descendants.append(sub_workflow)
            descendants.extend(sub_workflow.get_all_descendants())
        return descendants

    def get_workflow_hierarchy_path(self):
        """Get the full path from root to this workflow"""
        path = []
        current = self
        while current:
            path.insert(0, current)
            current = current.parent_workflow
        return path

    def get_child_config(self, child_workflow_type):
        """Return the WorkflowTypeChildConfig for a given child type, or None."""
        return self.workflow_type.allowed_child_configs.filter(
            child_type=child_workflow_type
        ).first()

    def can_be_parent_of(self, child_workflow_type):
        """Check if this workflow's type allows the given WorkflowType as a child."""
        return self.workflow_type.allowed_child_configs.filter(
            child_type=child_workflow_type
        ).exists()

    def create_sub_workflow(self, child_workflow_type, title, **kwargs):
        """Helper method to create a sub-workflow using a predefined child config."""
        config = self.get_child_config(child_workflow_type)
        if not config:
            raise ValueError(
                f"{self.workflow_type.name} cannot be parent of {child_workflow_type.name}"
            )

        defaults = {
            "owner": self.owner,
            "priority": self.priority,
        }
        defaults.update(kwargs)

        return Workflow.objects.create(
            workflow_type=child_workflow_type,
            title=title,
            parent_workflow=self,
            relationship_type=config,
            **defaults,
        )

    @property
    def hierarchy_level(self):
        """Get the depth level in the hierarchy (0 for root)"""
        level = 0
        current = self.parent_workflow
        while current:
            level += 1
            current = current.parent_workflow
        return level

    @property
    def is_root_workflow(self):
        """Check if this is a root workflow (has no parent)"""
        return self.parent_workflow is None

    @property
    def has_sub_workflows(self):
        """Check if this workflow has any sub-workflows"""
        return self.sub_workflows.exists()

    @property
    def effective_group(self):
        """Get the effective group: workflow's group or type's group"""
        return self.workflow_type.group

    @property
    def active_referrals(self):
        """Return all currently active WorkflowReferrals."""
        return self.referrals.filter(recalled_at__isnull=True).order_by("-referred_at")

    @property
    def active_referral(self):
        """Return the most recent active WorkflowReferral, or None (for backward compatibility)."""
        return self.active_referrals.first()

    @property
    def is_referred(self):
        """Check if workflow has any active referrals."""
        return self.active_referrals.exists()

    @property
    def referral_deadline(self):
        """Get the earliest deadline among active referrals, or None if no deadlines."""
        return (
            self.active_referrals.filter(deadline__isnull=False)
            .order_by("deadline")
            .first()
            .deadline
            if self.active_referrals.filter(deadline__isnull=False).exists()
            else None
        )

    def get_available_transitions(self, user):
        """Get transitions available to a user from current state"""

        user_roles = []

        # Check RBAC WorkflowGroupAccess first
        if self.group_access.exists():
            # Get user's roles in groups that have access to this workflow
            user_memberships = user.memberships.filter(is_active=True).select_related(
                "role", "group"
            )
            accessible_groups = self.group_access.filter(
                group__in=user_memberships.values_list("group", flat=True)
            )

            for group_access in accessible_groups:
                # Get user's roles in this specific group
                roles_in_group = user_memberships.filter(
                    group=group_access.group
                ).values_list("role", flat=True)
                user_roles.extend(roles_in_group)
        else:
            # Fallback to legacy system: check effective_group
            user_roles = list(
                user.memberships.filter(
                    group=self.effective_group, is_active=True
                ).values_list("role", flat=True)
            )

        # Referred groups: allow all roles in any referred group (no config dependency)
        for referred_group in self.referred_to_groups.all():
            referred_user_roles = list(
                user.memberships.filter(
                    group=referred_group,
                    is_active=True,
                ).values_list("role", flat=True)
            )
            user_roles = user_roles + referred_user_roles

        # If workflow has active referrals, block owner from making transitions
        # but allow referred group members to proceed
        if self.is_referred:
            # Check if user is the workflow owner
            if user == self.owner:
                # Owner can only recall referrals, not make other transitions
                return Transition.objects.none()
            # If not owner, proceed with normal permission checks (referred group members can transition)

        return Transition.objects.filter(
            workflow_type=self.workflow_type,
            from_state=self.current_state,
            allowed_roles__in=user_roles,
        ).distinct()

    def _user_roles_for_workflow(self, user):
        """Return queryset of role IDs the user holds in this workflow's relevant groups."""
        groups = [self.effective_group]
        groups.extend(self.referred_to_groups.all())
        return user.memberships.filter(group__in=groups, is_active=True).values_list(
            "role", flat=True
        )

    def _user_in_workflow_groups(self, user):
        """Return True if the user is a member of the workflow's group or any referred group."""
        user_groups = user.memberships.filter(is_active=True).values_list(
            "group", flat=True
        )
        referred_group_ids = list(self.referred_to_groups.values_list("id", flat=True))
        return self.effective_group.id in user_groups or (
            any(group_id in user_groups for group_id in referred_group_ids)
        )

    def _check_rbac_permission(self, user, permission_type):
        """
        Check RBAC permissions using Role-based system.
        permission_type: 'view', 'edit', 'delete', 'transition', 'assign', or 'manage_permissions'
        Returns True if user has the specified permission.

        Permission hierarchy:
        1. Check if workflow owner (always has full permissions except manage_permissions)
        2. Check WorkflowRolePermission overrides (if configured for this workflow)
        3. Check State permissions for CRUD operations
        4. Check Role's default workflow permissions (non-CRUD only)
        5. Fallback to WorkflowGroupAccess group-level permissions (legacy)
        """
        # Owner always has full permissions (except manage_permissions which is role-based)
        if user == self.owner and permission_type != "manage_permissions":
            return True

        # Get all group access records for this workflow where user is a member
        user_memberships = user.memberships.filter(is_active=True).select_related(
            "role", "group"
        )
        accessible_groups = self.group_access.filter(
            group__in=user_memberships.values_list("group", flat=True)
        ).prefetch_related("role_permissions")

        for group_access in accessible_groups:
            # Get user's memberships in this specific group
            memberships_in_group = user_memberships.filter(group=group_access.group)

            for membership in memberships_in_group:
                role = membership.role

                # 1. Check WorkflowRolePermission overrides first (workflow-specific)
                role_perm = group_access.role_permissions.filter(role=role).first()
                if role_perm:
                    # If state-specific permissions are defined, check current state
                    if role_perm.allowed_states.exists():
                        if self.current_state not in role_perm.allowed_states.all():
                            continue

                    # Check the specific permission from override
                    if permission_type == "view" and role_perm.can_view:
                        return True
                    elif permission_type == "edit" and role_perm.can_edit:
                        return True
                    elif permission_type == "delete" and role_perm.can_delete:
                        return True
                    elif permission_type == "transition" and role_perm.can_transition:
                        return True
                    elif permission_type == "assign" and role_perm.can_assign:
                        return True
                    continue  # Override exists, don't check role defaults

                # 2. For CRUD permissions, check State permissions (not Role defaults)
                if permission_type in ["view", "edit", "delete", "transition"]:
                    state_perm = self.current_state.permissions.filter(
                        roles=role
                    ).first()
                    if state_perm:
                        if permission_type == "view" and state_perm.can_view:
                            return True
                        elif permission_type == "edit" and state_perm.can_edit:
                            return True
                        elif permission_type == "delete" and state_perm.can_delete:
                            return True
                        elif (
                            permission_type == "transition"
                            and state_perm.can_transition
                        ):
                            return True
                    # For transition, also check Transition.allowed_roles as fallback
                    elif permission_type == "transition":
                        if Transition.objects.filter(
                            workflow_type=self.workflow_type,
                            from_state=self.current_state,
                            allowed_roles=role,
                        ).exists():
                            return True
                    continue  # State permission checked, don't check role defaults for CRUD

                # 3. Check Role's default workflow permissions (non-CRUD only)
                if permission_type == "transition" and role.can_transition_workflows:
                    return True
                elif permission_type == "assign" and role.can_assign_workflows:
                    return True
                elif (
                    permission_type == "manage_permissions"
                    and role.can_manage_permissions
                ):
                    return True

        return False

    def can_user_view(self, user):
        """Check if user can view this workflow using RBAC system."""
        if user.is_superuser:
            return True

        # Check new RBAC system first
        if self.group_access.exists():
            if self._check_rbac_permission(user, "view"):
                return True

        # Fallback to legacy permission system for backward compatibility
        if not self._user_in_workflow_groups(user):
            return False

        # Members of any referred group always get view access
        for referred_group in self.referred_to_groups.all():
            referred_member = user.memberships.filter(
                group=referred_group, is_active=True
            ).exists()
            if referred_member:
                return True

        # Check state permissions only (no role fallback)
        user_roles = self._user_roles_for_workflow(user)
        state_perms = self.current_state.permissions.filter(roles__in=user_roles)
        return state_perms.filter(can_view=True).exists()

    def can_user_edit(self, user):
        """Check if user can edit this workflow using RBAC system."""
        if user.is_superuser:
            return True

        # Check new RBAC system first
        if self.group_access.exists():
            if self._check_rbac_permission(user, "edit"):
                return True

        # Fallback to legacy permission system
        if not self._user_in_workflow_groups(user):
            return False

        # Members of any referred group get edit access (no config dependency)
        for referred_group in self.referred_to_groups.all():
            in_referred = user.memberships.filter(
                group=referred_group, is_active=True
            ).exists()
            if in_referred:
                return True

        # Check state permissions only (no role fallback)
        user_roles = self._user_roles_for_workflow(user)
        state_perms = self.current_state.permissions.filter(roles__in=user_roles)
        return state_perms.filter(can_edit=True).exists()

    def can_user_delete(self, user):
        """Check if user can delete this workflow using RBAC system."""
        if user.is_superuser:
            return True

        # Check new RBAC system first
        if self.group_access.exists():
            if self._check_rbac_permission(user, "delete"):
                return True

        # Fallback to legacy permission system
        if not self._user_in_workflow_groups(user):
            return False

        # Check state permissions only (no role fallback)
        user_roles = self._user_roles_for_workflow(user)
        state_perms = self.current_state.permissions.filter(roles__in=user_roles)
        return state_perms.filter(can_delete=True).exists()

    def get_accessible_groups(self):
        """Get all groups that have access to this workflow."""
        return Group.objects.filter(workflow_access__workflow=self).distinct()

    def add_group_access(self, group, is_primary=False, granted_by=None, notes=""):
        """
        Helper method to add group access to this workflow.

        NOTE: Permissions are now determined by the user's Role within the group.
        This method only grants ACCESS to the workflow for the group.
        Use WorkflowRolePermission to override Role defaults if needed.

        Returns the created WorkflowGroupAccess instance.
        """
        from workflows.models import WorkflowGroupAccess

        access, created = WorkflowGroupAccess.objects.get_or_create(
            workflow=self,
            group=group,
            defaults={
                "is_primary": is_primary,
                "granted_by": granted_by,
                "notes": notes,
            },
        )

        if not created:
            # Update existing access metadata
            access.is_primary = is_primary
            if granted_by:
                access.granted_by = granted_by
            if notes:
                access.notes = notes
            access.save()

        return access

    def can_user_assign(self, user):
        """Check if user can assign this workflow to other users."""
        if user.is_superuser or user == self.owner:
            return True
        return self._check_rbac_permission(user, "assign")

    def can_user_manage_permissions(self, user):
        """Check if user can grant/revoke group access to this workflow."""
        if user.is_superuser:
            return True
        return self._check_rbac_permission(user, "manage_permissions")


# ============================================================================
# REFERRAL MODELS
# ============================================================================


class WorkflowTypeReferralConfig(models.Model):
    """
    Declares which groups a WorkflowType can be dynamically referred to,
    and which roles in the referred group are allowed to perform transitions
    or edit the workflow while it is referred.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    workflow_type = models.ForeignKey(
        WorkflowType,
        on_delete=models.CASCADE,
        related_name="referral_configs",
    )
    target_group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="referral_configs_as_target",
        help_text="Group that workflows of this type can be referred to",
    )
    label = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional label for this referral route (e.g. 'For comment', 'For decision')",
    )
    # Roles in the referred group that may perform transitions
    referred_transition_roles = models.ManyToManyField(
        Role,
        related_name="referral_transition_configs",
        blank=True,
        help_text="Roles in the referred group allowed to perform transitions",
    )
    # Roles in the referred group that may edit the workflow
    referred_edit_roles = models.ManyToManyField(
        Role,
        related_name="referral_edit_configs",
        blank=True,
        help_text="Roles in the referred group allowed to edit the workflow",
    )

    class Meta:
        ordering = ["workflow_type", "target_group"]
        unique_together = [["workflow_type", "target_group"]]

    def __str__(self):
        label = f" ({self.label})" if self.label else ""
        return f"{self.workflow_type.name} → {self.target_group.name}{label}"


class WorkflowReferral(models.Model):
    """
    Records each referral of a workflow to another group, with full history.
    The currently active referral (recalled_at=None) drives the permission system.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name="referrals",
    )
    referred_to = models.ForeignKey(
        Group,
        on_delete=models.PROTECT,
        related_name="received_referrals",
    )
    config = models.ForeignKey(
        WorkflowTypeReferralConfig,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referral_instances",
        help_text="The referral config that governs permissions for this referral (deprecated)",
    )
    reason = models.TextField(blank=True, help_text="Reason for the referral")
    deadline = models.DateTimeField(
        null=True, blank=True, help_text="Deadline for referral response (optional)"
    )
    deadline_notified = models.BooleanField(
        default=False, help_text="Whether deadline notifications have been sent"
    )
    referred_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="referrals_made",
    )
    referred_at = models.DateTimeField(auto_now_add=True)

    # Recall fields
    recalled_at = models.DateTimeField(null=True, blank=True)
    recalled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referrals_recalled",
    )
    recall_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-referred_at"]

    def __str__(self):
        status = "active" if self.recalled_at is None else "recalled"
        return f"{self.workflow} → {self.referred_to.name} [{status}]"

    @property
    def is_active(self):
        return self.recalled_at is None

    def save(self, *args, **kwargs):
        """Override save to update workflow's referred_to_groups when referral is active."""
        super().save(*args, **kwargs)

        # Update the workflow's referred_to_groups based on active referrals
        if self.is_active:
            self.workflow.referred_to_groups.add(self.referred_to)
        else:
            # If this referral is recalled, check if there are other active referrals to this group
            other_active = (
                self.workflow.referrals.filter(
                    referred_to=self.referred_to, recalled_at__isnull=True
                )
                .exclude(id=self.id)
                .exists()
            )
            if not other_active:
                self.workflow.referred_to_groups.remove(self.referred_to)


# ============================================================================
# WORKFLOW PERMISSION MODELS (RBAC)
# ============================================================================


class WorkflowGroupAccess(models.Model):
    """
    Defines which groups have access to a specific workflow instance.
    This decouples workflow access from WorkflowType, allowing instance-level
    group assignment and multi-group access.

    NOTE: Actual permissions are determined by the user's Role within the group.
    This model only tracks WHICH groups have access, not WHAT they can do.
    Use WorkflowRolePermission to override Role defaults for specific workflows.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name="group_access",
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="workflow_access",
    )

    # Track if this was inherited from WorkflowType default or explicitly set
    is_primary = models.BooleanField(
        default=False, help_text="Primary owning group (typically selected at creation)"
    )
    inherited_from_type = models.BooleanField(
        default=False,
        help_text="Access was inherited from WorkflowType configuration (legacy)",
    )

    # Metadata
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_workflow_access",
        help_text="User who granted this access",
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-is_primary", "group__name"]
        unique_together = [["workflow", "group"]]
        indexes = [
            models.Index(fields=["workflow", "group"]),
            models.Index(fields=["group"]),
        ]

    def __str__(self):
        primary = " [PRIMARY]" if self.is_primary else ""
        return f"{self.workflow.title} → {self.group.name}{primary}"

    def get_role_permissions_summary(self):
        """Get a summary of which roles have which permissions for this group access."""
        from collections import defaultdict

        summary = defaultdict(list)

        # Get all role permissions configured for this workflow
        for role_perm in self.role_permissions.all():
            perms = []
            if role_perm.can_view:
                perms.append("view")
            if role_perm.can_edit:
                perms.append("edit")
            if role_perm.can_delete:
                perms.append("delete")
            if role_perm.can_transition:
                perms.append("transition")
            summary[role_perm.role.name] = perms

        return dict(summary)


class WorkflowRolePermission(models.Model):
    """
    Fine-grained role-based permissions within a group's access to a workflow.
    This allows specific roles within a group to have different permission levels.

    If no role permissions are defined for a WorkflowGroupAccess, the group-level
    permissions apply to all roles. If role permissions exist, they override
    the group-level defaults for those specific roles.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    group_access = models.ForeignKey(
        WorkflowGroupAccess,
        on_delete=models.CASCADE,
        related_name="role_permissions",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="workflow_permissions",
    )

    # Override permissions for this specific role
    can_view = models.BooleanField(default=True)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    can_transition = models.BooleanField(default=False)

    # State-specific permissions (optional, overrides state permissions)
    allowed_states = models.ManyToManyField(
        State,
        blank=True,
        related_name="role_workflow_permissions",
        help_text="If specified, these permissions only apply in these states",
    )

    class Meta:
        ordering = ["role__name"]
        unique_together = [["group_access", "role"]]
        indexes = [
            models.Index(fields=["group_access", "role"]),
        ]

    def __str__(self):
        perms = []
        if self.can_view:
            perms.append("view")
        if self.can_edit:
            perms.append("edit")
        if self.can_delete:
            perms.append("delete")
        if self.can_transition:
            perms.append("transition")
        perm_str = ", ".join(perms) if perms else "none"
        return f"{self.group_access.group.name} - {self.role.name}: [{perm_str}]"


# ============================================================================
# AUDIT & HISTORY MODELS
# ============================================================================


class WorkflowTransitionLog(models.Model):
    """
    Audit log for workflow state transitions.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
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
        ("transition", "Transition"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    # Generic foreign key to any model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey("content_type", "object_id")

    action = models.CharField(max_length=12, choices=ACTION_CHOICES)
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

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return str(self.name)


class Building(models.Model):
    """
    Buildings that contain venues.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    name = models.CharField(max_length=255, unique=True)
    address = models.TextField(blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return str(self.name)


class Venue(models.Model):
    """
    Venues where events take place.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    name = models.CharField(max_length=255)
    building = models.ForeignKey(
        Building, on_delete=models.CASCADE, null=True, blank=True, related_name="venues"
    )
    floor = models.CharField(max_length=50, blank=True)
    room_number = models.CharField(max_length=50, blank=True)
    capacity = models.IntegerField(null=True, blank=True)
    facilities = models.TextField(blank=True)

    class Meta:
        ordering = ["building", "floor", "room_number", "name"]

    def __str__(self):
        parts = []
        if self.building:
            parts.append(str(self.building))
        if self.floor:
            parts.append(f"Floor {self.floor}")
        if self.room_number:
            parts.append(f"Room {self.room_number}")
        parts.append(self.name)
        return " - ".join(parts)


class Event(models.Model):
    """
    Events as workflows - Plenary sessions, meetings, briefings, etc.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    # Link to workflow system
    workflow = models.OneToOneField(
        Workflow,
        on_delete=models.CASCADE,
        related_name="event_instance",
        null=True,
        blank=True,
    )

    event_type = models.ForeignKey(EventType, on_delete=models.PROTECT)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)

    # Event details
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="events")
    venue = models.ForeignKey(Venue, on_delete=models.PROTECT, null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
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

    @classmethod
    def update_automatic_statuses(cls):
        """
        Automatically update event statuses based on scheduled times.
        - Transitions 'scheduled' events to 'in_progress' when start_datetime is reached
        - Transitions 'in_progress' events to 'completed' when end_datetime is reached
        Returns a dict with counts of updated events.
        """
        from django.utils import timezone

        now = timezone.now()
        updated = {"to_in_progress": 0, "to_completed": 0}

        # Transition scheduled events to in_progress
        events_to_start = cls.objects.filter(
            status="scheduled", start_datetime__lte=now
        )
        for event in events_to_start:
            event.status = "in_progress"
            event.save()
            updated["to_in_progress"] += 1

        # Transition in_progress events to completed
        events_to_complete = cls.objects.filter(
            status="in_progress", end_datetime__lte=now
        )
        for event in events_to_complete:
            event.status = "completed"
            event.save()
            updated["to_completed"] += 1

        return updated

    def create_attendance_records(self):
        """Create attendance records for all group members when event is completed."""
        from django.db import transaction

        with transaction.atomic():
            # Get all active members of the event's group
            members = self.group.members.filter(is_active=True).select_related("user")

            for membership in members:
                # Create attendance record only if it doesn't exist
                EventAttendance.objects.get_or_create(
                    event=self, user=membership.user, defaults={"status": "invited"}
                )

    def save(self, *args, **kwargs):
        """Override save to create attendance records when status changes to completed."""
        # Check if this is an existing event and status is being changed
        if self.pk:
            old_event = Event.objects.get(pk=self.pk)
            status_changed = old_event.status != self.status
            is_now_completed = self.status == "completed"

            if status_changed and is_now_completed:
                # Create attendance records after saving
                super().save(*args, **kwargs)
                self.create_attendance_records()
                return

        super().save(*args, **kwargs)


class EventAttendance(models.Model):
    """
    Track attendance for events.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
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
# EVENT COMMENT MODEL
# ============================================================================


class EventComment(models.Model):
    """
    Comments on events.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="event_comments"
    )
    message = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        truncated = self.message[:40]
        return f"{self.author} on {self.event}: {truncated}..."


# ============================================================================
# NOTIFICATION & COMMENT MODELS (Optional)
# ============================================================================


class Notification(models.Model):
    """
    Notifications for users about workflow changes, deadlines, etc.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    VERB_TRANSITION = "transition"
    VERB_ASSIGNED = "assigned"
    VERB_REFERRED = "referred"
    VERB_COMMENT = "comment"
    VERB_OVERDUE = "overdue"
    VERB_PENDING = "pending"
    VERB_DELEGATION_CREATED = "delegation_created"
    VERB_DELEGATION_APPROVED = "delegation_approved"
    VERB_DELEGATION_REVOKED = "delegation_revoked"
    VERB_DELEGATION_EXPIRED = "delegation_expired"
    VERB_DEADLINE_WARNING = "deadline_warning"
    VERB_AUTO_RECALL = "auto_recall"

    VERB_CHOICES = [
        (VERB_TRANSITION, "Transition"),
        (VERB_ASSIGNED, "Assigned"),
        (VERB_REFERRED, "Referred"),
        (VERB_COMMENT, "Comment"),
        (VERB_OVERDUE, "Overdue"),
        (VERB_PENDING, "Pending Deadline"),
        (VERB_DELEGATION_CREATED, "Delegation Created"),
        (VERB_DELEGATION_APPROVED, "Delegation Approved"),
        (VERB_DELEGATION_REVOKED, "Delegation Revoked"),
        (VERB_DELEGATION_EXPIRED, "Delegation Expired"),
        (VERB_DEADLINE_WARNING, "Deadline Warning"),
        (VERB_AUTO_RECALL, "Auto Recall"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )

    verb = models.CharField(
        max_length=20, choices=VERB_CHOICES, default=VERB_TRANSITION
    )
    title = models.CharField(max_length=255)
    message = models.TextField()

    # Direct link to the related workflow
    workflow = models.ForeignKey(
        "Workflow",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )

    # Generic FK kept for backward compatibility / other object types
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.CharField(max_length=64, null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    is_read = models.BooleanField(default=False)  # type: ignore
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read"]),
        ]

    def __str__(self):
        return f"Notification for {self.user}: {self.title}"


class Comment(models.Model):
    """
    Comments on workflows.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    workflow = models.ForeignKey(
        Workflow, on_delete=models.CASCADE, related_name="comments"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    text = models.TextField()

    # Optional attachments for comments
    attachments = models.ManyToManyField(
        "Attachment",
        blank=True,
        related_name="comments",
        help_text="Supporting documents attached to this comment",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.user} on {self.workflow}"


# =======================================================================
# Sharepoint Models for Sites and Drives
# =======================================================================


class Site(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    name = models.CharField(max_length=200)
    url = models.URLField()
    site_id = models.CharField(max_length=200)
    is_personal_site = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    # When this record was last refreshed from SharePoint.
    last_synced_at = models.DateTimeField(
        default=timezone.now,
        help_text="When this record was last refreshed from SharePoint.",
    )
    # Timestamp reported by SharePoint (e.g., lastModifiedDateTime).
    remote_modified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The last modified timestamp reported by SharePoint for this site.",
    )

    def __str__(self):
        return self.name


class SiteMember(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date_added = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} - {self.site.name}"

    class Meta:
        unique_together = [["site", "user"]]


class Drive(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    drive_id = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class SharePointToken(models.Model):
    """
    Stores SharePoint Graph API access tokens for application-level authentication.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    access_token = models.TextField(help_text="SharePoint access token")
    refresh_token = models.TextField(blank=True, help_text="SharePoint refresh token")
    expires_at = models.DateTimeField(help_text="Token expiration time")
    is_active = models.BooleanField(
        default=True, help_text="Whether this token is active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Token {'Active' if self.is_active else 'Inactive'} - expires {self.expires_at}"

    def is_expired(self):
        """Check if the token is expired"""
        from django.utils import timezone

        return timezone.now() >= self.expires_at

    class Meta:
        ordering = ["-created_at"]


class SharePointFolder(models.Model):
    """
    Represents a folder hierarchy in SharePoint for navigation.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE)
    drive = models.ForeignKey(Drive, on_delete=models.CASCADE)
    folder_id = models.CharField(max_length=200, help_text="SharePoint folder ID")
    name = models.CharField(max_length=200)
    parent_folder = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="subfolders",
    )
    web_url = models.URLField(
        blank=True, null=True, help_text="Direct URL to folder in SharePoint"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.site.name}"

    def get_full_path(self):
        """Get the full path from root to this folder"""
        if self.parent_folder:
            return f"{self.parent_folder.get_full_path()}/{self.name}"
        return f"/{self.name}"

    class Meta:
        ordering = ["site", "drive", "name"]
        unique_together = [["site", "drive", "folder_id"]]


# =======================================================================
# Attachment Model for Sharepoint documents
# =======================================================================


class UserDelegation(models.Model):
    """
    Delegation of workflow permissions and responsibilities from one user to another.
    Allows a user to delegate their workflow permissions, assignments, and responsibilities
    to another user for a specific period or indefinitely.
    """

    STATUS_CHOICES = [
        ("active", "Active"),
        ("expired", "Expired"),
        ("revoked", "Revoked"),
        ("pending", "Pending"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    # Delegation relationship
    delegator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="delegations_made",
        help_text="User who is delegating their permissions",
    )
    delegatee = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="delegations_received",
        help_text="User who receives the delegated permissions",
    )

    # Delegation scope
    workflows = models.ManyToManyField(
        Workflow,
        blank=True,
        related_name="delegations",
        help_text="Specific workflows this delegation applies to (empty = all workflows)",
    )
    groups = models.ManyToManyField(
        Group,
        blank=True,
        related_name="delegations",
        help_text="Specific groups this delegation applies to (empty = all groups)",
    )

    # Time period
    start_date = models.DateTimeField(
        default=timezone.now,
        help_text="When the delegation becomes effective",
    )
    end_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the delegation expires (null = indefinite)",
    )

    # Delegation properties
    can_view_workflows = models.BooleanField(
        default=True,
        help_text="Delegatee can view delegator's workflows",
    )
    can_edit_workflows = models.BooleanField(
        default=False,
        help_text="Delegatee can edit delegator's workflows",
    )
    can_transition_workflows = models.BooleanField(
        default=False,
        help_text="Delegatee can perform transitions on delegator's workflows",
    )
    can_receive_assignments = models.BooleanField(
        default=True,
        help_text="New workflow assignments to delegator go to delegatee",
    )
    can_receive_notifications = models.BooleanField(
        default=True,
        help_text="Delegatee receives delegator's workflow notifications",
    )

    # Status and metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    reason = models.TextField(blank=True, help_text="Reason for the delegation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Audit fields
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_delegations",
        help_text="User who approved this delegation (if required)",
    )
    approved_at = models.DateTimeField(
        null=True, blank=True, help_text="When this delegation was approved"
    )
    revoked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revoked_delegations",
        help_text="User who revoked this delegation",
    )
    revoked_at = models.DateTimeField(
        null=True, blank=True, help_text="When this delegation was revoked"
    )
    revoke_reason = models.TextField(
        blank=True, help_text="Reason for revoking the delegation"
    )

    class Meta:
        ordering = ["-created_at"]
        unique_together = [["delegator", "delegatee", "start_date"]]
        indexes = [
            models.Index(fields=["delegator", "status"]),
            models.Index(fields=["delegatee", "status"]),
            models.Index(fields=["start_date", "end_date"]),
            models.Index(fields=["status", "end_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__isnull=True)
                | models.Q(end_date__gt=models.F("start_date")),
                name="delegation_end_after_start",
            ),
        ]

    def __str__(self):
        return f"{self.delegator} → {self.delegatee} [{self.status}]"

    def clean(self):
        """Validate delegation constraints"""
        if self.delegator == self.delegatee:
            raise ValidationError("A user cannot delegate to themselves.")

        if self.end_date and self.end_date <= self.start_date:
            raise ValidationError("End date must be after start date.")

    def save(self, *args, **kwargs):
        """Override save to run validation, auto-update status, and send notifications"""
        self.clean()

        # Check if this is a new delegation
        is_new = self.pk is None

        # Auto-update status based on dates
        now = timezone.now()
        if self.end_date and self.end_date <= now and self.status == "active":
            self.status = "expired"
        elif self.start_date <= now and self.status == "pending":
            self.status = "active"

        super().save(*args, **kwargs)

        # Send notifications for new delegations
        if is_new:
            self._notify_delegatee()

    def _notify_delegatee(self):
        """Send notification to delegatee when delegation is created"""
        from .views import _create_notification

        delegator_name = self.delegator.get_full_name() or self.delegator.username
        delegatee_name = self.delegatee.get_full_name() or self.delegatee.username

        # Log delegation creation
        logger.info(
            f"Creating delegation notification: {delegator_name} -> {delegatee_name} "
            f"(ID: {self.pk}, Start: {self.start_date}, End: {self.end_date or 'Indefinite'})"
        )

        # Create in-app notification
        try:
            _create_notification(
                user=self.delegatee,
                verb=Notification.VERB_DELEGATION_CREATED,
                title=f"New delegation from {delegator_name}",
                message=(
                    f"{delegator_name} has delegated workflow permissions to you. "
                    f"Start: {self.start_date.strftime('%Y-%m-%d %H:%M')}"
                    f"{' | End: ' + self.end_date.strftime('%Y-%m-%d %H:%M') if self.end_date else ' (Indefinite)'}"
                    f"{'. Reason: ' + self.reason if self.reason else ''}"
                ),
            )
            logger.info(f"In-app notification created for delegatee {delegatee_name}")
        except Exception as e:
            logger.error(
                f"Failed to create in-app notification for {delegatee_name}: {e}"
            )

        # Send email notification
        try:
            from django.conf import settings
            from django.core.mail import send_mail

            subject = f"Workflow Delegation from {delegator_name}"

            message = f"""
Hello {self.delegatee.get_full_name() or self.delegatee.username},

{delegator_name} has delegated workflow permissions to you with the following details:

Start Date: {self.start_date.strftime("%Y-%m-%d %H:%M")}
End Date: {self.end_date.strftime("%Y-%m-%d %H:%M") if self.end_date else "Indefinite"}

Permissions:
• View Workflows: {"Yes" if self.can_view_workflows else "No"}
• Edit Workflows: {"Yes" if self.can_edit_workflows else "No"}
• Perform Transitions: {"Yes" if self.can_transition_workflows else "No"}
• Receive Assignments: {"Yes" if self.can_receive_assignments else "No"}
• Receive Notifications: {"Yes" if self.can_receive_notifications else "No"}

{f"Reason: {self.reason}" if self.reason else ""}

You can view this delegation in your dashboard.

Best regards,
Workflow Management System
            """.strip()

            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(
                    settings, "DEFAULT_FROM_EMAIL", "noreply@parliament.gov.za"
                ),
                recipient_list=[self.delegatee.email],
                fail_silently=False,
            )

            logger.info(
                f"Delegation email sent to {delegatee_name} at {self.delegatee.email}"
            )

        except Exception as e:
            # Log error but don't fail the delegation creation
            logger.error(
                f"Failed to send delegation email to {self.delegatee.email}: {e}"
            )

    def revoke(self, revoked_by, reason=""):
        """Revoke the delegation and send notifications"""
        delegator_name = self.delegator.get_full_name() or self.delegator.username
        delegatee_name = self.delegatee.get_full_name() or self.delegatee.username
        revoker_name = revoked_by.get_full_name() or revoked_by.username

        # Log revocation
        logger.info(
            f"Revoking delegation: {delegator_name} -> {delegatee_name} "
            f"by {revoker_name} (ID: {self.pk}, Reason: {reason or 'None'})"
        )

        self.status = "revoked"
        self.revoked_by = revoked_by
        self.revoked_at = timezone.now()
        self.revoke_reason = reason
        self.save()

        # Notify delegatee of revocation
        from .views import _create_notification

        try:
            _create_notification(
                user=self.delegatee,
                verb=Notification.VERB_DELEGATION_REVOKED,
                title=f"Delegation revoked by {revoker_name}",
                message=(
                    f"Your delegation from {delegator_name} "
                    f"has been revoked by {revoker_name}."
                    f"{f' Reason: {reason}' if reason else ''}"
                ),
            )
            logger.info(f"Revocation notification created for {delegatee_name}")
        except Exception as e:
            logger.error(
                f"Failed to create revocation notification for {delegatee_name}: {e}"
            )

        # Send email notification for revocation
        try:
            from django.conf import settings
            from django.core.mail import send_mail

            subject = f"Delegation Revoked by {revoker_name}"

            message = f"""
Hello {self.delegatee.get_full_name() or self.delegatee.username},

Your delegation from {delegator_name}
has been revoked by {revoker_name}.

{f"Reason: {reason}" if reason else ""}

You no longer have the delegated workflow permissions.

Best regards,
Workflow Management System
            """.strip()

            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(
                    settings, "DEFAULT_FROM_EMAIL", "noreply@parliament.gov.za"
                ),
                recipient_list=[self.delegatee.email],
                fail_silently=False,
            )

            logger.info(
                f"Revocation email sent to {delegatee_name} at {self.delegatee.email}"
            )

        except Exception as e:
            # Log error but don't fail the revocation
            logger.error(
                f"Failed to send delegation revocation email to {self.delegatee.email}: {e}"
            )

    def expire_delegation(self):
        """Expire the delegation and send notifications"""
        if self.status == "expired":
            return  # Already expired

        delegator_name = self.delegator.get_full_name() or self.delegator.username
        delegatee_name = self.delegatee.get_full_name() or self.delegatee.username

        # Log expiration
        logger.info(
            f"Expiring delegation: {delegator_name} -> {delegatee_name} "
            f"(ID: {self.pk}, End date: {self.end_date})"
        )

        self.status = "expired"
        self.save()

        # Notify delegatee of expiration
        from .views import _create_notification

        try:
            _create_notification(
                user=self.delegatee,
                verb=Notification.VERB_DELEGATION_EXPIRED,
                title="Delegation expired",
                message=(
                    f"Your delegation from {delegator_name} "
                    f"has expired as of {self.end_date.strftime('%Y-%m-%d %H:%M')}. "
                    "You no longer have the delegated workflow permissions."
                ),
            )
            logger.info(f"Expiration notification created for {delegatee_name}")
        except Exception as e:
            logger.error(
                f"Failed to create expiration notification for {delegatee_name}: {e}"
            )

        # Notify delegator of expiration
        try:
            _create_notification(
                user=self.delegator,
                verb=Notification.VERB_DELEGATION_EXPIRED,
                title=f"Delegation to {delegatee_name} expired",
                message=(
                    f"Your delegation to {delegatee_name} "
                    f"has expired as of {self.end_date.strftime('%Y-%m-%d %H:%M')}."
                ),
            )
            logger.info(
                f"Expiration notification created for delegator {delegator_name}"
            )
        except Exception as e:
            logger.error(
                f"Failed to create expiration notification for delegator {delegator_name}: {e}"
            )

        # Send email notifications
        self._send_expiration_emails(delegator_name, delegatee_name)

    def _send_expiration_emails(self, delegator_name, delegatee_name):
        """Send email notifications for delegation expiration"""
        from django.conf import settings
        from django.core.mail import send_mail

        # Email to delegatee
        try:
            subject = f"Delegation Expired - {delegator_name}"

            message = f"""
Hello {self.delegatee.get_full_name() or self.delegatee.username},

Your delegation from {delegator_name} has expired as of {self.end_date.strftime("%Y-%m-%d %H:%M")}.

You no longer have the delegated workflow permissions that were assigned to you.

If you need continued access, please contact {delegator_name} to create a new delegation.

Best regards,
Workflow Management System
            """.strip()

            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(
                    settings, "DEFAULT_FROM_EMAIL", "noreply@parliament.gov.za"
                ),
                recipient_list=[self.delegatee.email],
                fail_silently=False,
            )

            logger.info(
                f"Expiration email sent to delegatee {delegatee_name} at {self.delegatee.email}"
            )

        except Exception as e:
            logger.error(
                f"Failed to send expiration email to delegatee {self.delegatee.email}: {e}"
            )

        # Email to delegator
        try:
            subject = f"Your Delegation to {delegatee_name} Has Expired"

            message = f"""
Hello {delegator_name},

Your delegation to {delegatee_name} has expired as of {self.end_date.strftime("%Y-%m-%d %H:%M")}.

{delegatee_name} no longer has the workflow permissions you delegated to them.

If you need to extend this delegation, please create a new one in the delegation management system.

Best regards,
Workflow Management System
            """.strip()

            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(
                    settings, "DEFAULT_FROM_EMAIL", "noreply@parliament.gov.za"
                ),
                recipient_list=[self.delegator.email],
                fail_silently=False,
            )

            logger.info(
                f"Expiration email sent to delegator {delegator_name} at {self.delegator.email}"
            )

        except Exception as e:
            logger.error(
                f"Failed to send expiration email to delegator {self.delegator.email}: {e}"
            )

    @property
    def is_active(self):
        """Check if delegation is currently active"""
        if self.status != "active":
            return False
        now = timezone.now()
        if self.start_date > now:
            return False
        if self.end_date and now > self.end_date:
            return False
        return True

    @property
    def is_expired(self):
        """Check if delegation has expired"""
        if self.end_date and timezone.now() > self.end_date:
            return True
        return False

    def applies_to_workflow(self, workflow):
        """Check if this delegation applies to a specific workflow"""
        if not self.is_active:
            return False

        # If no specific workflows are defined, applies to all
        if not self.workflows.exists():
            return True

        return self.workflows.filter(id=workflow.id).exists()

    def applies_to_group(self, group):
        """Check if this delegation applies to a specific group"""
        if not self.is_active:
            return False

        # If no specific groups are defined, applies to all
        if not self.groups.exists():
            return True

        return self.groups.filter(id=group.id).exists()

    # def revoke(self, revoked_by, reason=""):
    #     """Revoke this delegation"""
    #     self.status = "revoked"
    #     self.revoked_by = revoked_by
    #     self.revoked_at = timezone.now()
    #     self.revoke_reason = reason
    #     self.save()

    def approve(self, approved_by):
        """Approve this delegation"""
        if self.status == "pending":
            self.status = "active"
            self.approved_by = approved_by
            self.approved_at = timezone.now()
            self.save()


class Attachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    attachment_type = {
        "response": "Response",
        "document": "Document",
        "petition": "Petition",
        "other": "Other",
    }
    # Generic foreign key to link to any model (Workflow, Event, etc.)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.CharField(max_length=64, null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    # Legacy field for backward compatibility
    related_workflow = models.ForeignKey(
        Workflow, on_delete=models.CASCADE, null=True, blank=True
    )

    name = models.CharField(max_length=500)
    drive_id = models.CharField(max_length=512, help_text="SharePoint drive ID")
    item_id = models.CharField(max_length=512, help_text="SharePoint item ID")
    mimetype = models.CharField(
        max_length=512, blank=True, null=True, help_text="MIME type of the file"
    )
    size = models.BigIntegerField(blank=True, null=True, help_text="File size in bytes")
    download_url = models.URLField(
        max_length=2048,
        blank=True,
        null=True,
        help_text="SharePoint download URL",
    )
    # Enhanced SharePoint references
    sharepoint_site = models.ForeignKey(
        Site, on_delete=models.CASCADE, null=True, blank=True
    )
    sharepoint_drive = models.ForeignKey(
        Drive, on_delete=models.CASCADE, null=True, blank=True
    )
    sharepoint_folder = models.ForeignKey(
        SharePointFolder, on_delete=models.CASCADE, null=True, blank=True
    )
    sharepoint_web_url = models.URLField(
        max_length=2048,
        blank=True,
        null=True,
        help_text="Direct SharePoint web URL",
    )
    sharepoint_folder_path = models.CharField(
        max_length=500, blank=True, help_text="Folder path in SharePoint"
    )

    type = models.CharField(max_length=200, choices=attachment_type.items())
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.content_object:
            return f"{self.name} - {self.content_object}"
        return f"{self.name} - {self.related_workflow or 'Unattached'}"

    def get_sharepoint_url(self):
        """Get the direct SharePoint URL for this attachment"""
        return self.sharepoint_web_url or self.download_url

    class Meta:
        ordering = ["-created_at"]
        unique_together = [["related_workflow", "item_id"]]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["related_workflow"]),
            models.Index(fields=["sharepoint_site", "sharepoint_drive"]),
        ]
