import asyncio
import json

import httpx
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (
    Attachment,
    Drive,
    Event,
    EventType,
    Group,
    GroupMembership,
    Role,
    SharePointFolder,
    SharePointToken,
    Site,
    SiteMember,
    State,
    Transition,
    User,
    Workflow,
    WorkflowTransitionLog,
    WorkflowType,
)
from .sharepoint import (
    get_all_sites,
    get_application_token,
    get_drive_items,
    get_folder_items,
    get_site_drives,
    upload_file,
)

# ============================================================================
# AUTHENTICATION VIEWS
# ============================================================================


def login_view(request):
    """User login view"""
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(
                request, f"Welcome back, {user.get_full_name() or user.username}!"
            )
            return redirect("dashboard")
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, "workflows/login.html")


def logout_view(request):
    """User logout view"""
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("login")


# ============================================================================
# DASHBOARD VIEW
# ============================================================================


@login_required
def dashboard(request):
    """Main dashboard view with workflow overview"""
    user = request.user

    # Get user's groups
    user_groups = user.memberships.filter(is_active=True).values_list(
        "group", flat=True
    )

    # Get workflows user can view
    workflows = Workflow.objects.filter(
        Q(workflow_type__group__in=user_groups) | Q(referred_to__in=user_groups)
    ).select_related("workflow_type", "current_state", "owner")

    # Statistics
    total_workflows = workflows.count()
    my_workflows = workflows.filter(owner=user).count()
    assigned_to_me = workflows.filter(assigned_to=user).count()

    # Overdue workflows - count all workflows past deadline
    overdue_workflows = workflows.filter(
        deadline__lt=timezone.now(), current_state__is_terminal=False
    ).count()

    # Workflows by priority
    urgent_count = workflows.filter(priority="urgent").count()
    high_count = workflows.filter(priority="high").count()

    # Recent workflows
    recent_workflows = workflows.order_by("-created_at")[:10]

    # Upcoming events
    upcoming_events = Event.objects.filter(
        group__in=user_groups, start_datetime__gte=timezone.now(), status="scheduled"
    ).order_by("start_datetime")[:5]

    # Workflows by state (for chart)
    workflows_by_state = workflows.values(
        "current_state__name", "current_state__color"
    ).annotate(count=Count("id"))

    # Workflows by type
    workflows_by_type = workflows.values("workflow_type__name").annotate(
        count=Count("id")
    )

    context = {
        "total_workflows": total_workflows,
        "my_workflows": my_workflows,
        "assigned_to_me": assigned_to_me,
        "overdue_workflows": overdue_workflows,
        "urgent_count": urgent_count,
        "high_count": high_count,
        "recent_workflows": recent_workflows,
        "upcoming_events": upcoming_events,
        "workflows_by_state": workflows_by_state,
        "workflows_by_type": workflows_by_type,
    }

    return render(request, "workflows/dashboard.html", context)


# ============================================================================
# WORKFLOW VIEWS
# ============================================================================


@login_required
def workflow_list(request):
    """List all workflows user can access"""
    user = request.user
    user_groups = user.memberships.filter(is_active=True).values_list(
        "group", flat=True
    )

    # Base queryset with hierarchy support
    workflows = Workflow.objects.filter(
        Q(workflow_type__group__in=user_groups) | Q(referred_to__in=user_groups)
    ).select_related(
        "workflow_type",
        "current_state",
        "owner",
        "assigned_to",
        "parent_workflow",
    )

    # Filters
    workflow_type = request.GET.get("type")
    state = request.GET.get("state")
    priority = request.GET.get("priority")
    group = request.GET.get("group")
    search = request.GET.get("search")

    if workflow_type:
        workflows = workflows.filter(workflow_type_id=workflow_type)
    if state:
        workflows = workflows.filter(current_state_id=state)
    if priority:
        workflows = workflows.filter(priority=priority)
    if group:
        workflows = workflows.filter(workflow_type__group_id=group)
    if search:
        workflows = workflows.filter(
            Q(title__icontains=search) | Q(description__icontains=search)
        )

    # For filter dropdowns
    workflow_types = WorkflowType.objects.all()
    states = State.objects.all()
    groups = Group.objects.filter(id__in=user_groups)

    context = {
        "workflows": workflows,
        "workflow_types": workflow_types,
        "states": states,
        "groups": groups,
    }

    return render(request, "workflows/workflow_list.html", context)


@login_required
def workflow_create(request):
    """
    Create a Workflow instance from an available WorkflowType.

    UI/POST contract (kept intentionally simple so you can wire it up from a modal or page):
    - workflow_type (required): WorkflowType id
    - group (optional): Group id (defaults to type's group)
    - title (required)
    - description (optional)
    - priority (optional): low|medium|high|urgent
    - deadline (optional): ISO-ish datetime string accepted by Django DateTimeField form parsing if you later add a Form
    """
    user = request.user

    # Only allow users with roles that can create at least one enabled workflow type
    user_roles = user.memberships.filter(is_active=True).values_list("role", flat=True)
    can_create = WorkflowType.objects.filter(
        enabled=True, create_roles__in=user_roles
    ).exists()
    if not can_create:
        messages.error(request, "You do not have permission to create workflows.")
        return redirect("workflow_list")

    parent_workflow = None
    if request.method == "GET":
        parent_id = request.GET.get("parent")
        if parent_id:
            parent_workflow = get_object_or_404(Workflow, pk=parent_id)
            # Check if user can create subworkflows for this parent
            if not parent_workflow.can_user_edit(request.user):
                messages.error(
                    request,
                    "You do not have permission to create subworkflows for this workflow.",
                )
                return redirect("workflow_detail", pk=parent_id)

        # Filter workflow types to only enabled ones where user has create roles
        context = {
            "workflow_types": WorkflowType.objects.filter(
                enabled=True, create_roles__in=user_roles
            ),
            "parent_workflow": parent_workflow,
        }
        return render(request, "workflows/workflow_create.html", context)

    # POST
    workflow_type_id = request.POST.get("workflow_type")
    parent_workflow_id = request.POST.get("parent_workflow")
    relationship_type = request.POST.get("relationship_type")
    title = (request.POST.get("title") or "").strip()
    description = (request.POST.get("description") or "").strip()
    priority = request.POST.get("priority") or "medium"

    if not workflow_type_id or not title:
        messages.error(request, "Workflow type and title are required.")
        return redirect("workflow_list")

    workflow_type = get_object_or_404(WorkflowType, pk=workflow_type_id)

    # Parse JSON data from optional fields
    workflow_data_str = request.POST.get("workflow_data", "{}")
    try:
        workflow_data = (
            json.loads(workflow_data_str) if workflow_data_str.strip() else {}
        )
        # Validate against workflow type schema if it exists
        if workflow_type.json_schema:
            # Basic validation - ensure it's a dict
            if not isinstance(workflow_data, dict):
                workflow_data = {}
    except (json.JSONDecodeError, ValueError):
        workflow_data = {}

    # Check if user has a role that can create this specific workflow type
    if not workflow_type.create_roles.filter(id__in=user_roles).exists():
        messages.error(
            request, "You do not have permission to create this type of workflow."
        )
        return redirect("workflow_list")

    parent_workflow = None
    if parent_workflow_id:
        parent_workflow = get_object_or_404(Workflow, pk=parent_workflow_id)
        # Check permissions
        if not parent_workflow.can_user_edit(request.user):
            messages.error(
                request,
                "You do not have permission to create subworkflows for this workflow.",
            )
            return redirect("workflow_detail", pk=parent_workflow_id)
        # Check if parent can have this type
        if not parent_workflow.can_be_parent_of(workflow_type.name):
            messages.error(
                request,
                f"{parent_workflow.workflow_type.name} cannot have {workflow_type.name} as subworkflow.",
            )
            return redirect("workflow_detail", pk=parent_workflow_id)
        # Require relationship_type for subworkflows
        if not relationship_type:
            messages.error(request, "Relationship type is required for subworkflows.")
            return redirect("workflow_detail", pk=parent_workflow_id)

    initial_state = (
        State.objects.filter(workflow_type=workflow_type, is_initial=True)
        .order_by("order", "id")
        .first()
    )
    if not initial_state:
        # Fallback: first state by order if none marked initial
        initial_state = (
            State.objects.filter(workflow_type=workflow_type)
            .order_by("order", "id")
            .first()
        )

    if not initial_state:
        messages.error(
            request, f"No states configured for workflow type '{workflow_type.name}'."
        )
        return redirect("workflow_list")

    workflow = Workflow.objects.create(
        workflow_type=workflow_type,
        title=title,
        description=description,
        current_state=initial_state,
        owner=user,
        priority=priority,
        parent_workflow=parent_workflow,
        relationship_type=relationship_type if parent_workflow else "",
        data=workflow_data,
    )

    messages.success(request, f"Workflow created: {workflow.title}")
    return redirect("workflow_detail", pk=workflow.pk)


