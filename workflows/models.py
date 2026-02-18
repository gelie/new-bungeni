import base64
import datetime
import hashlib
import hmac
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

    title = models.CharField(max_length=10, choices=TITLE_CHOICES, blank=True)
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
    ]

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
    """

    name = models.CharField(max_length=100, unique=True)
    slug = AutoSlugField(populate_from="name", unique=True, db_index=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return str(self.name)

    def get_absolute_url(self):
        return reverse("bungeni:role_detail", kwargs={"slug": self.slug})


class GroupMembership(models.Model):
    """
    Links users to groups with specific roles.
    A user can have multiple roles in multiple groups.
    """

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
        if not self.create_roles.exists():
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

    # Ordering for display
    order = models.IntegerField(default=0)  # type: ignore

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


class Facet(models.Model):
    """
    Facets define bundled permissions for workflow states.
    They control visibility and actions based on state.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    # Permissions encapsulated with roles
    view_roles = models.ManyToManyField(
        Role, related_name="viewable_facets", blank=True
    )
    edit_roles = models.ManyToManyField(
        Role, related_name="editable_facets", blank=True
    )
    delete_roles = models.ManyToManyField(
        Role, related_name="deletable_facets", blank=True
    )
    transition_roles = models.ManyToManyField(
        Role, related_name="transitionable_facets", blank=True
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return str(self.name)


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

    # Parent-child workflow relationships
    parent_workflow = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sub_workflows",
        help_text="Parent workflow (e.g., International Report for Resolutions)",
    )

    # Optional: Add a field to indicate the relationship type
    relationship_type = models.CharField(
        max_length=50,
        choices=[
            ("resolution", "Resolution"),
            ("amendment", "Amendment"),
            ("follow_up", "Follow-up Action"),
            ("supplement", "Supplementary Document"),
            ("correction", "Correction/Erratum"),
        ],
        null=True,
        blank=True,
        help_text="Type of relationship to parent workflow",
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
                f" ({self.relationship_type})" if self.relationship_type else ""
            )
            return f"{prefix}└─ {self.workflow_type.name}: {self.title}{relationship}"
        return f"{self.workflow_type.name}: {self.title}"

    def get_available_transitions(self, user):
        """Get transitions available to a user from current state"""
        # Get user's roles in the workflow's group
        user_roles = user.memberships.filter(
            group=self.effective_group, is_active=True
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

        if self.effective_group.id in user_groups or (
            self.referred_to and self.referred_to.id in user_groups
        ):
            # Owners can always view their own workflows
            # if self.owner == user:
            #     return True

            # Check facet permissions for current state
            state_facets = self.current_state.facets.all()
            if not state_facets.exists():
                return True  # No facets = visible to all group members

            user_roles = user.memberships.filter(
                group__in=[self.effective_group, self.referred_to]
                if self.referred_to
                else [self.effective_group],
                is_active=True,
            ).values_list("role", flat=True)

            for state_facet in state_facets:
                facet = state_facet.facet
                if (
                    facet.view_roles.exists()
                    and facet.view_roles.filter(id__in=user_roles).exists()
                ):
                    return True

            return False

        return False

    def can_user_edit(self, user):
        """Check if user can edit this workflow"""
        # Check if user is in the workflow's group or referred group
        user_groups = user.memberships.filter(is_active=True).values_list(
            "group", flat=True
        )

        if self.effective_group.id in user_groups or (
            self.referred_to and self.referred_to.id in user_groups
        ):
            # Check facet permissions for current state
            state_facets = self.current_state.facets.all()
            if not state_facets.exists():
                return False  # No facets = no edit permission by default

            user_roles = user.memberships.filter(
                group__in=[self.effective_group, self.referred_to]
                if self.referred_to
                else [self.effective_group],
                is_active=True,
            ).values_list("role", flat=True)

            for state_facet in state_facets:
                facet = state_facet.facet
                if (
                    facet.edit_roles.exists()
                    and not facet.edit_roles.filter(id__in=user_roles).exists()
                ):
                    return False

            return True

        return False

    def can_user_delete(self, user):
        """Check if user can delete this workflow"""
        # Check if user is in the workflow's group or referred group
        user_groups = user.memberships.filter(is_active=True).values_list(
            "group", flat=True
        )

        if self.effective_group.id in user_groups or (
            self.referred_to and self.referred_to.id in user_groups
        ):
            # Check facet permissions for current state
            state_facets = self.current_state.facets.all()
            if not state_facets.exists():
                return False  # No facets = no delete permission by default

            user_roles = user.memberships.filter(
                group__in=[self.effective_group, self.referred_to]
                if self.referred_to
                else [self.effective_group],
                is_active=True,
            ).values_list("role", flat=True)

            for state_facet in state_facets:
                facet = state_facet.facet
                if (
                    facet.delete_roles.exists()
                    and not facet.delete_roles.filter(id__in=user_roles).exists()
                ):
                    return False

            return True

        return False

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

        # Check if potential parent is self
        if potential_parent.id == self.id:
            return True

        # Check if potential parent is already a descendant (only for saved instances)
        if self.pk:
            descendants = self.get_all_descendants()
            return potential_parent in descendants

        return False

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

    def can_be_parent_of(self, potential_child_type):
        """Check if this workflow type can be parent of another workflow type"""
        # Define valid parent-child relationships
        valid_relationships = {
            "International Report": ["International Resolution"],
            "Bill": ["Amendment"],
            "Motion": ["Amendment", "Follow-up Action"],
            # Add more as needed
        }

        parent_type = self.workflow_type.name
        return potential_child_type in valid_relationships.get(parent_type, [])

    def create_sub_workflow(self, workflow_type, title, relationship_type, **kwargs):
        """Helper method to create a sub-workflow"""
        if not self.can_be_parent_of(workflow_type.name):
            raise ValueError(
                f"{self.workflow_type.name} cannot be parent of {workflow_type.name}"
            )

        # Inherit some properties from parent if not specified
        defaults = {
            "owner": self.owner,
            "priority": self.priority,
        }
        defaults.update(kwargs)

        return Workflow.objects.create(
            workflow_type=workflow_type,
            title=title,
            parent_workflow=self,
            relationship_type=relationship_type,
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
        return str(self.name)


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
        return str(self.name)


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

    VERB_TRANSITION = "transition"
    VERB_ASSIGNED = "assigned"
    VERB_REFERRED = "referred"
    VERB_COMMENT = "comment"

    VERB_CHOICES = [
        (VERB_TRANSITION, "Transition"),
        (VERB_ASSIGNED, "Assigned"),
        (VERB_REFERRED, "Referred"),
        (VERB_COMMENT, "Comment"),
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
    object_id = models.PositiveIntegerField(null=True, blank=True)
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


# =======================================================================
# Sharepoint Models for Sites and Drives
# =======================================================================


class Site(models.Model):
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
    site = models.ForeignKey(Site, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date_added = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} - {self.site.name}"


class Drive(models.Model):
    site = models.ForeignKey(Site, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    drive_id = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class SharePointToken(models.Model):
    """
    Stores SharePoint Graph API access tokens for application-level authentication.
    """

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


class Attachment(models.Model):
    attachment_type = {
        "response": "Response",
        "document": "Document",
        "petition": "Petition",
    }
    # Generic foreign key to link to any model (Workflow, Event, etc.)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    # Legacy field for backward compatibility
    related_workflow = models.ForeignKey(
        Workflow, on_delete=models.CASCADE, null=True, blank=True
    )

    name = models.CharField(max_length=200)
    drive_id = models.CharField(max_length=200, help_text="SharePoint drive ID")
    item_id = models.CharField(max_length=200, help_text="SharePoint item ID")
    mimetype = models.CharField(
        max_length=200, blank=True, null=True, help_text="MIME type of the file"
    )
    size = models.BigIntegerField(blank=True, null=True, help_text="File size in bytes")
    download_url = models.URLField(
        blank=True, null=True, help_text="SharePoint download URL"
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
        blank=True, null=True, help_text="Direct SharePoint web URL"
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
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["related_workflow"]),
            models.Index(fields=["sharepoint_site", "sharepoint_drive"]),
        ]
