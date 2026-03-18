from django.urls import path

from workflows.api.endpoints import api

from . import views

urlpatterns = [
    # API
    path("api/", api.urls),
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
    path("workflows/<int:pk>/report/", views.workflow_report, name="workflow_report"),
    path(
        "workflows/<int:pk>/share/email/",
        views.workflow_share_email,
        name="workflow_share_email",
    ),
    path(
        "workflows/<int:pk>/comments/<int:comment_pk>/delete/",
        views.comment_delete,
        name="comment_delete",
    ),
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
    path("events/create/", views.event_create, name="event_create"),
    path("events/<int:pk>/", views.event_detail, name="event_detail"),
    path("events/<int:pk>/edit/", views.event_edit, name="event_edit"),
    path(
        "events/<int:pk>/attendance/",
        views.event_attendance_edit,
        name="event_attendance_edit",
    ),
    path("events/<int:pk>/export/", views.event_export, name="event_export"),
    path(
        "events/<int:pk>/export/pdf/", views.event_export_pdf, name="event_export_pdf"
    ),
    path(
        "events/<int:pk>/status/<str:status>/",
        views.event_update_status,
        name="event_update_status",
    ),
    # Groups
    path("groups/", views.group_list, name="group_list"),
    path("groups/<int:pk>/", views.group_detail, name="group_detail"),
    # Notifications
    path("notifications/", views.notifications_json, name="notifications_json"),
    path(
        "notifications/mark-read/",
        views.notifications_mark_read,
        name="notifications_mark_read",
    ),
    path(
        "notifications/clear/",
        views.notifications_clear,
        name="notifications_clear",
    ),
    # Reports
    path("reports/", views.reports, name="reports"),
    path("reports/export/csv/", views.reports_export_csv, name="reports_export_csv"),
    path(
        "reports/export/excel/", views.reports_export_excel, name="reports_export_excel"
    ),
    path(
        "reports/recent-activity/pdf/",
        views.reports_recent_activity_pdf,
        name="reports_recent_activity_pdf",
    ),
    path(
        "workflows/<int:parent_pk>/bulk-create/",
        views.workflow_bulk_create,
        name="workflow_bulk_create",
    ),
    path(
        "workflows/<int:pk>/refer/",
        views.workflow_refer,
        name="workflow_refer",
    ),
    path(
        "api/workflows/<int:pk>/referral-targets/",
        views.api_referral_targets,
        name="api_referral_targets",
    ),
    # SharePoint API endpoints
    path(
        "api/sharepoint/members/",
        views.api_sharepoint_members_create,
        name="api_sharepoint_members_create",
    ),
    path(
        "api/sharepoint/members/<int:member_id>/",
        views.api_sharepoint_members_delete,
        name="api_sharepoint_members_delete",
    ),
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
    path(
        "manage/workflow-types/create/",
        views.workflow_type_create,
        name="admin_workflow_type_create",
    ),
    path(
        "manage/workflow-types/<int:pk>/edit/",
        views.workflow_type_edit,
        name="admin_workflow_type_edit",
    ),
    path(
        "manage/workflow-types/<int:pk>/states/",
        views.workflow_type_states,
        name="admin_workflow_type_states",
    ),
    path(
        "manage/workflow-types/<int:pk>/transitions/",
        views.workflow_type_transitions,
        name="admin_workflow_type_transitions",
    ),
    path(
        "manage/workflow-types/<int:pk>/referral-configs/",
        views.workflow_type_referral_configs,
        name="admin_workflow_type_referral_configs",
    ),
    path(
        "workflow-types/<int:pk>/diagram/",
        views.workflow_type_diagram,
        name="workflow_type_diagram",
    ),
    path("manage/groups/", views.group_admin, name="admin_groups"),
    path(
        "manage/sharepoint/sites/",
        views.sharepoint_admin_sites,
        name="admin_sharepoint_sites",
    ),
    path(
        "manage/sharepoint/members/",
        views.sharepoint_admin_members,
        name="admin_sharepoint_members",
    ),
    # Delegation management
    path("manage/delegations/", views.delegation_list, name="delegation_list"),
    path(
        "manage/delegations/create/", views.delegation_create, name="delegation_create"
    ),
    path(
        "manage/delegations/<int:pk>/",
        views.delegation_detail,
        name="delegation_detail",
    ),
    path(
        "manage/delegations/<int:pk>/edit/",
        views.delegation_edit,
        name="delegation_edit",
    ),
    path(
        "manage/delegations/<int:pk>/revoke/",
        views.delegation_revoke,
        name="delegation_revoke",
    ),
    path(
        "manage/delegations/<int:pk>/approve/",
        views.delegation_approve,
        name="delegation_approve",
    ),
    # User search for delegation
    path("user-search/", views.user_search, name="user_search"),
]
