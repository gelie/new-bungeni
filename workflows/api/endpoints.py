from uuid import UUID

from django.db.models import Exists, OuterRef, Q
from django.http import Http404
from ninja import NinjaAPI, Query
from ninja.pagination import paginate

import workflows.api.schemas as schemas
from workflows import models
from workflows.api.pagination import ResultsLimitOffsetPagination

api = NinjaAPI()


@api.get(
    "/health",
    summary="Get health status",
    description="Get API health status.",
    tags=["System"],
    operation_id="get_health",
)
def get_health(request):
    """Get API health status."""
    return {"status": "ok"}


@api.get(
    "/workflows",
    summary="List workflows",
    description="List workflows. This endpoint is currently a placeholder.",
    tags=["Workflows"],
    operation_id="list_workflows",
)
def list_workflows(request):
    """List workflows."""
    return {"workflows": "workflows"}


@api.get(
    "/workflows/{workflow_id}",
    summary="Get workflow by ID",
    description="Get a workflow by ID. This endpoint is currently a placeholder.",
    tags=["Workflows"],
    operation_id="get_workflow_by_id",
)
def get_workflow_by_id(request, workflow_id: UUID):
    """Get workflow by ID."""
    return {"workflow": "workflow"}


USER_MEMBERSHIP_PREFETCH = ("memberships__group", "memberships__role")
USER_MEMBERSHIP_SELECT_RELATED = ("group", "role")

USER_SEARCH_FIELDS = ("username", "last_name", "first_name")
GROUP_SEARCH_FIELDS = ("name",)
MEMBERSHIP_SEARCH_FIELDS = ("user__username",)
ROLE_SEARCH_FIELDS = ("name",)
SITE_SEARCH_FIELDS = ("name",)


def _apply_search(queryset, search: str = None, fields: tuple[str, ...] = ()):
    if not search or not fields:
        return queryset

    search_query = Q()
    for field in fields:
        search_query |= Q(**{f"{field}__icontains": search})

    return queryset.filter(search_query)


def _build_membership_filters(
    query: schemas.MembershipFilterQuerySchema,
) -> dict[str, object]:
    filters = {
        "role__name__iexact": query.role,
        "group__name__iexact": query.group,
        "role_id": query.role_id,
        "group_id": query.group_id,
        "role__slug__iexact": query.role_slug,
        "group__slug__iexact": query.group_slug,
    }
    return {key: value for key, value in filters.items() if value is not None}


def _apply_membership_filters(queryset, membership_filters: dict[str, object]):
    if membership_filters:
        return queryset.filter(**membership_filters)
    return queryset


def _get_user_with_memberships(**lookup):
    return models.User.objects.prefetch_related(*USER_MEMBERSHIP_PREFETCH).get(**lookup)


def _with_filtered_groupmembership(user, membership_filters: dict[str, object]):
    memberships = _apply_membership_filters(
        user.memberships.select_related(*USER_MEMBERSHIP_SELECT_RELATED),
        membership_filters,
    )
    user._groupmembership = memberships
    return user


@api.get(
    "/users",
    response=list[schemas.UserSchema],
    summary="List users",
    description=(
        "List users with optional search and membership filters. "
        "Paginated with `limit` and `offset` (default `limit=20`). "
        "`search` matches username, first name, or last name. "
        "Membership filters (`role`, `group`, `role_id`, `group_id`, "
        "`role_slug`, `group_slug`) are combined with AND and applied "
        "to active memberships only."
    ),
    tags=["Users"],
    operation_id="list_users",
)
@paginate(ResultsLimitOffsetPagination)
def list_users(request, query: schemas.UserQuerySchema = Query(...)):
    """List users. Paginated with `limit` and `offset` (default `limit=20`)."""
    users = _apply_search(models.User.objects.all(), query.search, USER_SEARCH_FIELDS)

    membership_filters = _build_membership_filters(query)
    if membership_filters:
        memberships = _apply_membership_filters(
            models.GroupMembership.objects.filter(
                user_id=OuterRef("pk"), is_active=True
            ),
            membership_filters,
        )
        users = users.filter(Exists(memberships))

    return users.distinct()


@api.get(
    "/users/{username}",
    response=schemas.UserWithMembershipSchema,
    summary="Get user by username",
    description=(
        "Get a user by username, including nested `groupmembership` entries. "
        "Optional membership filters narrow only the returned `groupmembership` "
        "list and do not affect user lookup."
    ),
    tags=["Users"],
    operation_id="get_user_by_username",
)
def get_user_by_username(
    request,
    username: str,
    query: schemas.MembershipFilterQuerySchema = Query(...),
):
    """Get user by username."""
    membership_filters = _build_membership_filters(query)
    user = _get_user_with_memberships(username=username)
    return _with_filtered_groupmembership(user, membership_filters)


