from uuid import UUID

from ninja import ModelSchema, Schema

from workflows.models import Group, GroupMembership, Role, Site, User


class SearchQuerySchema(Schema):
    search: str | None = None


class MembershipFilterQuerySchema(Schema):
    role: str | None = None
    group: str | None = None
    role_id: UUID | None = None
    group_id: UUID | None = None
    role_slug: str | None = None
    group_slug: str | None = None


class UserQuerySchema(SearchQuerySchema, MembershipFilterQuerySchema):
    pass


class UserSchema(ModelSchema):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            # "is_staff",
            # "is_superuser",
            # "date_joined",
            # "last_login",
        ]


class GroupSchema(ModelSchema):
    class Meta:
        model = Group
        fields = ["id", "name", "slug"]


class RoleSchema(ModelSchema):
    class Meta:
        model = Role
        fields = ["id", "name", "slug"]


class MembershipSchema(ModelSchema):
    class Meta:
        model = GroupMembership
        fields = ["user", "group", "role"]


class UserGroupMembershipSchema(ModelSchema):
    group: GroupSchema
    role: RoleSchema

    class Meta:
        model = GroupMembership
        fields = ["id", "group", "role", "start_date", "end_date", "is_active"]


class UserWithMembershipSchema(UserSchema):
    groupmembership: list[UserGroupMembershipSchema]
    groupmembership_count: int

    @staticmethod
    def resolve_groupmembership(obj: User):
        memberships = getattr(obj, "_groupmembership", None)
        if memberships is not None:
            return memberships
        return obj.memberships.select_related("group", "role")

    @staticmethod
    def resolve_groupmembership_count(obj: User):
        memberships = getattr(obj, "_groupmembership", None)
        if memberships is not None:
            # memberships may be a QuerySet or an iterable
            try:
                return memberships.count()
            except Exception:
                return len(list(memberships))
        # Fallback to counting all memberships
        try:
            return obj.memberships.count()
        except Exception:
            return len(list(obj.memberships.select_related("group", "role")))


class SharePointSiteSchema(ModelSchema):
    class Meta:
        model = Site
        fields = ["site_id", "name", "url", "is_personal_site"]


class SharePointDriveSchema(Schema):
    drive_id: str
    name: str
    site: SharePointSiteSchema
    # class Meta:
    #     model = Drive
    #     fields = ["drive_id", "name", "site"]