@login_required
def workflow_detail(request, pk):
    """Detailed view of a workflow"""
    workflow = get_object_or_404(Workflow, pk=pk)

    # Check if user can view this workflow
    if not workflow.can_user_view(request.user):
        messages.error(request, "You do not have permission to view this workflow.")
        return redirect("workflow_list")

    # Get available transitions for this user
    available_transitions = workflow.get_available_transitions(request.user)

    # Get transition history
    transition_logs = workflow.transition_logs.all().select_related(
        "user", "from_state", "to_state"
    )

    # Get comments
    comments = workflow.comments.all().select_related("user")

    # Get hierarchy information
    hierarchy_path = workflow.get_workflow_hierarchy_path()
    sub_workflows = workflow.sub_workflows.all().select_related(
        "workflow_type", "current_state", "owner"
    )
    root_workflow = workflow.get_root_workflow()

    # Get sibling workflows (other sub-workflows of the same parent)
    sibling_workflows = []
    if workflow.parent_workflow:
        sibling_workflows = workflow.parent_workflow.sub_workflows.exclude(
            id=workflow.id
        ).select_related("workflow_type", "current_state")

    # Calculate related count for badge
    related_count = sub_workflows.count() + len(sibling_workflows)
    if workflow.parent_workflow:
        related_count += 1

    context = {
        "workflow": workflow,
        "available_transitions": available_transitions,
        "transition_logs": transition_logs,
        "comments": comments,
        "hierarchy_path": hierarchy_path,
        "sub_workflows": sub_workflows,
        "sibling_workflows": sibling_workflows,
        "root_workflow": root_workflow,
        "is_root": workflow.is_root_workflow,
        "has_children": workflow.has_sub_workflows,
        "hierarchy_level": workflow.hierarchy_level,
        "related_count": related_count,
        "can_edit": workflow.can_user_edit(request.user),
    }

    return render(request, "workflows/workflow_detail.html", context)


@login_required
def workflow_edit(request, pk):
    """Edit a workflow"""
    workflow = get_object_or_404(Workflow, pk=pk)

    # Check if user can edit this workflow
    if not workflow.can_user_edit(request.user):
        messages.error(request, "You do not have permission to edit this workflow.")
        return redirect("workflow_detail", pk=pk)

    if request.method == "GET":
        context = {
            "workflow": workflow,
            "workflow_types": WorkflowType.objects.all(),
        }
        return render(request, "workflows/workflow_edit.html", context)

    # POST
    workflow_type_id = request.POST.get("workflow_type")
    title = (request.POST.get("title") or "").strip()
    description = (request.POST.get("description") or "").strip()
    priority = request.POST.get("priority") or "medium"
    deadline = request.POST.get("deadline")

    if not workflow_type_id or not title:
        messages.error(request, "Workflow type and title are required.")
        return redirect("workflow_edit", pk=pk)

    workflow_type = get_object_or_404(WorkflowType, pk=workflow_type_id)

    # Parse JSON data from optional fields
    workflow_data_str = request.POST.get("workflow_data", "{}")
    try:
        workflow_data = (
            json.loads(workflow_data_str) if workflow_data_str.strip() else {}
        )
        # Validate against workflow type schema if it exists
        if workflow_type.json_schema:
            # Basic validation - ensure it's a dict
            if not isinstance(workflow_data, dict):
                workflow_data = {}
    except (json.JSONDecodeError, ValueError):
        workflow_data = {}

    # Update workflow
    workflow.workflow_type = workflow_type
    workflow.title = title
    workflow.description = description
    workflow.priority = priority
    workflow.data = workflow_data
    if deadline:
        workflow.deadline = deadline
    workflow.save()

    messages.success(request, f"Workflow updated: {workflow.title}")
    return redirect("workflow_detail", pk=workflow.pk)


@login_required
def workflow_transition(request, pk, transition_id):
    """Execute a workflow transition"""
    workflow = get_object_or_404(Workflow, pk=pk)
    transition = get_object_or_404(Transition, pk=transition_id)

    # Check if user can perform this transition
    available_transitions = workflow.get_available_transitions(request.user)
    if transition not in available_transitions:
        messages.error(
            request, "You do not have permission to perform this transition."
        )
        return redirect("workflow_detail", pk=pk)

    if request.method == "POST":
        comment = request.POST.get("comment", "")

        # Validate comment if required
        if transition.requires_comment and not comment:
            messages.error(request, "A comment is required for this transition.")
            return redirect("workflow_detail", pk=pk)

        # Log the transition
        WorkflowTransitionLog.objects.create(
            workflow=workflow,
            transition=transition,
            from_state=workflow.current_state,
            to_state=transition.to_state,
            user=request.user,
            comment=comment,
        )

        # Update workflow state
        workflow.current_state = transition.to_state
        workflow.save()

        messages.success(
            request, f"Workflow transitioned to {transition.to_state.name}"
        )
        return redirect("workflow_detail", pk=pk)

    context = {
        "workflow": workflow,
        "transition": transition,
    }

    return render(request, "workflows/workflow_transition.html", context)


