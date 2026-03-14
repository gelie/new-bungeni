from django.db.models import Q
from ninja import NinjaAPI
from ninja.pagination import RouterPaginated

from workflows.models import Group, GroupMembership, Role, User

from .schemas import GroupSchema, MembershipSchema, RoleSchema, UserSchema

api = NinjaAPI(default_router=RouterPaginated())


@api.get("/health")
def health(request):
    return {"status": "ok"}


@api.get("/workflows")
def workflows(request):
    return {"workflows": "workflows"}


@api.get("/workflows/{workflow_id}")
def workflow(request, workflow_id: int):
    return {"workflow": "workflow"}


@api.get("/users/", response=list[UserSchema])
def users(request, search: str = None):
    users = User.objects.all()
    if search:
        users = users.filter(
            Q(username__icontains=search)
            | Q(last_name__icontains=search)
            | Q(first_name__icontains=search)
        )
    return users


@api.get("/users/{user_id}", response=UserSchema)
def user(request, user_id: int):
    user = User.objects.get(id=user_id)
    return user


@api.get("/groups", response=list[GroupSchema])
# @paginate(PageNumberPagination)
def groups(request, search: str = None) -> list[Group]:
    groups = Group.objects.all()
    if search:
        groups = groups.filter(
            name__icontains=search
        )  # , group_type__icontains=search)
    return groups


@api.get("/group-types", response=list[str])
def group_types(request):
    return [choice[0] for choice in Group.GROUP_TYPE_CHOICES]


@api.get("/groups/{group_id}", response=GroupSchema)
def get_group(request, group_id: int):
    group = Group.objects.get(id=group_id)
    return group


@api.get("/memberships", response=list[MembershipSchema])
# @paginate(PageNumberPagination)
def memberships(request, search: str = None) -> list[GroupMembership]:
    memberships = GroupMembership.objects.all()
    if search:
        memberships = memberships.filter(
            user__username__icontains=search
        )  # , group_type__icontains=search)
    return memberships


@api.get("/roles", response=list[RoleSchema])
# @paginate(PageNumberPagination)
def roles(request, search: str = None) -> list[Role]:
    roles = Role.objects.all()
    if search:
        roles = roles.filter(name__icontains=search)  # , group_type__icontains=search)
    return roles
