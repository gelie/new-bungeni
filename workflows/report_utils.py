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

    context = {
        "workflow": workflow,
        "sub_workflows": sub_workflows,
        "total_count": total_count,
        "completed_count": completed_count,
        "completion_percentage": completion_percentage,
        "transition_logs": transition_logs,
        "comments": comments,
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