@api.get(
    "/users/{user_id}",
    response=schemas.UserWithMembershipSchema,
    summary="Get user by ID",
    description=(
        "Get a user by ID, including nested `groupmembership` entries. "
        "Optional membership filters narrow only the returned `groupmembership` "
        "list and do not affect user lookup."
    ),
    tags=["Users"],
    operation_id="get_user_by_id",
)
def get_user_by_id(
    request,
    user_id: UUID,
    query: schemas.MembershipFilterQuerySchema = Query(...),
):
    """Get user by ID."""
    membership_filters = _build_membership_filters(query)
    user = _get_user_with_memberships(id=user_id)
    return _with_filtered_groupmembership(user, membership_filters)


@api.get(
    "/groups",
    response=list[schemas.GroupSchema],
    summary="List groups",
    description="List groups with optional `search` by name. Paginated with `limit` and `offset` (default `limit=20`).",
    tags=["Groups"],
    operation_id="list_groups",
)
@paginate(ResultsLimitOffsetPagination)
def list_groups(
    request, query: schemas.SearchQuerySchema = Query(...)
) -> list[models.Group]:
    """List groups. Paginated with `limit` and `offset` (default `limit=20`)."""
    return _apply_search(models.Group.objects.all(), query.search, GROUP_SEARCH_FIELDS)


@api.get(
    "/group-types",
    response=list[str],
    summary="List group types",
    description="List available group type values.",
    tags=["Groups"],
    operation_id="list_group_types",
)
def list_group_types(request):
    """List group types."""
    return [choice[0] for choice in models.Group.GROUP_TYPE_CHOICES]


@api.get(
    "/groups/{group_id}",
    response=schemas.GroupSchema,
    summary="Get group by ID",
    description="Get a group by ID.",
    tags=["Groups"],
    operation_id="get_group_by_id",
)
def get_group_by_id(request, group_id: UUID):
    """Get group by ID."""
    group = models.Group.objects.get(id=group_id)
    return group


@api.get(
    "/memberships",
    response=list[schemas.MembershipSchema],
    summary="List memberships",
    description="List memberships with optional `search` by username. Paginated with `limit` and `offset` (default `limit=20`).",
    tags=["Memberships"],
    operation_id="list_memberships",
)
@paginate(ResultsLimitOffsetPagination)
def list_memberships(
    request, query: schemas.SearchQuerySchema = Query(...)
) -> list[models.GroupMembership]:
    """List memberships. Paginated with `limit` and `offset` (default `limit=20`)."""
    return _apply_search(
        models.GroupMembership.objects.all(), query.search, MEMBERSHIP_SEARCH_FIELDS
    )


@api.get(
    "/roles",
    response=list[schemas.RoleSchema],
    summary="List roles",
    description="List roles with optional `search` by name. Paginated with `limit` and `offset` (default `limit=20`).",
    tags=["Roles"],
    operation_id="list_roles",
)
@paginate(ResultsLimitOffsetPagination)
def list_roles(
    request, query: schemas.SearchQuerySchema = Query(...)
) -> list[models.Role]:
    """List roles. Paginated with `limit` and `offset` (default `limit=20`)."""
    return _apply_search(models.Role.objects.all(), query.search, ROLE_SEARCH_FIELDS)


@api.get(
    "/sites",
    response=list[schemas.SharePointSiteSchema],
    summary="List sites",
    description="List sites with optional `search` by name. Paginated with `limit` and `offset` (default `limit=20`).",
    tags=["Sites"],
    operation_id="list_sites",
)
@paginate(ResultsLimitOffsetPagination)
def list_sites(
    request, query: schemas.SearchQuerySchema = Query(...)
) -> list[models.Site]:
    """List sites. Paginated with `limit` and `offset` (default `limit=20`)."""
    return _apply_search(models.Site.objects.all(), query.search, SITE_SEARCH_FIELDS)


@api.get(
    "/sites/{site_id}/drives",
    response=list[schemas.SharePointDriveSchema],
    summary="List site drives",
    description="List drives for a site by external site ID (`site_id`). Paginated with `limit` and `offset` (default `limit=20`).",
    tags=["Sites"],
    operation_id="list_site_drives",
)
@paginate(ResultsLimitOffsetPagination)
def list_site_drives(request, site_id: str):
    """List site drives by external site ID. Paginated with `limit` and `offset` (default `limit=20`)."""
    site = models.Site.objects.filter(site_id=site_id).first()
    if not site:
        raise Http404("Site not found")
    return models.Drive.objects.filter(site_id=site.id)


@api.get(
    "/sites/{username}",
    response=list[schemas.SharePointSiteSchema],
    summary="List user sites",
    description="List sites where the specified user is a member. Paginated with `limit` and `offset` (default `limit=20`).",
    tags=["Sites"],
    operation_id="list_user_sites",
)
@paginate(ResultsLimitOffsetPagination)
def list_user_sites(request, username: str):
    """List sites where the specified user is a member. Paginated with `limit` and `offset` (default `limit=20`)."""
    return models.Site.objects.filter(sitemember__user__username=username).distinct()
