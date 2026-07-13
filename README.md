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

## API Pagination

The Django Ninja API uses paginated list responses by default.

- Pagination parameters: `limit` and `offset`
- Default page size: `20`
- Response shape: `count`, `next`, `previous`, `results`

Example response:

```json
{
  "count": 1632,
  "next": "http://localhost/api/users?limit=20&offset=20",
  "previous": null,
  "results": []
}
```

Examples:

```bash
/api/users?limit=20&offset=40
/api/groups?search=finance&limit=20
```

## API Endpoints

| Tag | Method | Path | Description |
| --- | --- | --- | --- |
| System | `GET` | `/health` | Health |
| Workflows | `GET` | `/workflows` | Workflows |
| Workflows | `GET` | `/workflows/{workflow_id}` | Workflow |
| Users | `GET` | `/users` | Users |
| Users | `GET` | `/users/{username}` | User |
| Users | `GET` | `/users/{user_id}` | User |
| Groups | `GET` | `/groups` | Groups |
| Groups | `GET` | `/group-types` | Group types |
| Groups | `GET` | `/groups/{group_id}` | Group |
| Memberships | `GET` | `/memberships` | Memberships |
| Roles | `GET` | `/roles` | Roles |
| Sites | `GET` | `/sites` | Sites |
| Sites | `GET` | `/sites/{site_id}/drives` | Site drives |
| Sites | `GET` | `/sites/{username}` | User sites |


## API Query Matrix

| Endpoint | Search | Membership filters | Pagination |
| --- | --- | --- | --- |
| `GET /users` | `search` | `role`, `group`, `role_id`, `group_id`, `role_slug`, `group_slug` | `limit`, `offset` |
| `GET /groups` | `search` | - | `limit`, `offset` |
| `GET /memberships` | `search` | - | `limit`, `offset` |
| `GET /roles` | `search` | - | `limit`, `offset` |
| `GET /sites` | `search` | - | `limit`, `offset` |
| `GET /sites/{site_id}/drives` | - | - | `limit`, `offset` |
| `GET /sites/{username}` | - | - | `limit`, `offset` |

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