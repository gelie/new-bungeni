# Parliament Workflow Management System (PWMS)

Django-based workflow and case management system for Parliament operations.

## Tech Stack

- **Backend**: Django 6.0, Django Ninja (REST APIs), django-htmx
- **Database**: Oracle
- **Authentication**: LDAP (django-auth-ldap)
- **Dependencies**: django-mptt, django-background-tasks, oracledb, reportlab, weasyprint

## Key Features

- **Workflow Management**: Create and manage workflow types with states, transitions, and permissions
- **Event Management**: Event scheduling, attendance tracking, comments
- **User Management**: Custom user model with MP-specific fields (constituency, party affiliation)
- **Role-Based Access Control**: Fine-grained permissions per role and workflow state
- **Membership Sync**: Synchronization with Oracle database
- **Notifications**: Deadline alerts and email notifications
- **Document Generation**: PDF reports using reportlab and weasyprint
- **SharePoint Integration**

## Management Commands

- `sync_users_oracle` - Sync users from Oracle
- `sync_groups_oracle` - Sync groups from Oracle
- `sync_roles_oracle` - Sync roles from Oracle
- `validate_memberships` - Validate user memberships
- `scrape_parliament_committees` - Scrape committee data
- `send_overdue_alerts` - Send deadline overdue alerts
- `update_lucide_icons` - Update Lucide icons

## Setup

```bash
# Install dependencies
uv sync

# Run migrations
python manage.py migrate

# Start development server
python manage.py runserver
```