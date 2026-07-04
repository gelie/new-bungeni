import logging

from background_task import background
from django.core.mail import send_mail
from django.utils import timezone

from workflows.models import UserDelegation

logger = logging.getLogger(__name__)


@background(schedule=0)
def update_event_statuses() -> dict:
    """
    Automatically update event statuses based on scheduled times.
    - Transitions 'scheduled' events to 'in_progress' when start_datetime is reached
    - Transitions 'in_progress' events to 'completed' when end_datetime is reached

    Returns a dict with counts of updated events.
    """
    from .models import Event

    return Event.update_automatic_statuses()


@background(schedule=0)
def send_transition_alert(
    workflow_id: str,
    workflow_title: str,
    workflow_type_name: str,
    transition_name: str,
    from_state_name: str,
    to_state_name: str,
    triggered_by: str,
    recipient_emails: list,
    site_url: str,
) -> int:
    """
    Send email alerts to group members whose roles are listed in
    Transition.notify_roles when a workflow transition occurs.

    All arguments are JSON-serializable primitives so they round-trip
    safely through the task queue.

    Returns the number of emails sent.
    """
    if not recipient_emails:
        return 0

    subject = (
        f"[PWMS] {workflow_type_name}: '{workflow_title}' moved to {to_state_name}"
    )

    message = (
        f"A workflow transition has occurred.\n\n"
        f"Workflow:    {workflow_title}\n"
        f"Type:        {workflow_type_name}\n"
        f"Transition:  {transition_name}\n"
        f"From state:  {from_state_name}\n"
        f"To state:    {to_state_name}\n"
        f"Actioned by: {triggered_by}\n\n"
        f"View the workflow:\n"
        f"{site_url}/workflows/{workflow_id}/\n\n"
        f"--\n"
        f"This is an automated notification from Parliament Workflow System."
    )

    html_message = (
        f"<p>A workflow transition has occurred.</p>"
        f"<table style='border-collapse:collapse;font-family:sans-serif;font-size:14px'>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Workflow</td>"
        f"<td style='padding:4px 0'><strong>{workflow_title}</strong></td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Type</td>"
        f"<td style='padding:4px 0'>{workflow_type_name}</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Transition</td>"
        f"<td style='padding:4px 0'>{transition_name}</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>From state</td>"
        f"<td style='padding:4px 0'>{from_state_name}</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>To state</td>"
        f"<td style='padding:4px 0'><strong>{to_state_name}</strong></td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Actioned by</td>"
        f"<td style='padding:4px 0'>{triggered_by}</td></tr>"
        f"</table>"
        f"<p style='margin-top:16px'>"
        f"<a href='{site_url}/workflows/{workflow_id}/' "
        f"style='background:#1d4ed8;color:#fff;padding:8px 16px;border-radius:6px;"
        f"text-decoration:none;font-size:14px'>View Workflow</a></p>"
        f"<p style='margin-top:24px;font-size:12px;color:#9ca3af'>"
        f"This is an automated notification from Parliament Workflow System.</p>"
    )

    sent = send_mail(
        subject=subject,
        message=message,
        from_email=None,
        recipient_list=recipient_emails,
        html_message=html_message,
        fail_silently=True,
    )
    return sent


