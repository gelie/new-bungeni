"""Utilities for generating workflow reports and exports."""

from io import BytesIO

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone


def generate_workflow_report_html(workflow, user):
    """Generate HTML report for a workflow."""

    # Get sub-workflows
    sub_workflows = (
        workflow.sub_workflows.all()
        .select_related("workflow_type", "current_state", "owner")
        .order_by("created_at")
    )

    # Calculate completion stats
    total_count = sub_workflows.count()
    completed_count = sub_workflows.filter(current_state__is_terminal=True).count()
    completion_percentage = (
        int((completed_count / total_count) * 100) if total_count > 0 else 0
    )

    # Get transition history
    transition_logs = (
        workflow.transition_logs.all()
        .select_related("user", "from_state", "to_state", "transition")
        .order_by("-timestamp")
    )

    # Get comments
    comments = workflow.comments.all().select_related("user").order_by("-created_at")

    # Process custom fields (including delegate_group)
    from .models import User

    workflow_schema = workflow.workflow_type.json_schema or {}
    custom_fields = {}
    if workflow_schema and workflow.data:
        properties = workflow_schema.get("properties", {})
        for field_name, field_config in properties.items():
            if field_name in workflow.data:
                field_value = workflow.data[field_name]

                # Special handling for delegate_group field
                if field_name == "delegate_group" and isinstance(field_value, list):
                    # Fetch user details for each delegate
                    delegate_details = []
                    for delegate in field_value:
                        if isinstance(delegate, dict) and "user_id" in delegate:
                            try:
                                user_obj = User.objects.get(pk=delegate["user_id"])
                                delegate_details.append(
                                    {
                                        "user_id": delegate["user_id"],
                                        "user_name": f"{user_obj.first_name} {user_obj.last_name}",
                                        "delegation_role": delegate.get(
                                            "delegation_role", ""
                                        ),
                                    }
                                )
                            except User.DoesNotExist:
                                # Handle case where user doesn't exist
                                delegate_details.append(
                                    {
                                        "user_id": delegate["user_id"],
                                        "user_name": f"Unknown User ({delegate['user_id']})",
                                        "delegation_role": delegate.get(
                                            "delegation_role", ""
                                        ),
                                    }
                                )

                    custom_fields[field_name] = {
                        "title": field_config.get("title", field_name),
                        "value": delegate_details,
                        "type": "delegate_group",
                    }
                else:
                    custom_fields[field_name] = {
                        "title": field_config.get("title", field_name),
                        "value": field_value,
                        "type": field_config.get("type", "string"),
                    }

    context = {
        "workflow": workflow,
        "sub_workflows": sub_workflows,
        "total_count": total_count,
        "completed_count": completed_count,
        "completion_percentage": completion_percentage,
        "transition_logs": transition_logs,
        "comments": comments,
        "custom_fields": custom_fields,
        "report_date": timezone.now(),
    }

    return render_to_string("workflows/workflow_report.html", context)


def export_workflow_to_pdf(workflow, user):
    """Export workflow report as PDF using WeasyPrint."""
    try:
        from django.utils import timezone
        from weasyprint import HTML

        html_content = generate_workflow_report_html(workflow, user)

        # Generate PDF
        pdf_file = BytesIO()
        HTML(string=html_content).write_pdf(pdf_file)
        pdf_file.seek(0)

        # Create response
        response = HttpResponse(pdf_file.read(), content_type="application/pdf")
        filename = (
            f"workflow_report_{workflow.pk}_{timezone.now().strftime('%Y%m%d')}.pdf"
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        return response
    except ImportError:
        # WeasyPrint not installed, return HTML instead
        from django.utils import timezone

        html_content = generate_workflow_report_html(workflow, user)
        response = HttpResponse(html_content, content_type="text/html")
        return response