# ============================================================================
# EVENT VIEWS
# ============================================================================


@login_required
def event_list(request):
    """List all events"""
    user = request.user
    user_groups = user.memberships.filter(is_active=True).values_list(
        "group", flat=True
    )

    events = Event.objects.filter(group__in=user_groups).select_related(
        "event_type", "group", "venue", "organizer"
    )

    # Filters
    event_type = request.GET.get("type")
    status = request.GET.get("status")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if event_type:
        events = events.filter(event_type_id=event_type)
    if status:
        events = events.filter(status=status)
    if date_from:
        events = events.filter(start_datetime__gte=date_from)
    if date_to:
        events = events.filter(start_datetime__lte=date_to)

    # Separate upcoming and past events
    now = timezone.now()
    upcoming_events = events.filter(start_datetime__gte=now).order_by("start_datetime")
    past_events = events.filter(start_datetime__lt=now).order_by("-start_datetime")

    event_types = EventType.objects.all()

    context = {
        "upcoming_events": upcoming_events,
        "past_events": past_events,
        "event_types": event_types,
    }

    return render(request, "workflows/event_list.html", context)


@login_required
def event_detail(request, pk):
    """Detailed view of an event"""
    event = get_object_or_404(Event, pk=pk)

    # Get attendance records
    attendances = event.attendances.all().select_related("user")

    # Check if current user has attendance record
    user_attendance = attendances.filter(user=request.user).first()

    context = {
        "event": event,
        "attendances": attendances,
        "user_attendance": user_attendance,
    }

    return render(request, "workflows/event_detail.html", context)


# ============================================================================
# GROUP VIEWS
# ============================================================================


@login_required
def group_list(request):
    """List all groups"""
    user = request.user
    user_groups = user.memberships.filter(is_active=True).values_list(
        "group", flat=True
    )

    # Get groups user can access (their groups and descendants)
    groups = Group.objects.filter(id__in=user_groups).select_related("parent")

    context = {
        "groups": groups,
    }

    return render(request, "workflows/group_list.html", context)


@login_required
def group_detail(request, pk):
    """Detailed view of a group"""
    group = get_object_or_404(Group, pk=pk)

    # Get members
    memberships = group.members.filter(is_active=True).select_related("user", "role")

    # Get workflows
    workflows = Workflow.objects.filter(workflow_type__group=group).select_related(
        "workflow_type", "current_state"
    )[:10]

    # Get events
    events = group.events.filter(start_datetime__gte=timezone.now()).order_by(
        "start_datetime"
    )[:5]

    # Get child groups
    children = group.get_children()

    context = {
        "group": group,
        "memberships": memberships,
        "workflows": workflows,
        "events": events,
        "children": children,
    }

    return render(request, "workflows/group_detail.html", context)


# ============================================================================
# REPORTS VIEWS
# ============================================================================