@background(schedule=0)
def notify_overdue_workflows(
    site_url: str = "",
    workflow_id: str | None = None,
    force: bool = False,
) -> dict:
    """
    Scan all non-terminal workflows that are past their deadline and:
      - Create an in-app notification for the owner and assigned_to user
        (skipped if an overdue notification was already sent today).
      - Send a single email to the owner (and assigned_to if different).

    Pass workflow_id to restrict processing to a single workflow.
    Pass force=True to bypass the overdue/terminal-state check and the
    today-already-notified deduplication (useful for testing).

    Returns a summary dict: {"workflows_processed": N, "notifications_created": N, "emails_sent": N}
    """
    from .models import Notification, Workflow

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if force and workflow_id is not None:
        overdue_qs = Workflow.objects.filter(pk=workflow_id).select_related(
            "workflow_type", "current_state", "owner", "assigned_to"
        )
    else:
        overdue_qs = (
            Workflow.objects.filter(
                deadline__lt=now,
                current_state__is_terminal=False,
            )
            .select_related(
                "workflow_type",
                "current_state",
                "owner",
                "assigned_to",
            )
            .exclude(deadline__isnull=True)
        )
        if workflow_id is not None:
            overdue_qs = overdue_qs.filter(pk=workflow_id)

    notifications_created = 0
    emails_sent = 0

    for workflow in overdue_qs:
        days_overdue = (now - workflow.deadline).days
        overdue_label = f"{days_overdue} day{'s' if days_overdue != 1 else ''} overdue"

        title = f"{workflow.workflow_type.name}: '{workflow.title}' is {overdue_label}"
        message = (
            f"The workflow '{workflow.title}' ({workflow.workflow_type.name}) "
            f"is {overdue_label}. "
            f"Current state: {workflow.current_state.name}. "
            f"Deadline was: {workflow.deadline.strftime('%Y-%m-%d %H:%M')}."
        )

        # Collect unique users to notify (owner + assigned_to)
        users_to_notify = {workflow.owner}
        if workflow.assigned_to and workflow.assigned_to != workflow.owner:
            users_to_notify.add(workflow.assigned_to)

        for user in users_to_notify:
            # Skip if already notified today for this workflow (unless force=True)
            if not force:
                already_notified = Notification.objects.filter(
                    user=user,
                    verb=Notification.VERB_OVERDUE,
                    workflow=workflow,
                    created_at__gte=today_start,
                ).exists()
                if already_notified:
                    continue

            Notification.objects.create(
                user=user,
                verb=Notification.VERB_OVERDUE,
                title=title,
                message=message,
                workflow=workflow,
            )
            notifications_created += 1

            # Send email if user has an address
            if user.email:
                email_subject = (
                    f"[PWS] Overdue: {workflow.workflow_type.name} — {workflow.title}"
                )
                plain = (
                    f"This is a reminder that the following workflow is overdue.\n\n"
                    f"Workflow:      {workflow.title}\n"
                    f"Type:          {workflow.workflow_type.name}\n"
                    f"Current state: {workflow.current_state.name}\n"
                    f"Deadline:      {workflow.deadline.strftime('%Y-%m-%d %H:%M')}\n"
                    f"Overdue by:    {overdue_label}\n\n"
                    + (
                        f"View: {site_url}/workflows/{workflow.pk}/\n\n"
                        if site_url
                        else ""
                    )
                    + "--\nThis is an automated notification from Parliament Workflow System."
                )
                html_message = (
                    f"<p>This is a reminder that the following workflow is <strong>overdue</strong>.</p>"
                    f"<table style='border-collapse:collapse;font-family:sans-serif;font-size:14px'>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Workflow</td>"
                    f"<td style='padding:4px 0'><strong>{workflow.title}</strong></td></tr>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Type</td>"
                    f"<td style='padding:4px 0'>{workflow.workflow_type.name}</td></tr>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Current state</td>"
                    f"<td style='padding:4px 0'>{workflow.current_state.name}</td></tr>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Deadline</td>"
                    f"<td style='padding:4px 0;color:#dc2626'><strong>{workflow.deadline.strftime('%Y-%m-%d %H:%M')}</strong></td></tr>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Overdue by</td>"
                    f"<td style='padding:4px 0;color:#dc2626'>{overdue_label}</td></tr>"
                    f"</table>"
                    + (
                        f"<p style='margin-top:16px'>"
                        f"<a href='{site_url}/workflows/{workflow.pk}/' "
                        f"style='background:#1d4ed8;color:#fff;padding:8px 16px;border-radius:6px;"
                        f"text-decoration:none;font-size:14px'>View Workflow</a></p>"
                        if site_url
                        else ""
                    )
                    + "<p style='margin-top:24px;font-size:12px;color:#9ca3af'>"
                    "This is an automated notification from Parliament Workflow System.</p>"
                )
                send_mail(
                    subject=email_subject,
                    message=plain,
                    from_email=None,
                    recipient_list=[user.email],
                    html_message=html_message,
                    fail_silently=True,
                )
                emails_sent += 1

    return {
        "workflows_processed": overdue_qs.count(),
        "notifications_created": notifications_created,
        "emails_sent": emails_sent,
    }


