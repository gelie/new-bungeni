"""Membership-specific exceptions."""


class MembershipError(Exception):
    """Base exception for membership operations."""


class GroupNameCollisionError(MembershipError):
    """Raised when multiple groups normalize to the same name."""

    def __init__(self, normalized_name: str, colliding_groups: list):
        self.normalized_name = normalized_name
        self.colliding_groups = colliding_groups
        names = ", ".join(g.name for g in colliding_groups)
        super().__init__(
            f"Group name collision: {len(colliding_groups)} groups "
            f"normalize to '{normalized_name}': {names}"
        )


class InvalidMembershipError(MembershipError):
    """Raised when membership data is invalid."""


class MembershipSyncError(MembershipError):
    """Raised when a membership sync operation fails."""


class GroupNotFoundError(MembershipError):
    """Raised when a target group cannot be resolved."""

    def __init__(self, oracle_org_name: str, username: str):
        self.oracle_org_name = oracle_org_name
        self.username = username
        super().__init__(
            f"No target group found for user '{username}' "
            f"(Oracle org: '{oracle_org_name}')"
        )


class RoleNotFoundError(MembershipError):
    """Raised when a role cannot be resolved."""

    def __init__(self, role_name: str, username: str):
        self.role_name = role_name
        self.username = username
        super().__init__(
            f"No role found for '{role_name}' (user: '{username}')"
        )