@login_required
def reports(request):
    """Reports and analytics view"""
    user = request.user
    user_groups = user.memberships.filter(is_active=True).values_list(
        "group", flat=True
    )

    # Get workflows user can view
    workflows = Workflow.objects.filter(
        Q(workflow_type__group__in=user_groups) | Q(referred_to__in=user_groups)
    ).select_related("workflow_type", "current_state", "owner")

    # Workflow statistics
    total_workflows = workflows.count()

    # By workflow type
    by_type = (
        workflows.values("workflow_type__name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # By state
    by_state = (
        workflows.values("current_state__name", "current_state__color")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # By priority
    by_priority = (
        workflows.values("priority").annotate(count=Count("id")).order_by("priority")
    )

    # By group
    by_group = (
        workflows.values("workflow_type__group__name")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    # Overdue workflows
    overdue = workflows.filter(
        deadline__lt=timezone.now(), current_state__is_terminal=False
    ).count()

    # Workflows created this month

    this_month_start = timezone.now().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    created_this_month = workflows.filter(created_at__gte=this_month_start).count()

    # Completed workflows (terminal states)
    completed = workflows.filter(current_state__is_terminal=True).count()

    # Active workflows
    active = workflows.filter(current_state__is_terminal=False).count()

    # Recent activity (transition logs)
    recent_transitions = (
        WorkflowTransitionLog.objects.filter(workflow__in=workflows)
        .select_related("workflow", "user", "from_state", "to_state")
        .order_by("-timestamp")[:20]
    )

    # Events statistics
    events = Event.objects.filter(group__in=user_groups)
    total_events = events.count()
    upcoming_events = events.filter(start_datetime__gte=timezone.now()).count()

    context = {
        "total_workflows": total_workflows,
        "by_type": by_type,
        "by_state": by_state,
        "by_priority": by_priority,
        "by_group": by_group,
        "overdue": overdue,
        "created_this_month": created_this_month,
        "completed": completed,
        "active": active,
        "recent_transitions": recent_transitions,
        "total_events": total_events,
        "upcoming_events": upcoming_events,
    }

    return render(request, "workflows/reports.html", context)


# ============================================================================
# SHAREPOINT API VIEWS
# ============================================================================


@require_http_methods(["GET"])
def sharepoint_test(request):
    """Test SharePoint configuration and return debug info."""
    try:
        from django.conf import settings

        debug_info = {
            "settings": {
                "SHAREPOINT_CLIENT_ID": bool(settings.SHAREPOINT_CLIENT_ID),
                "SHAREPOINT_CLIENT_SECRET": bool(settings.SHAREPOINT_CLIENT_SECRET),
                "SHAREPOINT_TENANT_ID": settings.SHAREPOINT_TENANT_ID,
                "SHAREPOINT_TOKEN_URL": settings.SHAREPOINT_TOKEN_URL,
                "SHAREPOINT_SCOPE": settings.SHAREPOINT_SCOPE,
            },
            "cached_tokens": list(
                SharePointToken.objects.values_list("id", "is_active", "expires_at")
            ),
        }

        # Try to get a token
        try:
            token_data = get_application_token()
            debug_info["token_test"] = "SUCCESS"
            debug_info["token_keys"] = list(token_data.keys())
        except Exception as e:
            debug_info["token_test"] = f"FAILED: {str(e)}"

        return JsonResponse(debug_info)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def sharepoint_sites(request):
    """Get SharePoint sites where the current user is a member."""
    try:
        # First try to get token
        print("Attempting to get SharePoint token...")
        token_data = get_application_token()
        print("Token obtained successfully")

        # Run async function in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        sites_data = loop.run_until_complete(get_all_sites(token_data))
        loop.close()

        print("Sites data received:", sites_data)

        # Get site IDs where current user is a member
        user_member_sites = SiteMember.objects.filter(user=request.user).values_list(
            "site__site_id", flat=True
        )

        # Update local database with sites and filter for user's memberships
        sites = []
        for site_info in sites_data.get("value", []):
            site_id = site_info["id"]

            # Update or create site in database
            site, created = Site.objects.update_or_create(
                site_id=site_id,
                defaults={
                    "name": site_info.get(
                        "displayName", site_info.get("name", "Unknown")
                    ),
                    "url": site_info.get("webUrl", ""),
                    "is_personal_site": site_info.get("isPersonalSite", False),
                },
            )

            # Only include sites where user is a member
            if site_id in user_member_sites:
                sites.append(
                    {
                        "id": site.site_id,
                        "name": site.name,
                        "url": site.url,
                        "is_personal_site": site.is_personal_site,
                    }
                )

        return JsonResponse({"sites": sites})

    except Exception as e:
        print("Error in sharepoint_sites:", str(e))
        import traceback

        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def sharepoint_site_drives(request, site_id):
    """Get all drives for a specific SharePoint site."""
    try:
        # Check if user is a member of this site
        if not SiteMember.objects.filter(
            user=request.user, site__site_id=site_id
        ).exists():
            return JsonResponse(
                {"error": "Access denied: You are not a member of this site"},
                status=403,
            )

        token_data = get_application_token()

        # Run async function in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        drives_data = loop.run_until_complete(get_site_drives(token_data, site_id))
        loop.close()

        # Update local database with drives
        site = Site.objects.get(site_id=site_id)
        drives = []
        for drive_info in drives_data.get("value", []):
            drive, created = Drive.objects.update_or_create(
                site=site,
                drive_id=drive_info["id"],
                defaults={"name": drive_info.get("name", "Unknown")},
            )
            drives.append(
                {"id": drive.drive_id, "name": drive.name, "site_id": site.site_id}
            )

        return JsonResponse({"drives": drives})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def sharepoint_drive_folders(request, drive_id):
    """Get root folders for a specific drive."""
    try:
        token_data = get_application_token()

        # Run async function in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        items_data = loop.run_until_complete(get_drive_items(token_data, drive_id))
        loop.close()

        # Filter for folders only
        folders = []
        for item in items_data.get("value", []):
            if "folder" in item:
                folders.append(
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "web_url": item.get("webUrl", ""),
                        "parent_reference": item.get("parentReference", {}),
                    }
                )

        # Create response with appropriate messaging
        response_data = {"folders": folders}

        if not folders:
            response_data["message"] = (
                "No folders in the root directory. You can select files directly from the root folder."
            )
            response_data["show_root_files"] = (
                True  # Flag to indicate UI should show root files option
            )
        else:
            response_data["message"] = (
                f"Found {len(folders)} folder(s) in the root directory"
            )
            response_data["show_root_files"] = True  # Still allow root file access

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def sharepoint_folder_items(request, folder_id):
    """Get items in a specific SharePoint folder or root folder."""
    try:
        # Get drive_id from query parameter or fetch from folder info
        drive_id = request.GET.get("drive_id")
        if not drive_id:
            # For root folder, we can't get drive_id from folder since it doesn't exist in DB
            if folder_id == "root":
                return JsonResponse(
                    {"error": "drive_id parameter required for root folder"}, status=400
                )
            # Try to get drive_id from the folder itself
            folder = SharePointFolder.objects.filter(folder_id=folder_id).first()
            if folder:
                drive_id = folder.drive.drive_id
            else:
                return JsonResponse(
                    {"error": "drive_id parameter required"}, status=400
                )

        token_data = get_application_token()

        # Run async function in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        items_data = loop.run_until_complete(
            get_folder_items(token_data, drive_id, folder_id)
        )
        loop.close()

        # Process items to separate files and folders
        files = []
        folders = []

        for item in items_data.get("value", []):
            if item.get("folder"):
                # This is a folder
                folders.append(
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "parent_reference": item.get("parentReference", {}),
                    }
                )
            elif item.get("file"):
                # This is a file
                files.append(
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "size": item.get("size", 0),
                        "mimetype": item.get("file", {}).get("mimeType", ""),
                        "web_url": item.get("webUrl", ""),
                        "download_url": item.get("@microsoft.graph.downloadUrl", ""),
                        "created_at": item.get("createdDateTime"),
                        "modified_at": item.get("lastModifiedDateTime"),
                    }
                )

        # Create response with appropriate messaging
        response_data = {"files": files, "folders": folders}

        # Add message about folder location
        if folder_id == "root":
            response_data["folder_info"] = {"name": "Root Folder", "is_root": True}
        else:
            # Try to get folder name from the items data or database
            folder_name = "Unknown Folder"
            if folder_id != "root":
                folder = SharePointFolder.objects.filter(folder_id=folder_id).first()
                if folder:
                    folder_name = folder.get_full_path()
            response_data["folder_info"] = {"name": folder_name, "is_root": False}

        # Add message if no files or folders
        if not files and not folders:
            if folder_id == "root":
                response_data["message"] = "No files or folders in the root directory"
            else:
                response_data["message"] = "No files or folders in this directory"

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def sharepoint_admin_sites(request):
    """SharePoint administration - manage SharePoint sites"""
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")

    sites = Site.objects.all().select_related().order_by("name")

    search = request.GET.get("search")
    is_personal = request.GET.get("is_personal")

    if search:
        sites = sites.filter(
            Q(name__icontains=search)
            | Q(url__icontains=search)
            | Q(site_id__icontains=search)
        )
    if is_personal:
        sites = sites.filter(is_personal_site=is_personal == "true")

    # Get member counts for each site
    sites_with_counts = []
    team_sites_count = 0
    personal_sites_count = 0

    for site in sites:
        member_count = SiteMember.objects.filter(site=site).count()
        site_data = {"site": site, "member_count": member_count}
        sites_with_counts.append(site_data)

        if site.is_personal_site:
            personal_sites_count += 1
        else:
            team_sites_count += 1

    context = {
        "sites_with_counts": sites_with_counts,
        "team_sites_count": team_sites_count,
        "personal_sites_count": personal_sites_count,
    }

    return render(request, "workflows/admin/sharepoint_sites.html", context)