@background(schedule=0)
def notify_pending_deadlines(
    site_url: str = "",
    workflow_id: str | None = None,
    days_before: int = 3,
    force: bool = False,
) -> dict:
    """
    Scan all non-terminal workflows with deadlines approaching within N days and:
      - Create an in-app notification for the owner and assigned_to user
        (skipped if a pending notification was already sent today).
      - Send a single email to the owner (and assigned_to if different).

    Pass workflow_id to restrict processing to a single workflow.
    Pass days_before to customize the warning period (default: 3 days).
    Pass force=True to bypass the today-already-notified deduplication (useful for testing).

    Returns a summary dict: {"workflows_processed": N, "notifications_created": N, "emails_sent": N}
    """
    from datetime import timedelta

    from .models import Notification, Workflow

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    deadline_threshold = now + timedelta(days=days_before)

    if force and workflow_id is not None:
        pending_qs = Workflow.objects.filter(pk=workflow_id).select_related(
            "workflow_type", "current_state", "owner", "assigned_to"
        )
    else:
        pending_qs = (
            Workflow.objects.filter(
                deadline__gte=now,
                deadline__lte=deadline_threshold,
                current_state__is_terminal=False,
            )
            .select_related(
                "workflow_type",
                "current_state",
                "owner",
                "assigned_to",
            )
            .exclude(deadline__isnull=True)
        )
        if workflow_id is not None:
            pending_qs = pending_qs.filter(pk=workflow_id)

    notifications_created = 0
    emails_sent = 0

    for workflow in pending_qs:
        time_remaining = workflow.deadline - now
        days_remaining = time_remaining.days
        hours_remaining = time_remaining.seconds // 3600

        if days_remaining > 0:
            time_label = f"{days_remaining} day{'s' if days_remaining != 1 else ''}"
        elif hours_remaining > 0:
            time_label = f"{hours_remaining} hour{'s' if hours_remaining != 1 else ''}"
        else:
            time_label = "less than 1 hour"

        title = f"{workflow.workflow_type.name}: '{workflow.title}' deadline in {time_label}"
        message = (
            f"The workflow '{workflow.title}' ({workflow.workflow_type.name}) "
            f"has a deadline approaching in {time_label}. "
            f"Current state: {workflow.current_state.name}. "
            f"Deadline: {workflow.deadline.strftime('%Y-%m-%d %H:%M')}."
        )

        # Collect unique users to notify (owner + assigned_to)
        users_to_notify = {workflow.owner}
        if workflow.assigned_to and workflow.assigned_to != workflow.owner:
            users_to_notify.add(workflow.assigned_to)

        for user in users_to_notify:
            # Skip if already notified today for this workflow (unless force=True)
            if not force:
                already_notified = Notification.objects.filter(
                    user=user,
                    verb=Notification.VERB_PENDING,
                    workflow=workflow,
                    created_at__gte=today_start,
                ).exists()
                if already_notified:
                    continue

            Notification.objects.create(
                user=user,
                verb=Notification.VERB_PENDING,
                title=title,
                message=message,
                workflow=workflow,
            )
            notifications_created += 1

            # Send email if user has an address
            if user.email:
                email_subject = f"[PWMS] Deadline Approaching: {workflow.workflow_type.name} — {workflow.title}"
                plain = (
                    f"This is a reminder that the following workflow has a deadline approaching.\n\n"
                    f"Workflow:      {workflow.title}\n"
                    f"Type:          {workflow.workflow_type.name}\n"
                    f"Current state: {workflow.current_state.name}\n"
                    f"Deadline:      {workflow.deadline.strftime('%Y-%m-%d %H:%M')}\n"
                    f"Time remaining: {time_label}\n\n"
                    + (
                        f"View: {site_url}/workflows/{workflow.pk}/\n\n"
                        if site_url
                        else ""
                    )
                    + "--\nThis is an automated notification from Parliament Workflow System."
                )
                html_message = (
                    f"<p>This is a reminder that the following workflow has a <strong>deadline approaching</strong>.</p>"
                    f"<table style='border-collapse:collapse;font-family:sans-serif;font-size:14px'>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Workflow</td>"
                    f"<td style='padding:4px 0'><strong>{workflow.title}</strong></td></tr>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Type</td>"
                    f"<td style='padding:4px 0'>{workflow.workflow_type.name}</td></tr>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Current state</td>"
                    f"<td style='padding:4px 0'>{workflow.current_state.name}</td></tr>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Deadline</td>"
                    f"<td style='padding:4px 0;color:#f59e0b'><strong>{workflow.deadline.strftime('%Y-%m-%d %H:%M')}</strong></td></tr>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Time remaining</td>"
                    f"<td style='padding:4px 0;color:#f59e0b'>{time_label}</td></tr>"
                    f"</table>"
                    + (
                        f"<p style='margin-top:16px'>"
                        f"<a href='{site_url}/workflows/{workflow.pk}/' "
                        f"style='background:#1d4ed8;color:#fff;padding:8px 16px;border-radius:6px;"
                        f"text-decoration:none;font-size:14px'>View Workflow</a></p>"
                        if site_url
                        else ""
                    )
                    + "<p style='margin-top:24px;font-size:12px;color:#9ca3af'>"
                    "This is an automated notification from Parliament Workflow System.</p>"
                )
                send_mail(
                    subject=email_subject,
                    message=plain,
                    from_email=None,
                    recipient_list=[user.email],
                    html_message=html_message,
                    fail_silently=True,
                )
                emails_sent += 1

    return {
        "workflows_processed": pending_qs.count(),
        "notifications_created": notifications_created,
        "emails_sent": emails_sent,
    }


