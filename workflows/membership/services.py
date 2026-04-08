"""
Core membership business-logic services.

Provides a thin, testable API that the sync commands (and views / API
endpoints) can call instead of embedding membership logic inline.
"""

import logging
from typing import Dict, Optional

from django.utils import timezone

from workflows.models import Group, GroupMembership, Role, User

logger = logging.getLogger(__name__)


class MembershipService:
    """High-level operations on GroupMembership records."""

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_active_membership(user: User, group: Group) -> Optional[GroupMembership]:
        """Return the active membership for *user* in *group*, or ``None``."""
        return (
            GroupMembership.objects.filter(user=user, group=group, is_active=True)
            .select_related("role")
            .first()
        )

    @staticmethod
    def get_user_memberships(user: User, active_only: bool = True):
        """Return all memberships for a user."""
        qs = GroupMembership.objects.filter(user=user).select_related("group", "role")
        if active_only:
            qs = qs.filter(is_active=True)
        return qs

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    @staticmethod
    def create_membership(
        user: User,
        group: Group,
        role: Role,
        start_date=None,
    ) -> GroupMembership:
        """Create a new active membership record."""
        if start_date is None:
            start_date = timezone.now().date()
        return GroupMembership.objects.create(
            user=user,
            group=group,
            role=role,
            start_date=start_date,
            is_active=True,
        )

    @staticmethod
    def reactivate_membership(
        membership: GroupMembership, role: Role
    ) -> GroupMembership:
        """Re-activate a previously deactivated membership."""
        membership.is_active = True
        membership.end_date = None
        membership.role = role
        membership.save(update_fields=["is_active", "end_date", "role"])
        return membership

    @staticmethod
    def update_role(membership: GroupMembership, role: Role) -> GroupMembership:
        """Change the role on an existing active membership."""
        membership.role = role
        membership.save(update_fields=["role"])
        return membership

    @staticmethod
    def deactivate_membership(membership: GroupMembership) -> GroupMembership:
        """Deactivate a membership (set end_date to today)."""
        membership.is_active = False
        membership.end_date = timezone.now().date()
        membership.save(update_fields=["is_active", "end_date"])
        return membership

    @staticmethod
    def deactivate_user_memberships(user: User) -> int:
        """Deactivate all active memberships for a user. Returns count."""
        today = timezone.now().date()
        return GroupMembership.objects.filter(user=user, is_active=True).update(
            is_active=False, end_date=today
        )

    # ------------------------------------------------------------------
    # Sync-oriented helpers
    # ------------------------------------------------------------------

    @staticmethod
    def ensure_membership(
        user: User,
        group: Group,
        role: Role,
        existing_memberships: Optional[Dict] = None,
        dry_run: bool = False,
    ) -> Dict:
        """Idempotent upsert used during Oracle sync.

        Returns a dict ``{"action": "created"|"reactivated"|"updated"|"unchanged", ...}``.
        """
        membership_key = (user.id, group.id) if user.id and user.id != -1 else None
        existing = (
            existing_memberships.get(membership_key)
            if existing_memberships and membership_key
            else None
        )

        if not existing:
            if not dry_run:
                MembershipService.create_membership(user, group, role)
            logger.debug(
                "%s membership: %s -> %s as %s",
                "[DRY RUN] Would create" if dry_run else "✨ Created",
                user.username,
                group.name,
                role.name,
            )
            return {"action": "created", "group": group.name, "role": role.name}

        if not existing.is_active:
            if not dry_run:
                MembershipService.reactivate_membership(existing, role)
            logger.debug(
                "%s membership: %s -> %s as %s",
                "[DRY RUN] Would reactivate" if dry_run else "🔄 Reactivated",
                user.username,
                group.name,
                role.name,
            )
            return {"action": "reactivated", "group": group.name, "role": role.name}

        if existing.role != role:
            if not dry_run:
                MembershipService.update_role(existing, role)
            logger.debug(
                "%s role: %s in %s from %s to %s",
                "[DRY RUN] Would update" if dry_run else "🔄 Updated",
                user.username,
                group.name,
                existing.role.name,
                role.name,
            )
            return {"action": "updated", "group": group.name, "role": role.name}

        return {"action": "unchanged", "group": group.name, "role": role.name}