@login_required
def sharepoint_admin_members(request):
    """SharePoint administration - manage site memberships"""
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")

    site_members = (
        SiteMember.objects.all()
        .select_related("site", "user")
        .order_by("site__name", "user__username")
    )

    search = request.GET.get("search")
    site_filter = request.GET.get("site")

    if search:
        site_members = site_members.filter(
            Q(user__username__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(site__name__icontains=search)
        )
    if site_filter:
        site_members = site_members.filter(site__site_id=site_filter)

    # Get all sites for filter dropdown
    sites = Site.objects.all().order_by("name")

    # Calculate statistics
    unique_users_count = len(set(member.user_id for member in site_members))
    team_sites_count = sum(
        1 for member in site_members if not member.site.is_personal_site
    )
    personal_sites_count = sum(
        1 for member in site_members if member.site.is_personal_site
    )

    context = {
        "site_members": site_members,
        "sites": sites,
        "unique_users_count": unique_users_count,
        "team_sites_count": team_sites_count,
        "personal_sites_count": personal_sites_count,
    }

    return render(request, "workflows/admin/sharepoint_members.html", context)


@login_required
def attachment_link_sharepoint(request):
    """Link an existing SharePoint file as an attachment."""
    try:
        data = json.loads(request.body)
        file_id = data.get("file_id")
        site_id = data.get("site_id")
        drive_id = data.get("drive_id")
        folder_id = data.get("folder_id")
        attachment_type = data.get("type", "document")
        workflow_id = data.get("workflow_id")

        if not all([file_id, site_id, drive_id]):
            return JsonResponse(
                {"error": "file_id, site_id, and drive_id required"}, status=400
            )

        # Check if user is a member of this site
        if not SiteMember.objects.filter(
            user=request.user, site__site_id=site_id
        ).exists():
            return JsonResponse(
                {"error": "Access denied: You are not a member of this site"},
                status=403,
            )

        # Get SharePoint objects
        site = Site.objects.get(site_id=site_id)
        drive = Drive.objects.get(drive_id=drive_id)
        folder = (
            SharePointFolder.objects.filter(folder_id=folder_id).first()
            if folder_id
            else None
        )

        # Get file metadata from SharePoint
        token_data = get_application_token()

        # Run async function in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def fetch_file_metadata():
            file_url = (
                f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}"
            )
            headers = {"Authorization": f"Bearer {token_data['access_token']}"}

            async with httpx.AsyncClient() as client:
                response = await client.get(file_url, headers=headers)
                response.raise_for_status()
                return response.json()

        file_data = loop.run_until_complete(fetch_file_metadata())
        loop.close()

        # Create attachment record
        attachment = Attachment.objects.create(
            name=file_data["name"],
            drive_id=drive_id,
            item_id=file_id,
            mimetype=file_data.get("file", {}).get("mimeType", ""),
            size=file_data.get("size", 0),
            download_url=file_data.get("@microsoft.graph.downloadUrl", ""),
            sharepoint_web_url=file_data.get("webUrl", ""),
            sharepoint_site=site,
            sharepoint_drive=drive,
            sharepoint_folder=folder,
            sharepoint_folder_path=folder.get_full_path() if folder else "",
            type=attachment_type,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )

        # Link to workflow if provided
        if workflow_id:
            try:
                workflow = Workflow.objects.get(pk=workflow_id)
                attachment.related_workflow = workflow
                attachment.save()
                workflow.attachments.add(attachment)
            except Workflow.DoesNotExist:
                pass

        return JsonResponse(
            {
                "success": True,
                "attachment": {
                    "id": attachment.id,
                    "name": attachment.name,
                    "size": attachment.size,
                    "url": attachment.get_sharepoint_url(),
                    "type": attachment.type,
                },
            }
        )

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def attachment_upload(request):
    """Upload a file to SharePoint."""
    try:
        if "file" not in request.FILES:
            return JsonResponse({"error": "No file provided"}, status=400)

        file_obj = request.FILES["file"]
        site_id = request.POST.get("site_id")
        drive_id = request.POST.get("drive_id")
        folder_id = request.POST.get("folder_id")
        attachment_type = request.POST.get("type", "document")
        workflow_id = request.POST.get("workflow_id")

        if not all([site_id, drive_id]):
            return JsonResponse({"error": "site_id and drive_id required"}, status=400)

        # Get SharePoint objects
        site = Site.objects.get(site_id=site_id)
        drive = Drive.objects.get(drive_id=drive_id)

        # Read file content
        file_content = file_obj.read()

        # Get token and upload
        token_data = get_application_token()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Use root folder if no folder_id provided
        target_folder_id = folder_id if folder_id else "root"
        upload_result = loop.run_until_complete(
            upload_file(
                token_data, drive_id, target_folder_id, file_obj.name, file_content
            )
        )
        loop.close()

        # Create attachment record
        attachment = Attachment.objects.create(
            name=file_obj.name,
            drive_id=drive_id,
            item_id=upload_result["id"],
            mimetype=upload_result.get("file", {}).get("mimeType", ""),
            size=upload_result.get("size", 0),
            download_url=upload_result.get("@microsoft.graph.downloadUrl", ""),
            sharepoint_web_url=upload_result.get("webUrl", ""),
            sharepoint_site=site,
            sharepoint_drive=drive,
            type=attachment_type,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )

        # Link to workflow if provided
        if workflow_id:
            try:
                workflow = Workflow.objects.get(pk=workflow_id)
                attachment.related_workflow = workflow
                attachment.save()
                # Also add to workflow's many-to-many relationship
                workflow.attachments.add(attachment)
            except Workflow.DoesNotExist:
                pass  # Workflow doesn't exist, but attachment is still created

        return JsonResponse(
            {
                "success": True,
                "attachment": {
                    "id": attachment.id,
                    "name": attachment.name,
                    "size": attachment.size,
                    "url": attachment.get_sharepoint_url(),
                    "type": attachment.type,
                },
            }
        )

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET", "DELETE"])
def attachment_detail(request, pk):
    """Get or delete attachment details."""
    try:
        attachment = Attachment.objects.get(pk=pk)

        if request.method == "GET":
            return JsonResponse(
                {
                    "id": attachment.id,
                    "name": attachment.name,
                    "size": attachment.size,
                    "mimetype": attachment.mimetype,
                    "url": attachment.get_sharepoint_url(),
                    "type": attachment.type,
                    "created_at": attachment.created_at.isoformat(),
                    "uploaded_by": attachment.uploaded_by.username
                    if attachment.uploaded_by
                    else None,
                }
            )

        elif request.method == "DELETE":
            attachment.delete()
            return JsonResponse({"success": True})

    except Attachment.DoesNotExist:
        return JsonResponse({"error": "Attachment not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def workflow_attachments(request, pk):
    """View and manage attachments for a specific workflow."""
    workflow = get_object_or_404(Workflow, pk=pk)

    # Check if user can view this workflow
    if not workflow.can_user_view(request.user):
        messages.error(request, "You don't have permission to view this workflow.")
        return redirect("workflow_list")

    context = {
        "workflow": workflow,
    }

    return render(request, "workflows/attachments.html", context)


# ============================================================================
# ADMIN VIEWS
# ============================================================================


@login_required
def user_admin(request):
    """User administration - manage users and their basic information"""
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")

    users = User.objects.all().select_related("department", "supervisor")

    search = request.GET.get("search")
    employee_type = request.GET.get("employee_type")
    is_active = request.GET.get("is_active")

    if search:
        users = users.filter(
            Q(username__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
        )
    if employee_type:
        users = users.filter(employee_type=employee_type)
    if is_active:
        users = users.filter(is_active=is_active == "true")

    context = {
        "users": users,
        "employee_types": User.EMPLOYEE_TYPE_CHOICES,
    }

    return render(request, "workflows/admin/user_admin.html", context)


@login_required
def user_admin_groups(request):
    """User administration - manage user group memberships"""
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")

    memberships = GroupMembership.objects.all().select_related("user", "group", "role")

    user_filter = request.GET.get("user")
    group_filter = request.GET.get("group")
    role_filter = request.GET.get("role")
    is_active = request.GET.get("is_active")

    if user_filter:
        memberships = memberships.filter(user_id=user_filter)
    if group_filter:
        memberships = memberships.filter(group_id=group_filter)
    if role_filter:
        memberships = memberships.filter(role_id=role_filter)
    if is_active:
        memberships = memberships.filter(is_active=is_active == "true")

    users = User.objects.all()
    groups = Group.objects.all()
    roles = Role.objects.all()

    context = {
        "memberships": memberships,
        "users": users,
        "groups": groups,
        "roles": roles,
    }

    return render(request, "workflows/admin/user_admin_groups.html", context)


@login_required
def user_admin_roles(request):
    """User administration - manage user roles and permissions"""
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")

    roles = Role.objects.all()

    context = {
        "roles": roles,
    }

    return render(request, "workflows/admin/user_admin_roles.html", context)


@login_required
def user_admin_workflow_types(request):
    """User administration - manage workflow types"""
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")

    workflow_types = WorkflowType.objects.all().prefetch_related(
        "states", "transitions"
    )

    context = {
        "workflow_types": workflow_types,
    }

    return render(request, "workflows/admin/user_admin_workflow_types.html", context)


@login_required
def workflow_type_create(request):
    """Create a new workflow type template"""
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        group_id = request.POST.get("group")  # This comes from the hidden field
        enabled = request.POST.get("enabled") == "on"
        create_roles_str = request.POST.get("create_roles", "")
        json_schema_str = request.POST.get("json_schema", "{}")

        # Parse comma-separated roles from dropdown
        create_roles = (
            [
                role_id.strip()
                for role_id in create_roles_str.split(",")
                if role_id.strip()
            ]
            if create_roles_str
            else []
        )

        # Parse JSON schema

        try:
            json_schema = json.loads(json_schema_str) if json_schema_str.strip() else {}
            # Validate JSON schema structure
            if not isinstance(json_schema, dict):
                json_schema = {}
        except (json.JSONDecodeError, ValueError):
            json_schema = {}

        # Validation
        errors = []
        if not name:
            errors.append("Template name is required.")
        elif len(name) > 100:
            errors.append("Template name cannot exceed 100 characters.")

        if not group_id:
            errors.append(
                "Owner group is required. Please select a valid group from the dropdown."
            )

        if not create_roles:
            errors.append("At least one create role must be selected.")

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            try:
                group = Group.objects.get(id=group_id)

                # Check if workflow type with this name already exists
                if WorkflowType.objects.filter(name__iexact=name).exists():
                    messages.error(
                        request,
                        f"A workflow template with the name '{name}' already exists.",
                    )
                else:
                    workflow_type = WorkflowType.objects.create(
                        name=name,
                        description=description,
                        group=group,
                        enabled=enabled,
                        json_schema=json_schema,
                    )
                    workflow_type.create_roles.set(create_roles)

                    # Validate the workflow type
                    try:
                        workflow_type.clean()
                        workflow_type.save()
                        messages.success(
                            request, f"Workflow template '{name}' created successfully."
                        )
                        return redirect("admin_workflow_types")
                    except ValidationError as e:
                        workflow_type.delete()
                        for error in e.messages:
                            messages.error(request, error)

            except Group.DoesNotExist:
                messages.error(
                    request,
                    "Selected group does not exist. Please select a valid group.",
                )
            except Exception as e:
                messages.error(request, f"Error creating workflow template: {str(e)}")

    groups = Group.objects.all()
    roles = Role.objects.all()

    # Create a mapping of group IDs to available roles
    group_roles = {}
    for group in groups:
        # Get unique roles available in this group through memberships
        available_roles = group.members.values_list("role__id", "role__name").distinct()
        group_roles[str(group.id)] = [
            {"id": role_id, "name": role_name} for role_id, role_name in available_roles
        ]

    context = {
        "groups": groups,
        "roles": roles,
        "group_roles": group_roles,
    }

    return render(request, "workflows/admin/workflow_type_create.html", context)


@login_required
def workflow_type_edit(request, pk):
    """Edit an existing workflow type template"""
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")

    workflow_type = get_object_or_404(WorkflowType, pk=pk)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        group_id = request.POST.get("group")
        enabled = request.POST.get("enabled") == "on"
        create_roles_str = request.POST.get("create_roles", "")
        json_schema_str = request.POST.get("json_schema", "{}")

        # Parse comma-separated roles from dropdown
        create_roles = (
            [
                role_id.strip()
                for role_id in create_roles_str.split(",")
                if role_id.strip()
            ]
            if create_roles_str
            else []
        )

        # Parse JSON schema

        try:
            json_schema = json.loads(json_schema_str) if json_schema_str.strip() else {}
            # Validate JSON schema structure
            if not isinstance(json_schema, dict):
                json_schema = {}
        except (json.JSONDecodeError, ValueError):
            json_schema = {}

        # Validation
        errors = []
        if not name:
            errors.append("Template name is required.")
        elif len(name) > 100:
            errors.append("Template name cannot exceed 100 characters.")

        if not group_id:
            errors.append(
                "Owner group is required. Please select a valid group from the dropdown."
            )

        if not create_roles:
            errors.append("At least one create role must be selected.")

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            try:
                group = Group.objects.get(id=group_id)

                # Check if workflow type with this name already exists (excluding current)
                if (
                    WorkflowType.objects.filter(name__iexact=name)
                    .exclude(pk=workflow_type.pk)
                    .exists()
                ):
                    messages.error(
                        request,
                        f"A workflow template with the name '{name}' already exists.",
                    )
                else:
                    # Update workflow type
                    workflow_type.name = name
                    workflow_type.description = description
                    workflow_type.group = group
                    workflow_type.enabled = enabled
                    workflow_type.json_schema = json_schema
                    workflow_type.save()
                    workflow_type.create_roles.set(create_roles)

                    # Validate the workflow type
                    try:
                        workflow_type.clean()
                        workflow_type.save()
                        messages.success(
                            request, f"Workflow template '{name}' updated successfully."
                        )
                        return redirect("admin_workflow_types")
                    except ValidationError as e:
                        for error in e.messages:
                            messages.error(request, error)

            except Group.DoesNotExist:
                messages.error(
                    request,
                    "Selected group does not exist. Please select a valid group.",
                )
            except Exception as e:
                messages.error(request, f"Error updating workflow template: {str(e)}")

    groups = Group.objects.all()
    roles = Role.objects.all()

    # Create a mapping of group IDs to available roles
    group_roles = {}
    for group in groups:
        # Get unique roles available in this group through memberships
        available_roles = group.members.values_list("role__id", "role__name").distinct()
        group_roles[str(group.id)] = [
            {"id": role_id, "name": role_name} for role_id, role_name in available_roles
        ]

    # Prepare existing fields data for the form
    existing_fields = []
    if workflow_type.json_schema and isinstance(workflow_type.json_schema, dict):
        properties = workflow_type.json_schema.get("properties", {})
        required_fields = workflow_type.json_schema.get("required", [])

        for field_name, field_config in properties.items():
            field_data = {
                "name": field_name,
                "label": field_config.get("title", ""),
                "type": get_field_type_from_schema(field_config),
                "required": field_name in required_fields,
                "help_text": field_config.get("description", ""),
                "options": ", ".join(field_config.get("enum", []))
                if field_config.get("enum")
                else "",
            }
            existing_fields.append(field_data)

    context = {
        "workflow_type": workflow_type,
        "groups": groups,
        "roles": roles,
        "group_roles": json.dumps(group_roles),
        "existing_fields": json.dumps(existing_fields),
        "is_edit": True,
    }

    return render(request, "workflows/admin/workflow_type_edit.html", context)


def get_field_type_from_schema(field_config):
    """Convert JSON schema field type to form field type"""
    schema_type = field_config.get("type", "string")

    if schema_type == "boolean":
        return "checkbox"
    elif schema_type == "number":
        return "number"
    elif field_config.get("enum"):
        return "select"
    elif "date" in field_config.get("title", "").lower():
        if "time" in field_config.get("title", "").lower():
            return "datetime"
        return "date"
    elif "email" in field_config.get("title", "").lower():
        return "email"
    elif "url" in field_config.get("title", "").lower():
        return "url"
    elif (
        "text" in field_config.get("title", "").lower()
        or "description" in field_config.get("title", "").lower()
    ):
        return "textarea"
    else:
        return "text"


@login_required
def group_admin(request):
    """Group administration - manage groups and their hierarchies"""
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")

    groups = Group.objects.all().select_related("parent")

    search = request.GET.get("search")
    group_type = request.GET.get("group_type")

    if search:
        groups = groups.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )
    if group_type:
        groups = groups.filter(group_type=group_type)

    context = {
        "groups": groups,
    }

    return render(request, "workflows/admin/group_admin.html", context)


@login_required
def workflow_type_states(request, pk):
    """Manage workflow states for a workflow type"""
    workflow_type = get_object_or_404(WorkflowType, pk=pk)

    # Check permissions - user should be admin or have appropriate roles
    if not request.user.is_staff:
        messages.error(request, "You do not have permission to manage workflow states.")
        return redirect("admin_workflow_types")

    if request.method == "POST":
        action = request.POST.get("action")

        try:
            if action == "create":
                name = request.POST.get("name", "").strip()
                description = request.POST.get("description", "").strip()
                order = request.POST.get("order", 0)
                is_initial = request.POST.get("is_initial") == "on"
                is_terminal = request.POST.get("is_terminal") == "on"

                if not name:
                    return JsonResponse(
                        {"success": False, "error": "State name is required"}
                    )

                # If this is set as initial, unset all other initial states
                if is_initial:
                    State.objects.filter(
                        workflow_type=workflow_type, is_initial=True
                    ).update(is_initial=False)

                # If this is set as terminal, unset all other terminal states
                if is_terminal:
                    State.objects.filter(
                        workflow_type=workflow_type, is_terminal=True
                    ).update(is_terminal=False)

                state = State.objects.create(
                    workflow_type=workflow_type,
                    name=name,
                    description=description,
                    order=int(order),
                    is_initial=is_initial,
                    is_terminal=is_terminal,
                )

                return JsonResponse(
                    {
                        "success": True,
                        "state": {
                            "id": state.pk,
                            "name": state.name,
                            "description": state.description,
                            "order": state.order,
                            "is_initial": state.is_initial,
                            "is_terminal": state.is_terminal,
                        },
                    }
                )

            elif action == "get_state":
                state_id = request.POST.get("state_id")
                print(f"DEBUG GET_STATE: Received state_id: {state_id}")
                print(f"DEBUG GET_STATE: workflow_type.pk: {workflow_type.pk}")

                # First check if state exists at all
                try:
                    state_check = State.objects.get(pk=state_id)
                    print(
                        f"DEBUG GET_STATE: Found state with ID {state_id}: {state_check.name}"
                    )
                    print(
                        f"DEBUG GET_STATE: State's workflow_type: {state_check.workflow_type.pk}"
                    )
                except State.DoesNotExist:
                    print(f"DEBUG GET_STATE: No state found with ID {state_id}")
                    return JsonResponse(
                        {
                            "success": False,
                            "error": f"No state found with ID {state_id}",
                        }
                    )

                state = get_object_or_404(
                    State, pk=state_id, workflow_type=workflow_type
                )
                print("DEBUG GET_STATE: Successfully retrieved state for workflow type")

                return JsonResponse(
                    {
                        "success": True,
                        "state": {
                            "id": state.pk,
                            "name": state.name,
                            "description": state.description,
                            "order": state.order,
                            "is_initial": state.is_initial,
                            "is_terminal": state.is_terminal,
                        },
                    }
                )

            elif action == "edit":
                state_id = request.POST.get("state_id")
                print(f"DEBUG: Received state_id: {state_id}")
                print(f"DEBUG: workflow_type.pk: {workflow_type.pk}")
                print(f"DEBUG: workflow_type.name: {workflow_type.name}")

                # First check if state exists at all
                try:
                    state_check = State.objects.get(pk=state_id)
                    print(f"DEBUG: Found state with ID {state_id}: {state_check.name}")
                    print(
                        f"DEBUG: State's workflow_type: {state_check.workflow_type.pk}"
                    )
                except State.DoesNotExist:
                    print(f"DEBUG: No state found with ID {state_id}")
                    return JsonResponse(
                        {
                            "success": False,
                            "error": f"No state found with ID {state_id}",
                        }
                    )

                state = get_object_or_404(
                    State, pk=state_id, workflow_type=workflow_type
                )
                print("DEBUG: Successfully retrieved state for workflow type")

                name = request.POST.get("name", "").strip()
                description = request.POST.get("description", "").strip()
                order = request.POST.get("order", 0)
                is_initial = request.POST.get("is_initial") == "on"
                is_terminal = request.POST.get("is_terminal") == "on"

                # Debug logging
                print(
                    f"Edit state - ID: {state_id}, Name: {name}, is_initial: {is_initial}, is_terminal: {is_terminal}"
                )

                if not name:
                    return JsonResponse(
                        {"success": False, "error": "State name is required"}
                    )

                # If this is set as initial, unset all other initial states
                if is_initial and not state.is_initial:
                    State.objects.filter(
                        workflow_type=workflow_type, is_initial=True
                    ).update(is_initial=False)

                # If this is set as terminal, unset all other terminal states
                if is_terminal and not state.is_terminal:
                    State.objects.filter(
                        workflow_type=workflow_type, is_terminal=True
                    ).update(is_terminal=False)

                state.name = name
                state.description = description
                state.order = int(order)
                state.is_initial = is_initial
                state.is_terminal = is_terminal

                try:
                    state.save()
                    print(f"State saved successfully: {state.name}")
                except Exception as e:
                    print(f"Error saving state: {str(e)}")
                    return JsonResponse(
                        {"success": False, "error": f"Error saving state: {str(e)}"}
                    )

                return JsonResponse(
                    {
                        "success": True,
                        "state": {
                            "id": state.pk,
                            "name": state.name,
                            "description": state.description,
                            "order": state.order,
                            "is_initial": state.is_initial,
                            "is_terminal": state.is_terminal,
                        },
                    }
                )

            elif action == "delete":
                state_id = request.POST.get("state_id")
                state = get_object_or_404(
                    State, pk=state_id, workflow_type=workflow_type
                )

                # Check if state is being used by any transitions
                transition_count = Transition.objects.filter(
                    Q(from_state=state) | Q(to_state=state)
                ).count()

                if transition_count > 0:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": f"Cannot delete state: it is used by {transition_count} transition(s)",
                        }
                    )

                state.delete()
                return JsonResponse({"success": True})

        except Exception as e:
            print(f"Unexpected error in workflow_type_states: {str(e)}")
            return JsonResponse(
                {"success": False, "error": f"Unexpected error: {str(e)}"}
            )

    # GET request
    states = State.objects.filter(workflow_type=workflow_type).order_by("order", "name")

    context = {
        "workflow_type": workflow_type,
        "states": states,
    }

    return render(request, "workflows/admin/workflow_type_states.html", context)


