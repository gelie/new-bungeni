from django import forms

from .models import Event, EventAttendance, Group


class EventForm(forms.ModelForm):
    """Form for creating and editing events."""

    class Meta:
        model = Event
        fields = [
            "event_type",
            "title",
            "description",
            "group",
            "venue",
            "location",
            "start_datetime",
            "end_datetime",
            "status",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "description": forms.Textarea(
                attrs={"class": "textarea textarea-bordered w-full", "rows": 4}
            ),
            "event_type": forms.Select(
                attrs={"class": "select select-bordered w-full"}
            ),
            "group": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "location": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "venue": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "start_datetime": forms.DateTimeInput(
                attrs={"class": "input input-bordered w-full", "type": "datetime-local"}
            ),
            "end_datetime": forms.DateTimeInput(
                attrs={"class": "input input-bordered w-full", "type": "datetime-local"}
            ),
            "status": forms.Select(attrs={"class": "select select-bordered w-full"}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Filter groups to those the user belongs to
        user_groups = user.memberships.filter(is_active=True).values_list(
            "group", flat=True
        )
        self.fields["group"].queryset = Group.objects.filter(id__in=user_groups)

        # Set organizer to current user on save
        self.instance.organizer = user

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_datetime")
        end = cleaned_data.get("end_datetime")
        if start and end and start >= end:
            raise forms.ValidationError("End time must be after start time.")
        return cleaned_data


class EventAttendanceForm(forms.ModelForm):
    """Form for updating a single attendance record."""

    class Meta:
        model = EventAttendance
        fields = ["status", "notes"]
        widgets = {
            "status": forms.Select(attrs={"class": "select select-bordered select-sm"}),
            "notes": forms.Textarea(
                attrs={
                    "class": "textarea textarea-bordered textarea-sm",
                    "rows": 2,
                    "placeholder": "Optional notes...",
                }
            ),
        }


class EventAttendanceBulkForm(forms.Form):
    """Form for bulk updating attendance records."""

    def __init__(self, event, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event

        # Add a field for each attendance record
        for attendance in event.attendances.select_related("user").order_by(
            "user__first_name", "user__last_name"
        ):
            field_name = f"attendance_{attendance.pk}"
            self.fields[field_name] = forms.ChoiceField(
                choices=EventAttendance.ATTENDANCE_CHOICES,
                initial=attendance.status,
                widget=forms.Select(
                    attrs={"class": "select select-bordered select-sm"}
                ),
                label=f"{attendance.user.first_name} {attendance.user.last_name}",
            )

            # Add notes field
            notes_field = f"notes_{attendance.pk}"
            self.fields[notes_field] = forms.CharField(
                required=False,
                initial=attendance.notes,
                widget=forms.Textarea(
                    attrs={
                        "class": "textarea textarea-bordered textarea-sm",
                        "rows": 1,
                        "placeholder": "Notes...",
                    }
                ),
                label=f"{attendance.user.first_name} {attendance.user.last_name} notes",
            )

    def save(self):
        """Save all attendance records."""
        updated_count = 0
        for attendance in self.event.attendances.all():
            status_field = f"attendance_{attendance.pk}"
            notes_field = f"notes_{attendance.pk}"

            if status_field in self.cleaned_data:
                old_status = attendance.status
                attendance.status = self.cleaned_data[status_field]
                attendance.notes = self.cleaned_data.get(notes_field, "")
                attendance.save()

                if old_status != attendance.status:
                    updated_count += 1

        return updated_count