@background(schedule=0)
def transition_overdue_to_followup(
    workflow_id: str | None = None,
    auto_transition: bool = True,
) -> dict:
    """
    Scan all overdue workflows and automatically transition them to a 'Follow-up' state
    if such a transition exists from their current state.

    This task should be run after notify_overdue_workflows to ensure users are notified
    before the automatic transition occurs.

    Pass workflow_id to restrict processing to a single workflow.
    Pass auto_transition=False to only report what would be transitioned without making changes.

    Returns a summary dict: {"workflows_checked": N, "workflows_transitioned": N, "transitions_failed": N}
    """
    from django.contrib.contenttypes.models import ContentType

    from .models import AuditLog, State, Transition, Workflow, WorkflowTransitionLog

    now = timezone.now()

    # Find overdue workflows
    if workflow_id is not None:
        overdue_qs = Workflow.objects.filter(
            pk=workflow_id,
            deadline__lt=now,
            current_state__is_terminal=False,
        ).select_related("workflow_type", "current_state", "owner", "assigned_to")
    else:
        overdue_qs = (
            Workflow.objects.filter(
                deadline__lt=now,
                current_state__is_terminal=False,
            )
            .select_related("workflow_type", "current_state", "owner", "assigned_to")
            .exclude(deadline__isnull=True)
        )

    workflows_transitioned = 0
    transitions_failed = 0

    for workflow in overdue_qs:
        # Look for a 'Follow-up' or 'Follow Up' state in this workflow type
        followup_state = State.objects.filter(
            workflow_type=workflow.workflow_type,
            name__icontains="follow",
        ).first()

        if not followup_state:
            transitions_failed += 1
            continue

        # Check if there's a valid transition from current state to follow-up state
        transition = Transition.objects.filter(
            workflow_type=workflow.workflow_type,
            from_state=workflow.current_state,
            to_state=followup_state,
        ).first()

        if not transition:
            transitions_failed += 1
            continue

        if auto_transition:
            from_state = workflow.current_state

            # Log the transition
            WorkflowTransitionLog.objects.create(
                workflow=workflow,
                transition=transition,
                from_state=from_state,
                to_state=followup_state,
                user=workflow.owner,
                comment="Automatic transition due to overdue deadline.",
            )

            # Audit log
            AuditLog.objects.create(
                content_type=ContentType.objects.get_for_model(workflow),
                object_id=workflow.pk,
                action="auto_transition",
                user=workflow.owner,
                ip_address="system",
                changes={
                    "transition": transition.name,
                    "from_state": from_state.name,
                    "to_state": followup_state.name,
                    "reason": "Automatic transition due to overdue deadline",
                },
            )

            # Update workflow state
            workflow.current_state = followup_state
            workflow.save()

            workflows_transitioned += 1

    return {
        "workflows_checked": overdue_qs.count(),
        "workflows_transitioned": workflows_transitioned,
        "transitions_failed": transitions_failed,
    }