@login_required
def workflow_type_transitions(request, pk):
    """Manage workflow transitions for a workflow type"""
    workflow_type = get_object_or_404(WorkflowType, pk=pk)

    # Check permissions - user should be admin or have appropriate roles
    if not request.user.is_staff:
        messages.error(
            request, "You do not have permission to manage workflow transitions."
        )
        return redirect("admin_workflow_types")

    if request.method == "POST":
        action = request.POST.get("action")

        try:
            if action == "create":
                name = request.POST.get("name", "").strip()
                from_state_id = request.POST.get("from_state")
                to_state_id = request.POST.get("to_state")
                role_ids = request.POST.getlist("roles")

                if not name:
                    return JsonResponse(
                        {"success": False, "error": "Transition name is required"}
                    )

                if not from_state_id or not to_state_id:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Both from and to states are required",
                        }
                    )

                if from_state_id == to_state_id:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "From and to states cannot be the same",
                        }
                    )

                from_state = get_object_or_404(
                    State, pk=from_state_id, workflow_type=workflow_type
                )
                to_state = get_object_or_404(
                    State, pk=to_state_id, workflow_type=workflow_type
                )

                transition = Transition.objects.create(
                    workflow_type=workflow_type,
                    name=name,
                    from_state=from_state,
                    to_state=to_state,
                )

                # Add allowed roles
                if role_ids:
                    roles = Role.objects.filter(id__in=role_ids)
                    transition.allowed_roles.set(roles)

                return JsonResponse(
                    {
                        "success": True,
                        "transition": {
                            "id": transition.pk,
                            "name": transition.name,
                            "from_state": transition.from_state.name,
                            "to_state": transition.to_state.name,
                            "roles": [
                                role.name for role in transition.allowed_roles.all()
                            ],
                        },
                    }
                )

            elif action == "get_transition":
                transition_id = request.POST.get("transition_id")
                transition = get_object_or_404(
                    Transition, pk=transition_id, workflow_type=workflow_type
                )

                return JsonResponse(
                    {
                        "success": True,
                        "transition": {
                            "id": transition.pk,
                            "name": transition.name,
                            "from_state": transition.from_state.pk,
                            "to_state": transition.to_state.pk,
                            "roles": [
                                role.pk for role in transition.allowed_roles.all()
                            ],
                        },
                    }
                )

            elif action == "edit":
                transition_id = request.POST.get("transition_id")
                transition = get_object_or_404(
                    Transition, pk=transition_id, workflow_type=workflow_type
                )

                name = request.POST.get("name", "").strip()
                from_state_id = request.POST.get("from_state")
                to_state_id = request.POST.get("to_state")
                role_ids = request.POST.getlist("roles")

                if not name:
                    return JsonResponse(
                        {"success": False, "error": "Transition name is required"}
                    )

                if not from_state_id or not to_state_id:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Both from and to states are required",
                        }
                    )

                if from_state_id == to_state_id:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "From and to states cannot be the same",
                        }
                    )

                from_state = get_object_or_404(
                    State, pk=from_state_id, workflow_type=workflow_type
                )
                to_state = get_object_or_404(
                    State, pk=to_state_id, workflow_type=workflow_type
                )

                transition.name = name
                transition.from_state = from_state
                transition.to_state = to_state
                transition.save()

                # Update allowed roles
                if role_ids:
                    roles = Role.objects.filter(id__in=role_ids)
                    transition.allowed_roles.set(roles)
                else:
                    transition.allowed_roles.clear()

                return JsonResponse(
                    {
                        "success": True,
                        "transition": {
                            "id": transition.pk,
                            "name": transition.name,
                            "from_state": transition.from_state.name,
                            "to_state": transition.to_state.name,
                            "roles": [
                                role.name for role in transition.allowed_roles.all()
                            ],
                        },
                    }
                )

            elif action == "delete":
                transition_id = request.POST.get("transition_id")
                transition = get_object_or_404(
                    Transition, pk=transition_id, workflow_type=workflow_type
                )

                transition.delete()
                return JsonResponse({"success": True})

        except Exception as e:
            print(f"Error in workflow_type_transitions: {str(e)}")
            return JsonResponse({"success": False, "error": f"Error: {str(e)}"})

    # GET request
    transitions = Transition.objects.filter(workflow_type=workflow_type).order_by(
        "name"
    )
    states = State.objects.filter(workflow_type=workflow_type).order_by("order", "name")

    # Get available roles from group owner
    available_roles = Role.objects.filter(id__in=workflow_type.group_owner_roles())

    context = {
        "workflow_type": workflow_type,
        "transitions": transitions,
        "states": states,
        "available_roles": available_roles,
    }

    return render(request, "workflows/admin/workflow_type_transitions.html", context)


@login_required
def role_admin(request):
    """Role administration - manage roles and their permissions"""
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard")

    roles = Role.objects.all()

    search = request.GET.get("search")
    if search:
        roles = roles.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )

    context = {
        "roles": roles,
    }

    return render(request, "workflows/admin/role_admin.html", context)
