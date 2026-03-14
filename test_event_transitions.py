#!/usr/bin/env python
"""
Quick test script for event automatic transitions.
Run with: python test_event_transitions.py
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.utils import timezone
from workflows.models import Event

def test_event_transitions():
    """Test the automatic event status transitions."""
    print("Testing Event Automatic Transitions")
    print("=" * 50)
    
    # Get current time
    now = timezone.now()
    print(f"\nCurrent time: {now}")
    
    # Find events that should transition to "in_progress"
    scheduled_events = Event.objects.filter(
        status="scheduled",
        start_datetime__lte=now
    )
    print(f"\nEvents that should be 'in_progress': {scheduled_events.count()}")
    for event in scheduled_events[:5]:  # Show first 5
        print(f"  - [{event.pk}] {event.title} (started: {event.start_datetime})")
    
    # Find events that should transition to "completed"
    in_progress_events = Event.objects.filter(
        status="in_progress",
        end_datetime__lte=now
    )
    print(f"\nEvents that should be 'completed': {in_progress_events.count()}")
    for event in in_progress_events[:5]:  # Show first 5
        print(f"  - [{event.pk}] {event.title} (ended: {event.end_datetime})")
    
    # Run the automatic update
    print("\n" + "=" * 50)
    print("Running automatic status updates...")
    print("=" * 50)
    
    result = Event.update_automatic_statuses()
    
    print(f"\n✓ Transitioned to 'in_progress': {result['to_in_progress']}")
    print(f"✓ Transitioned to 'completed': {result['to_completed']}")
    
    if result['to_in_progress'] == 0 and result['to_completed'] == 0:
        print("\n✓ No events needed status updates at this time.")
    else:
        print(f"\n✓ Successfully updated {result['to_in_progress'] + result['to_completed']} event(s).")

if __name__ == "__main__":
    test_event_transitions()
