from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from mptt.admin import MPTTModelAdmin

from .models import (
    AuditLog,
    Comment,
    Drive,
    Event,
    EventAttendance,
    EventType,
    Group,
    GroupMembership,
    # GroupType,
    Notification,
    Role,
    Site,
    SiteMember,
    State,
    StatePermission,
    Transition,
    User,
    Venue,
    Workflow,
    WorkflowTransitionLog,
    WorkflowType,
    WorkflowTypeChildConfig,
)

# ============================================================================
# USER ADMIN
# ============================================================================


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        "username",
        "email",
        "first_name",
        "last_name",
        "is_active",
        "is_staff",
    ]
    list_filter = ["is_staff", "is_superuser", "is_active", "is_active"]
    search_fields = ["username", "first_name", "last_name", "email"]

    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Parliamentary Info",
            {
                "fields": (
                    "phone",
                    "title",
                    "bio",
                    "avatar",
                    "date_joined_parliament",
                )
            },
        ),
    )


# ============================================================================
# GROUP ADMIN
# ============================================================================


# @admin.register(GroupType)
# class GroupTypeAdmin(admin.ModelAdmin):
#     list_display = ["name", "description"]
#     search_fields = ["name"]


@admin.register(Group)
class GroupAdmin(MPTTModelAdmin):
    list_display = ["name", "group_type", "parent", "is_active", "start_date"]
    list_filter = ["group_type", "is_active"]
    search_fields = ["name", "short_name", "description"]
    mptt_level_indent = 20


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ["name", "description"]
    search_fields = ["name"]


@admin.register(GroupMembership)
class GroupMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "group", "role", "start_date", "is_active"]
    list_filter = ["is_active", "role", "group__group_type"]
    search_fields = [
        "user__username",
        "user__first_name",
        "user__last_name",
        "group__name",
    ]
    autocomplete_fields = ["user", "group", "role"]
    date_hierarchy = "start_date"


# ============================================================================
# WORKFLOW ADMIN
# ============================================================================


class StatePermissionInline(admin.TabularInline):
    model = StatePermission
    extra = 1
    autocomplete_fields = ["role"]
    fields = ["role", "can_view", "can_edit", "can_delete"]


class WorkflowTypeChildConfigInline(admin.TabularInline):
    model = WorkflowTypeChildConfig
    fk_name = "parent_type"
    extra = 1
    autocomplete_fields = ["child_type"]
    fields = ["child_type", "relationship_label"]


@admin.register(WorkflowTypeChildConfig)
class WorkflowTypeChildConfigAdmin(admin.ModelAdmin):
    list_display = [
        "parent_type",
        "child_type",
        "relationship_label",
        "relationship_key",
    ]
    list_filter = ["parent_type"]
    search_fields = ["parent_type__name", "child_type__name", "relationship_label"]
    autocomplete_fields = ["parent_type", "child_type"]


@admin.register(WorkflowType)
class WorkflowTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "description", "group", "enabled"]
    search_fields = ["name"]
    autocomplete_fields = ["group", "create_roles"]
    inlines = [WorkflowTypeChildConfigInline]


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "workflow_type",
        "is_initial",
        "is_terminal",
        "order",
        "color",
    ]
    list_filter = ["workflow_type", "is_initial", "is_terminal"]
    search_fields = ["name"]
    ordering = ["workflow_type", "order"]
    inlines = [StatePermissionInline]