@background(schedule=0)
def check_delegation_expirations() -> dict:
    """
    Check for expired delegations and expire them with notifications.

    This task:
      - Finds active delegations where end_date has passed
      - Expires them and sends notifications to both delegator and delegatee
      - Sends email notifications to both parties
      - Logs all actions for audit purposes

    Returns a dict with counts of processed delegations and notifications.
    """
    now = timezone.now()

    # Find active delegations that should be expired
    expired_delegations = UserDelegation.objects.filter(
        status="active", end_date__lte=now
    )

    expired_count = 0
    notifications_created = 0
    emails_sent = 0
    errors = 0

    logger.info(f"Checking {expired_delegations.count()} delegations for expiration")

    for delegation in expired_delegations:
        try:
            delegator_name = (
                delegation.delegator.get_full_name() or delegation.delegator.username
            )
            delegatee_name = (
                delegation.delegatee.get_full_name() or delegation.delegatee.username
            )

            logger.info(
                f"Expiring delegation: {delegator_name} -> {delegatee_name} "
                f"(ID: {delegation.pk}, End: {delegation.end_date})"
            )

            # Expire the delegation (this sends notifications)
            delegation.expire_delegation()
            expired_count += 1

            # Count notifications and emails
            notifications_created += 2  # One for delegatee, one for delegator
            emails_sent += 2  # One email to each party

            logger.info(f"Successfully expired delegation {delegation.pk}")

        except Exception as e:
            errors += 1
            logger.error(f"Failed to expire delegation {delegation.pk}: {e}")

    result = {
        "delegations_checked": expired_delegations.count(),
        "delegations_expired": expired_count,
        "notifications_created": notifications_created,
        "emails_sent": emails_sent,
        "errors": errors,
    }

    logger.info(
        f"Delegation expiration check complete: "
        f"{expired_count} expired, {notifications_created} notifications, {emails_sent} emails, {errors} errors"
    )

    return result


# ============================================================================
# UNDECORATED VERSIONS FOR SYNCHRONOUS EXECUTION (Management Commands)
# ============================================================================


def _update_event_statuses_sync() -> dict:
    """Undecorated version for synchronous execution"""
    from .models import Event

    return Event.update_automatic_statuses()


def _send_transition_alert_sync(
    workflow_id: str,
    workflow_title: str,
    workflow_type_name: str,
    transition_name: str,
    from_state_name: str,
    to_state_name: str,
    triggered_by: str,
    recipient_emails: list,
    site_url: str,
) -> int:
    """Undecorated version for synchronous execution"""
    if not recipient_emails:
        return 0

    subject = (
        f"[PWMS] {workflow_type_name}: '{workflow_title}' moved to {to_state_name}"
    )

    message = (
        f"A workflow transition has occurred.\n\n"
        f"Workflow:    {workflow_title}\n"
        f"Type:        {workflow_type_name}\n"
        f"Transition:  {transition_name}\n"
        f"From state:  {from_state_name}\n"
        f"To state:    {to_state_name}\n"
        f"Actioned by: {triggered_by}\n\n"
        f"View the workflow:\n"
        f"{site_url}/workflows/{workflow_id}/\n\n"
        f"--\n"
        f"This is an automated notification from Parliament Workflow System."
    )

    html_message = (
        f"<p>A workflow transition has occurred.</p>"
        f"<table style='border-collapse:collapse;font-family:sans-serif;font-size:14px'>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Workflow</td>"
        f"<td style='padding:4px 0'><strong>{workflow_title}</strong></td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Type</td>"
        f"<td style='padding:4px 0'>{workflow_type_name}</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Transition</td>"
        f"<td style='padding:4px 0'>{transition_name}</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>From state</td>"
        f"<td style='padding:4px 0'>{from_state_name}</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>To state</td>"
        f"<td style='padding:4px 0'><strong>{to_state_name}</strong></td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Actioned by</td>"
        f"<td style='padding:4px 0'>{triggered_by}</td></tr>"
        f"</table>"
        f"<p style='margin-top:16px'>"
        f"<a href='{site_url}/workflows/{workflow_id}/' "
        f"style='background:#1d4ed8;color:#fff;padding:8px 16px;border-radius:6px;"
        f"text-decoration:none;font-size:14px'>View Workflow</a></p>"
        f"<p style='margin-top:24px;font-size:12px;color:#9ca3af'>"
        f"This is an automated notification from Parliament Workflow System.</p>"
    )

    sent = send_mail(
        subject=subject,
        message=message,
        from_email=None,
        recipient_list=recipient_emails,
        html_message=html_message,
        fail_silently=True,
    )
    return sent


