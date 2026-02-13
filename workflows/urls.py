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
    path("workflows/<int:pk>/edit/", views.workflow_edit, name="workflow_edit"),
    path(
        "workflows/<int:pk>/transition/<int:transition_id>/",
        views.workflow_transition,
        name="workflow_transition",
    ),
    # Workflow attachments
    path(
        "workflows/<int:pk>/attachments/",
        views.workflow_attachments,
        name="workflow_attachments",
    ),
    # Events
    path("events/", views.event_list, name="event_list"),
    path("events/<int:pk>/", views.event_detail, name="event_detail"),
    # Groups
    path("groups/", views.group_list, name="group_list"),
    path("groups/<int:pk>/", views.group_detail, name="group_detail"),
    # Reports
    path("reports/", views.reports, name="reports"),
    # SharePoint API endpoints
    path("api/sharepoint/sites/", views.sharepoint_sites, name="sharepoint_sites"),
    path("api/sharepoint/test/", views.sharepoint_test, name="sharepoint_test"),
    path(
        "api/sharepoint/sites/<str:site_id>/drives/",
        views.sharepoint_site_drives,
        name="sharepoint_site_drives",
    ),
    path(
        "api/sharepoint/drives/<str:drive_id>/folders/",
        views.sharepoint_drive_folders,
        name="sharepoint_drive_folders",
    ),
    path(
        "api/sharepoint/folders/<str:folder_id>/items/",
        views.sharepoint_folder_items,
        name="sharepoint_folder_items",
    ),
    path(
        "api/attachments/link-sharepoint/",
        views.attachment_link_sharepoint,
        name="attachment_link_sharepoint",
    ),
    path("api/attachments/upload/", views.attachment_upload, name="attachment_upload"),
    path(
        "api/attachments/<int:pk>/", views.attachment_detail, name="attachment_detail"
    ),
    path("manage/users/", views.user_admin, name="admin_users"),
    path("manage/memberships/", views.user_admin_groups, name="admin_memberships"),
    path("manage/roles/", views.role_admin, name="admin_roles"),
    path(
        "manage/workflow-types/",
        views.user_admin_workflow_types,
        name="admin_workflow_types",
    ),
    path("manage/groups/", views.group_admin, name="admin_groups"),
]
