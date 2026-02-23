from django.core.mail import send_mail
from django.tasks import task
from django.utils import timezone


@task
def send_transition_alert(
    workflow_id: int,
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
        f"[Bungeni] {workflow_type_name}: '{workflow_title}' moved to {to_state_name}"
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
        f"This is an automated notification from Bungeni."
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
        f"This is an automated notification from Bungeni.</p>"
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


@task
def notify_overdue_workflows(
    site_url: str = "",
    workflow_id: int | None = None,
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
                email_subject = f"[Bungeni] Overdue: {workflow.workflow_type.name} — {workflow.title}"
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
                    + "--\nThis is an automated notification from Bungeni."
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
                    "This is an automated notification from Bungeni.</p>"
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
