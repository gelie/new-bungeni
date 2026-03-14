from django import forms
from flatpickr import DateTimePickerInput

from .models import Event, EventAttendance, Group, User, UserDelegation, Workflow


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
                attrs={
                    "class": "form-control input input-bordered w-full",
                    "placeholder": "Select start date and time...",
                },
                format="%Y-%m-%d %H:%M",
            ),
            "end_datetime": forms.DateTimeInput(
                attrs={
                    "class": "form-control input input-bordered w-full",
                    "placeholder": "Select end date and time...",
                },
                format="%Y-%m-%d %H:%M",
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


class UserDelegationForm(forms.ModelForm):
    """Form for creating and editing user delegations."""

    class Meta:
        model = UserDelegation
        fields = [
            "delegatee",
            "workflows",
            "groups",
            "start_date",
            "end_date",
            "can_view_workflows",
            "can_edit_workflows",
            "can_transition_workflows",
            "can_receive_assignments",
            "can_receive_notifications",
            "reason",
        ]
        widgets = {
            "delegatee": forms.TextInput(
                attrs={"class": "input input-bordered w-full"}
            ),
            "workflows": forms.CheckboxSelectMultiple(attrs={"class": "space-y-2"}),
            "groups": forms.CheckboxSelectMultiple(attrs={"class": "space-y-2"}),
            "start_date": DateTimePickerInput(
                attrs={
                    "class": "form-control input input-bordered w-full",
                    "placeholder": "Select start date and time...",
                }
            ),
            "end_date": DateTimePickerInput(
                attrs={
                    "class": "form-control input input-bordered w-full",
                    "placeholder": "Select end date and time (optional)...",
                }
            ),
            "can_view_workflows": forms.CheckboxInput(
                attrs={"class": "checkbox checkbox-primary"}
            ),
            "can_edit_workflows": forms.CheckboxInput(
                attrs={"class": "checkbox checkbox-primary"}
            ),
            "can_transition_workflows": forms.CheckboxInput(
                attrs={"class": "checkbox checkbox-primary"}
            ),
            "can_receive_assignments": forms.CheckboxInput(
                attrs={"class": "checkbox checkbox-primary"}
            ),
            "can_receive_notifications": forms.CheckboxInput(
                attrs={"class": "checkbox checkbox-primary"}
            ),
            "reason": forms.Textarea(
                attrs={
                    "class": "textarea textarea-bordered w-full",
                    "rows": 6,
                    "placeholder": "Reason for delegation...",
                }
            ),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Filter delegatee to exclude current user and include only active users
        self.fields["delegatee"].queryset = (
            User.objects.filter(is_active=True)
            .exclude(id=user.id)
            .order_by("first_name", "last_name")
        )

        # Filter workflows to those the user has access to delegate
        user_workflows = []
        for workflow in Workflow.objects.all():
            if workflow.can_user_view(user):
                user_workflows.append(workflow.id)

        self.fields["workflows"].queryset = Workflow.objects.filter(
            id__in=user_workflows
        ).order_by("title")

        # Filter groups to those the user belongs to
        user_groups = user.memberships.filter(is_active=True).values_list(
            "group", flat=True
        )
        self.fields["groups"].queryset = Group.objects.filter(
            id__in=user_groups
        ).order_by("name")

        # Set delegator to current user
        self.instance.delegator = user

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        delegatee = cleaned_data.get("delegatee")

        # Validate date range
        if start_date and end_date and start_date >= end_date:
            raise forms.ValidationError("End date must be after start date.")

        # Check if delegation already exists for this user and delegatee
        if delegatee and not self.instance.pk:
            existing = UserDelegation.objects.filter(
                delegator=self.user, delegatee=delegatee, status="active"
            ).first()
            if existing:
                raise forms.ValidationError(
                    f"An active delegation to {delegatee.get_full_name() or delegatee.username} already exists."
                )

        return cleaned_data

    def clean_delegatee(self):
        delegatee = self.cleaned_data.get("delegatee")
        if delegatee == self.user:
            raise forms.ValidationError("You cannot delegate to yourself.")
        return delegatee


class UserDelegationSearchForm(forms.Form):
    """Form for searching and filtering delegations."""

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Search by delegator or delegatee name...",
            }
        ),
    )

    status = forms.ChoiceField(
        required=False,
        choices=[("", "All Status")] + UserDelegation.STATUS_CHOICES,
        widget=forms.Select(attrs={"class": "select select-bordered w-full"}),
    )

    delegator = forms.ModelChoiceField(
        required=False,
        queryset=User.objects.filter(is_active=True).order_by(
            "first_name", "last_name"
        ),
        widget=forms.Select(attrs={"class": "select select-bordered w-full"}),
        empty_label="All Delegators",
    )

    delegatee = forms.ModelChoiceField(
        required=False,
        queryset=User.objects.filter(is_active=True).order_by(
            "first_name", "last_name"
        ),
        widget=forms.Select(attrs={"class": "select select-bordered w-full"}),
        empty_label="All Delegatees",
    )
