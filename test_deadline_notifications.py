#!/usr/bin/env python
"""
Quick test script for workflow deadline notifications and auto-transitions.
Run with: python test_deadline_notifications.py
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.utils import timezone
from datetime import timedelta
from workflows.models import Workflow, State

def test_deadline_notifications():
    """Test the workflow deadline notification system."""
    print("Testing Workflow Deadline Notifications")
    print("=" * 60)
    
    now = timezone.now()
    print(f"\nCurrent time: {now}")
    
    # Pending deadlines (within 3 days)
    pending_threshold = now + timedelta(days=3)
    pending_workflows = Workflow.objects.filter(
        deadline__gte=now,
        deadline__lte=pending_threshold,
        current_state__is_terminal=False
    ).exclude(deadline__isnull=True)
    
    print(f"\n📅 Workflows with pending deadlines (within 3 days): {pending_workflows.count()}")
    for workflow in pending_workflows[:5]:
        days_remaining = (workflow.deadline - now).days
        print(f"  - [{workflow.pk}] {workflow.title}")
        print(f"    Deadline: {workflow.deadline} ({days_remaining} days remaining)")
        print(f"    State: {workflow.current_state.name}")
    
    # Overdue workflows
    overdue_workflows = Workflow.objects.filter(
        deadline__lt=now,
        current_state__is_terminal=False
    ).exclude(deadline__isnull=True)
    
    print(f"\n⚠️  Overdue workflows: {overdue_workflows.count()}")
    for workflow in overdue_workflows[:5]:
        days_overdue = (now - workflow.deadline).days
        print(f"  - [{workflow.pk}] {workflow.title}")
        print(f"    Deadline: {workflow.deadline} ({days_overdue} days overdue)")
        print(f"    State: {workflow.current_state.name}")
        
        # Check if follow-up state exists
        followup_state = State.objects.filter(
            workflow_type=workflow.workflow_type,
            name__icontains="follow"
        ).first()
        
        if followup_state:
            print(f"    ✓ Follow-up state available: {followup_state.name}")
        else:
            print(f"    ✗ No follow-up state configured")
    
    print("\n" + "=" * 60)
    print("To run the actual notifications and transitions:")
    print("=" * 60)
    print("\n1. Dry run (see what would happen):")
    print("   python manage.py notify_deadlines --dry-run")
    print("\n2. Run for real:")
    print("   python manage.py notify_deadlines")
    print("\n3. Test specific workflow:")
    print("   python manage.py notify_deadlines --workflow-id <ID> --force")
    print("\n4. Customize pending deadline warning:")
    print("   python manage.py notify_deadlines --days-before 5")
    print()

if __name__ == "__main__":
    test_deadline_notifications()
