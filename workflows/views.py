from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Case, Count, IntegerField, Q, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (
    Comment,
    Event,
    EventAttendance,
    EventType,
    Group,
    GroupMembership,
    Notification,
    Role,
    State,
    Transition,
    User,
    Venue,
    Workflow,
    WorkflowTransitionLog,
    WorkflowType,
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
        Q(group__in=user_groups) | Q(referred_to__in=user_groups)
    ).select_related("workflow_type", "current_state", "group", "owner")

    # Statistics
    total_workflows = workflows.count()
    my_workflows = workflows.filter(owner=user).count()
    assigned_to_me = workflows.filter(assigned_to=user).count()
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

    # Base queryset
    workflows = Workflow.objects.filter(
        Q(group__in=user_groups) | Q(referred_to__in=user_groups)
    ).select_related("workflow_type", "current_state", "group", "owner", "assigned_to")

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
        workflows = workflows.filter(group_id=group)
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

    context = {
        "workflow": workflow,
        "available_transitions": available_transitions,
        "transition_logs": transition_logs,
        "comments": comments,
    }

    return render(request, "workflows/workflow_detail.html", context)


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
    groups = Group.objects.filter(id__in=user_groups).select_related(
        "group_type", "parent"
    )

    context = {
        "groups": groups,
    }

    return render(request, "workflows/group_list.html", context)


@login_required
def group_detail(request, pk):
    """Detailed view of a group"""
    group = get_object_or_404(Group, pk=pk)

    # Get members
    memberships = group.memberships.filter(is_active=True).select_related(
        "user", "role"
    )

    # Get workflows
    workflows = group.workflows.all().select_related("workflow_type", "current_state")[
        :10
    ]

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
        Q(group__in=user_groups) | Q(referred_to__in=user_groups)
    ).select_related("workflow_type", "current_state", "group", "owner")

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
        workflows.values("group__name")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    # Overdue workflows
    overdue = workflows.filter(
        deadline__lt=timezone.now(), current_state__is_terminal=False
    ).count()

    # Workflows created this month
    from datetime import datetime

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
