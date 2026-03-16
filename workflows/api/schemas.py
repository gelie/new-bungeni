from ninja import ModelSchema, Schema

from workflows.models import Group, GroupMembership, Role, Site, User


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
            "is_staff",
            "is_superuser",
            "date_joined",
            "last_login",
        ]


class GroupSchema(ModelSchema):
    class Meta:
        model = Group
        fields = ["name", "group_type"]


class RoleSchema(ModelSchema):
    class Meta:
        model = Role
        fields = ["name"]


class MembershipSchema(ModelSchema):
    class Meta:
        model = GroupMembership
        fields = ["user", "group", "role"]


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