def _notify_overdue_workflows_sync(
    site_url: str = "",
    workflow_id: str | None = None,
    force: bool = False,
) -> dict:
    """Undecorated version for synchronous execution"""
    from .models import Notification, Workflow

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if force and workflow_id is not None:
        overdue_qs = Workflow.objects.filter(pk=workflow_id).select_related(
            "workflow_type", "current_state", "owner", "assigned_to"
        )
    else:
        overdue_qs = (
            Workflow.objects.filter(
                deadline__lt=now,
                current_state__is_terminal=False,
            )
            .select_related(
                "workflow_type",
                "current_state",
                "owner",
                "assigned_to",
            )
            .exclude(deadline__isnull=True)
        )
        if workflow_id is not None:
            overdue_qs = overdue_qs.filter(pk=workflow_id)

    notifications_created = 0
    emails_sent = 0

    for workflow in overdue_qs:
        days_overdue = (now - workflow.deadline).days
        overdue_label = f"{days_overdue} day{'s' if days_overdue != 1 else ''} overdue"

        title = f"{workflow.workflow_type.name}: '{workflow.title}' is {overdue_label}"
        message = (
            f"The workflow '{workflow.title}' ({workflow.workflow_type.name}) "
            f"is {overdue_label}. "
            f"Current state: {workflow.current_state.name}. "
            f"Deadline was: {workflow.deadline.strftime('%Y-%m-%d %H:%M')}."
        )

        # Collect unique users to notify (owner + assigned_to)
        users_to_notify = {workflow.owner}
        if workflow.assigned_to and workflow.assigned_to != workflow.owner:
            users_to_notify.add(workflow.assigned_to)

        for user in users_to_notify:
            # Skip if already notified today for this workflow (unless force=True)
            if not force:
                already_notified = Notification.objects.filter(
                    user=user,
                    verb=Notification.VERB_OVERDUE,
                    workflow=workflow,
                    created_at__gte=today_start,
                ).exists()
                if already_notified:
                    continue

            Notification.objects.create(
                user=user,
                verb=Notification.VERB_OVERDUE,
                title=title,
                message=message,
                workflow=workflow,
            )
            notifications_created += 1

            # Send email if user has an address
            if user.email:
                email_subject = (
                    f"[PWS] Overdue: {workflow.workflow_type.name} — {workflow.title}"
                )
                plain = (
                    f"This is a reminder that the following workflow is overdue.\n\n"
                    f"Workflow:      {workflow.title}\n"
                    f"Type:          {workflow.workflow_type.name}\n"
                    f"Current state: {workflow.current_state.name}\n"
                    f"Deadline:      {workflow.deadline.strftime('%Y-%m-%d %H:%M')}\n"
                    f"Overdue by:    {overdue_label}\n\n"
                    + (
                        f"View: {site_url}/workflows/{workflow.pk}/\n\n"
                        if site_url
                        else ""
                    )
                    + "--\nThis is an automated notification from Parliament Workflow System."
                )
                html_message = (
                    f"<p>This is a reminder that the following workflow is <strong>overdue</strong>.</p>"
                    f"<table style='border-collapse:collapse;font-family:sans-serif;font-size:14px'>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Workflow</td>"
                    f"<td style='padding:4px 0'><strong>{workflow.title}</strong></td></tr>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Type</td>"
                    f"<td style='padding:4px 0'>{workflow.workflow_type.name}</td></tr>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Current state</td>"
                    f"<td style='padding:4px 0'>{workflow.current_state.name}</td></tr>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Deadline</td>"
                    f"<td style='padding:4px 0;color:#dc2626'><strong>{workflow.deadline.strftime('%Y-%m-%d %H:%M')}</strong></td></tr>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Overdue by</td>"
                    f"<td style='padding:4px 0;color:#dc2626'>{overdue_label}</td></tr>"
                    f"</table>"
                    + (
                        f"<p style='margin-top:16px'>"
                        f"<a href='{site_url}/workflows/{workflow.pk}/' "
                        f"style='background:#1d4ed8;color:#fff;padding:8px 16px;border-radius:6px;"
                        f"text-decoration:none;font-size:14px'>View Workflow</a></p>"
                        if site_url
                        else ""
                    )
                    + "<p style='margin-top:24px;font-size:12px;color:#9ca3af'>"
                    "This is an automated notification from Parliament Workflow System.</p>"
                )
                send_mail(
                    subject=email_subject,
                    message=plain,
                    from_email=None,
                    recipient_list=[user.email],
                    html_message=html_message,
                    fail_silently=True,
                )
                emails_sent += 1

    return {
        "workflows_processed": overdue_qs.count(),
        "notifications_created": notifications_created,
        "emails_sent": emails_sent,
    }


