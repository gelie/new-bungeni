from django.urls import path

from . import views

urlpatterns = [
    # Authentication
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    # Dashboard
    path("", views.dashboard, name="dashboard"),
    # Workflows
    path("workflows/", views.workflow_list, name="workflow_list"),
    path("workflows/new/", views.workflow_create, name="workflow_create"),
    path("workflows/<int:pk>/", views.workflow_detail, name="workflow_detail"),
    path(
        "workflows/<int:pk>/transition/<int:transition_id>/",
        views.workflow_transition,
        name="workflow_transition",
    ),
    # Events
    path("events/", views.event_list, name="event_list"),
    path("events/<int:pk>/", views.event_detail, name="event_detail"),
    # Groups
    path("groups/", views.group_list, name="group_list"),
    path("groups/<int:pk>/", views.group_detail, name="group_detail"),
    # Reports
    path("reports/", views.reports, name="reports"),
]
