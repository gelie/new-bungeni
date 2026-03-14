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
def users(request, query: str = None):
    users = User.objects.all()
    if query:
        users = users.filter(username__icontains=query)
    return users


@api.get("/users/{user_id}", response=UserSchema)
def user(request, user_id: int):
    user = User.objects.get(id=user_id)
    return user


@api.get("/groups", response=list[GroupSchema])
# @paginate(PageNumberPagination)
def groups(request, query: str = None) -> list[Group]:
    groups = Group.objects.all()
    if query:
        groups = groups.filter(name__icontains=query)  # , group_type__icontains=query)
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
def memberships(request, query: str = None) -> list[GroupMembership]:
    memberships = GroupMembership.objects.all()
    if query:
        memberships = memberships.filter(
            user__username__icontains=query
        )  # , group_type__icontains=query)
    return memberships


@api.get("/roles", response=list[RoleSchema])
# @paginate(PageNumberPagination)
def roles(request, query: str = None) -> list[Role]:
    roles = Role.objects.all()
    if query:
        roles = roles.filter(name__icontains=query)  # , group_type__icontains=query)
    return roles