def _notify_pending_deadlines_sync(
    site_url: str = "",
    workflow_id: str | None = None,
    days_before: int = 3,
    force: bool = False,
) -> dict:
    """Undecorated version for synchronous execution"""
    from datetime import timedelta

    from .models import Notification, Workflow

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    deadline_threshold = now + timedelta(days=days_before)

    if force and workflow_id is not None:
        pending_qs = Workflow.objects.filter(pk=workflow_id).select_related(
            "workflow_type", "current_state", "owner", "assigned_to"
        )
    else:
        pending_qs = (
            Workflow.objects.filter(
                deadline__gte=now,
                deadline__lte=deadline_threshold,
                current_state__is_terminal=False,
            )
            .select_related(
                "workflow_type",
                "current_state",
                "owner",
                "assigned_to",
            )
            .exclude(deadline__isnull=True)
        )
        if workflow_id is not None:
            pending_qs = pending_qs.filter(pk=workflow_id)

    notifications_created = 0
    emails_sent = 0

    for workflow in pending_qs:
        time_remaining = workflow.deadline - now
        days_remaining = time_remaining.days
        hours_remaining = time_remaining.seconds // 3600

        if days_remaining > 0:
            time_label = f"{days_remaining} day{'s' if days_remaining != 1 else ''}"
        elif hours_remaining > 0:
            time_label = f"{hours_remaining} hour{'s' if hours_remaining != 1 else ''}"
        else:
            time_label = "less than 1 hour"

        title = f"{workflow.workflow_type.name}: '{workflow.title}' deadline in {time_label}"
        message = (
            f"The workflow '{workflow.title}' ({workflow.workflow_type.name}) "
            f"has a deadline approaching in {time_label}. "
            f"Current state: {workflow.current_state.name}. "
            f"Deadline: {workflow.deadline.strftime('%Y-%m-%d %H:%M')}."
        )

        # Collect unique users to notify (owner + assigned_to)
        users_to_notify = {workflow.owner}
        if workflow.assigned_to and workflow.assigned_to != workflow.owner:
            users_to_notify.add(workflow.assigned_to)

        for user in users_to_notify:
            # Skip if already notified today for this workflow (unless force=True)
            if not force:
                already_notified = Notification.objects.filter(
                    user=user,
                    verb=Notification.VERB_PENDING,
                    workflow=workflow,
                    created_at__gte=today_start,
                ).exists()
                if already_notified:
                    continue

            Notification.objects.create(
                user=user,
                verb=Notification.VERB_PENDING,
                title=title,
                message=message,
                workflow=workflow,
            )
            notifications_created += 1

            # Send email if user has an address
            if user.email:
                email_subject = f"[PWMS] Deadline Approaching: {workflow.workflow_type.name} — {workflow.title}"
                plain = (
                    f"This is a reminder that the following workflow has a deadline approaching.\n\n"
                    f"Workflow:      {workflow.title}\n"
                    f"Type:          {workflow.workflow_type.name}\n"
                    f"Current state: {workflow.current_state.name}\n"
                    f"Deadline:      {workflow.deadline.strftime('%Y-%m-%d %H:%M')}\n"
                    f"Time remaining: {time_label}\n\n"
                    + (
                        f"View: {site_url}/workflows/{workflow.pk}/\n\n"
                        if site_url
                        else ""
                    )
                    + "--\nThis is an automated notification from Parliament Workflow System."
                )
                html_message = (
                    f"<p>This is a reminder that the following workflow has a <strong>deadline approaching</strong>.</p>"
                    f"<table style='border-collapse:collapse;font-family:sans-serif;font-size:14px'>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Workflow</td>"
                    f"<td style='padding:4px 0'><strong>{workflow.title}</strong></td></tr>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Type</td>"
                    f"<td style='padding:4px 0'>{workflow.workflow_type.name}</td></tr>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Current state</td>"
                    f"<td style='padding:4px 0'>{workflow.current_state.name}</td></tr>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Deadline</td>"
                    f"<td style='padding:4px 0;color:#f59e0b'><strong>{workflow.deadline.strftime('%Y-%m-%d %H:%M')}</strong></td></tr>"
                    f"<tr><td style='padding:4px 12px 4px 0;color:#6b7280'>Time remaining</td>"
                    f"<td style='padding:4px 0;color:#f59e0b'>{time_label}</td></tr>"
                    f"</table>"
                    + (
                        f"<p style='margin-top:16px'>"
                        f"<a href='{site_url}/workflows/{workflow.pk}/' "
                        f"style='background:#1d4ed8;color:#fff;padding:8px 16px;border-radius:6px;"
                        f"text-decoration:none;font-size:14px'>View Workflow</a></p>"
                        if site_url
                        else ""
                    )
                    + "<p style='margin-top:24px;font-size:12px;color:#9ca3af'>"
                    "This is an automated notification from Parliament Workflow System.</p>"
                )
                send_mail(
                    subject=email_subject,
                    message=plain,
                    from_email=None,
                    recipient_list=[user.email],
                    html_message=html_message,
                    fail_silently=True,
                )
                emails_sent += 1

    return {
        "workflows_processed": pending_qs.count(),
        "notifications_created": notifications_created,
        "emails_sent": emails_sent,
    }


