from uuid import UUID

from django.db.models import Q
from django.http import Http404
from ninja import NinjaAPI
from ninja.pagination import RouterPaginated

import workflows.api.schemas as schemas
from workflows import models

api = NinjaAPI(default_router=RouterPaginated())


@api.get("/health")
def health(request):
    return {"status": "ok"}


@api.get("/workflows")
def workflows(request):
    return {"workflows": "workflows"}


@api.get("/workflows/{workflow_id}")
def workflow(request, workflow_id: UUID):
    return {"workflow": "workflow"}


@api.get("/users", response=list[schemas.UserSchema])
def users(request, search: str = None):
    users = models.User.objects.all()
    if search:
        users = users.filter(
            Q(username__icontains=search)
            | Q(last_name__icontains=search)
            | Q(first_name__icontains=search)
        )
    return users


@api.get("/users/{user_id}", response=schemas.UserSchema)
def user(request, user_id: UUID):
    user = models.User.objects.get(id=user_id)
    return user


@api.get("/groups", response=list[schemas.GroupSchema])
# @paginate(PageNumberPagination)
def groups(request, search: str = None) -> list[models.Group]:
    groups = models.Group.objects.all()
    if search:
        groups = groups.filter(
            name__icontains=search
        )  # , group_type__icontains=search)
    return groups


@api.get("/group-types", response=list[str])
def group_types(request):
    return [choice[0] for choice in models.Group.GROUP_TYPE_CHOICES]


@api.get("/groups/{group_id}", response=schemas.GroupSchema)
def get_group(request, group_id: UUID):
    group = models.Group.objects.get(id=group_id)
    return group


@api.get("/memberships", response=list[schemas.MembershipSchema])
# @paginate(PageNumberPagination)
def memberships(request, search: str = None) -> list[models.GroupMembership]:
    memberships = models.GroupMembership.objects.all()
    if search:
        memberships = memberships.filter(
            user__username__icontains=search
        )  # , group_type__icontains=search)
    return memberships


@api.get("/roles", response=list[schemas.RoleSchema])
# @paginate(PageNumberPagination)
def roles(request, search: str = None) -> list[models.Role]:
    roles = models.Role.objects.all()
    if search:
        roles = roles.filter(name__icontains=search)  # , group_type__icontains=search)
    return roles


@api.get("/sites", response=list[schemas.SharePointSiteSchema])
def sites(request, search: str = None) -> list[models.Site]:
    sites = models.Site.objects.all()
    if search:
        sites = sites.filter(name__icontains=search)  # , group_type__icontains=search)
    return sites


@api.get("/sites/{site_id}/drives", response=list[schemas.SharePointDriveSchema])
def site_drives(request, site_id: str):
    site = models.Site.objects.filter(site_id=site_id).first()
    if not site:
        raise Http404("Site not found")
    drives = models.Drive.objects.filter(site_id=site.id)
    return drives


@api.get("/sites/{username}", response=list[schemas.SharePointSiteSchema])
def my_sites(request, username: str):
    """
    Get sites where the specified user is a member.
    """
    sites = (
        models.SiteMember.objects.filter(user__username=username).select_related("site")
        or []
    )
    return [membership.site for membership in sites]
