from django.core.mail import send_mail
from django.tasks import task


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

    subject = f"[Bungeni] {workflow_type_name}: '{workflow_title}' moved to {to_state_name}"

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