@admin.register(Transition)
class TransitionAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "workflow_type",
        "from_state",
        "to_state",
        "requires_comment",
    ]
    list_filter = ["workflow_type", "requires_comment"]
    search_fields = ["name"]
    filter_horizontal = ["allowed_roles", "notify_roles"]
    autocomplete_fields = ["from_state", "to_state"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name in ["from_state", "to_state"]:
            if request.resolver_match.kwargs.get("object_id"):
                try:
                    transition = self.get_object(
                        request, request.resolver_match.kwargs["object_id"]
                    )
                    if transition and transition.workflow_type:
                        kwargs["queryset"] = State.objects.filter(
                            workflow_type=transition.workflow_type
                        )
                except Exception:
                    pass
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(StatePermission)
class StatePermissionAdmin(admin.ModelAdmin):
    list_display = ["state", "role", "can_view", "can_edit", "can_delete"]
    list_filter = ["state__workflow_type", "can_view", "can_edit", "can_delete"]
    search_fields = ["state__name", "role__name"]
    autocomplete_fields = ["state", "role"]


@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "workflow_type",
        "parent_workflow",
        "relationship_type",
        "current_state",
        "owner",
        "priority",
        "deadline",
        "created_at",
    ]
    list_filter = [
        "workflow_type",
        "current_state",
        "priority",
        "relationship_type",
        ("parent_workflow", admin.RelatedOnlyFieldListFilter),
    ]
    search_fields = ["title", "description"]
    date_hierarchy = "created_at"
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        ("Basic Information", {"fields": ("workflow_type", "title", "description")}),
        (
            "Hierarchy",
            {
                "fields": ("parent_workflow", "relationship_type"),
                "description": "Configure parent-child workflow relationships",
            },
        ),
        ("Assignment", {"fields": ("owner", "assigned_to", "referred_to")}),
        ("State & Priority", {"fields": ("current_state", "priority", "deadline")}),
        ("Data", {"fields": ("data",), "classes": ("collapse",)}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "parent_workflow":
            # Only allow selection of workflows that can be parents
            # and prevent circular references
            obj = getattr(request, "_obj_", None)
            if obj:
                # If editing existing workflow, exclude self and descendants
                exclude_ids = [obj.id] + [w.id for w in obj.get_all_descendants()]
                kwargs["queryset"] = Workflow.objects.exclude(id__in=exclude_ids)

        elif db_field.name == "workflow_type":
            # Only show enabled workflow types where user has create roles
            user_roles = request.user.memberships.filter(is_active=True).values_list(
                "role", flat=True
            )
            kwargs["queryset"] = WorkflowType.objects.filter(
                enabled=True, create_roles__in=user_roles
            )

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_form(self, request, obj=None, change=False, **kwargs):
        # Store the object being edited for use in formfield_for_foreignkey
        request._obj_ = obj
        return super().get_form(request, obj, change, **kwargs)


@admin.register(WorkflowTransitionLog)
class WorkflowTransitionLogAdmin(admin.ModelAdmin):
    list_display = [
        "workflow",
        "transition",
        "from_state",
        "to_state",
        "user",
        "timestamp",
    ]
    list_filter = ["transition", "from_state", "to_state"]
    search_fields = ["workflow__title", "user__username"]
    date_hierarchy = "timestamp"
    readonly_fields = ["timestamp"]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["content_type", "object_id", "action", "user", "timestamp"]
    list_filter = ["action", "content_type"]
    search_fields = ["user__username"]
    date_hierarchy = "timestamp"
    readonly_fields = ["timestamp"]


# ============================================================================
# EVENT ADMIN
# ============================================================================


@admin.register(EventType)
class EventTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "description"]
    search_fields = ["name"]


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ["name", "location", "capacity"]
    search_fields = ["name", "location"]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "event_type",
        "group",
        "venue",
        "start_datetime",
        "status",
        "organizer",
    ]
    list_filter = ["event_type", "status", "group__group_type"]
    search_fields = ["title", "description"]
    date_hierarchy = "start_datetime"


@admin.register(EventAttendance)
class EventAttendanceAdmin(admin.ModelAdmin):
    list_display = ["event", "user", "status"]
    list_filter = ["status", "event__event_type"]
    search_fields = [
        "event__title",
        "user__username",
        "user__first_name",
        "user__last_name",
    ]


# ============================================================================
# NOTIFICATION & COMMENT ADMIN
# ============================================================================


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["user", "title", "is_read", "created_at"]
    list_filter = ["is_read"]
    search_fields = ["user__username", "title", "message"]
    date_hierarchy = "created_at"


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["workflow", "user", "created_at"]
    search_fields = ["workflow__title", "user__username", "text"]
    date_hierarchy = "created_at"


# ============================================================================
# SHAREPOINT ADMIN
# ============================================================================


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "url",
        "site_id",
        "is_personal_site",
        "user",
        "last_synced_at",
        "remote_modified_at",
    ]
    list_filter = ["is_personal_site", "last_synced_at"]
    search_fields = ["name", "url", "site_id", "user__username"]
    readonly_fields = ["last_synced_at", "remote_modified_at"]
    date_hierarchy = "last_synced_at"

    fieldsets = (
        ("Basic Information", {"fields": ("name", "url", "site_id")}),
        ("Site Type", {"fields": ("is_personal_site", "user")}),
        (
            "Synchronization",
            {
                "fields": ("last_synced_at", "remote_modified_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(SiteMember)
class SiteMemberAdmin(admin.ModelAdmin):
    list_display = ["site", "user"]
    list_filter = ["site"]
    search_fields = [
        "site__name",
        "user__username",
        "user__first_name",
        "user__last_name",
    ]
    autocomplete_fields = ["site", "user"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("site", "user")


@admin.register(Drive)
class DriveAdmin(admin.ModelAdmin):
    list_display = ["name", "site", "drive_id"]
    list_filter = ["site"]
    search_fields = ["name", "drive_id", "site__name"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("site")