def _transition_overdue_to_followup_sync(
    workflow_id: str | None = None,
    auto_transition: bool = True,
) -> dict:
    """Undecorated version for synchronous execution"""
    from django.contrib.contenttypes.models import ContentType

    from .models import AuditLog, State, Transition, Workflow, WorkflowTransitionLog

    now = timezone.now()

    # Find overdue workflows
    if workflow_id is not None:
        overdue_qs = Workflow.objects.filter(
            pk=workflow_id,
            deadline__lt=now,
            current_state__is_terminal=False,
        ).select_related("workflow_type", "current_state", "owner", "assigned_to")
    else:
        overdue_qs = (
            Workflow.objects.filter(
                deadline__lt=now,
                current_state__is_terminal=False,
            )
            .select_related("workflow_type", "current_state", "owner", "assigned_to")
            .exclude(deadline__isnull=True)
        )

    workflows_transitioned = 0
    transitions_failed = 0

    for workflow in overdue_qs:
        # Look for a 'Follow-up' or 'Follow Up' state in this workflow type
        followup_state = State.objects.filter(
            workflow_type=workflow.workflow_type,
            name__icontains="follow",
        ).first()

        if not followup_state:
            transitions_failed += 1
            continue

        # Check if there's a valid transition from current state to follow-up state
        transition = Transition.objects.filter(
            workflow_type=workflow.workflow_type,
            from_state=workflow.current_state,
            to_state=followup_state,
        ).first()

        if not transition:
            transitions_failed += 1
            continue

        if auto_transition:
            from_state = workflow.current_state

            # Log the transition
            WorkflowTransitionLog.objects.create(
                workflow=workflow,
                transition=transition,
                from_state=from_state,
                to_state=followup_state,
                user=workflow.owner,
                comment="Automatic transition due to overdue deadline.",
            )

            # Audit log
            AuditLog.objects.create(
                content_type=ContentType.objects.get_for_model(workflow),
                object_id=workflow.pk,
                action="auto_transition",
                user=workflow.owner,
                ip_address="system",
                changes={
                    "transition": transition.name,
                    "from_state": from_state.name,
                    "to_state": followup_state.name,
                    "reason": "Automatic transition due to overdue deadline",
                },
            )

            # Update workflow state
            workflow.current_state = followup_state
            workflow.save()

            workflows_transitioned += 1

    return {
        "workflows_checked": overdue_qs.count(),
        "workflows_transitioned": workflows_transitioned,
        "transitions_failed": transitions_failed,
    }


def _check_delegation_expirations_sync() -> dict:
    """Undecorated version for synchronous execution"""
    now = timezone.now()

    # Find active delegations that should be expired
    expired_delegations = UserDelegation.objects.filter(
        status="active", end_date__lte=now
    )

    expired_count = 0
    notifications_created = 0
    emails_sent = 0
    errors = 0

    logger.info(f"Checking {expired_delegations.count()} delegations for expiration")

    for delegation in expired_delegations:
        try:
            delegator_name = (
                delegation.delegator.get_full_name() or delegation.delegator.username
            )
            delegatee_name = (
                delegation.delegatee.get_full_name() or delegation.delegatee.username
            )

            logger.info(
                f"Expiring delegation: {delegator_name} -> {delegatee_name} "
                f"(ID: {delegation.pk}, End: {delegation.end_date})"
            )

            # Expire the delegation (this sends notifications)
            delegation.expire_delegation()
            expired_count += 1

            # Count notifications and emails
            notifications_created += 2  # One for delegatee, one for delegator
            emails_sent += 2  # One email to each party

            logger.info(f"Successfully expired delegation {delegation.pk}")

        except Exception as e:
            errors += 1
            logger.error(f"Failed to expire delegation {delegation.pk}: {e}")

    result = {
        "delegations_checked": expired_delegations.count(),
        "delegations_expired": expired_count,
        "notifications_created": notifications_created,
        "emails_sent": emails_sent,
        "errors": errors,
    }

    logger.info(
        f"Delegation expiration check complete: "
        f"{expired_count} expired, {notifications_created} notifications, {emails_sent} emails, {errors} errors"
    )

    return result
