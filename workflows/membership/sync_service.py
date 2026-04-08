"""
Oracle-to-Django membership synchronisation service.

Extracts the group-resolution and membership-upsert logic that was
previously embedded inside ``sync_users_oracle.Command.handle_group_memberships``.
"""

import logging
from typing import Dict, Optional, Tuple

from workflows.models import Group, Role, User

from .services import MembershipService

logger = logging.getLogger(__name__)


class MembershipSyncService:
    """Resolves Oracle data to local Group/Role and delegates to MembershipService."""

    def __init__(
        self,
        group_cache: Dict[str, Group],
        role_cache: Dict[str, Role],
        strip_group_code_prefix,
        normalize_role_name,
    ):
        self._group_cache = group_cache
        self._role_cache = role_cache
        self._strip = strip_group_code_prefix
        self._normalize_role = normalize_role_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync_user_membership(
        self,
        user: User,
        oracle_row: Tuple,
        existing_memberships: Optional[Dict] = None,
        dry_run: bool = False,
    ) -> Dict:
        """Resolve the target group and role from *oracle_row* and upsert
        the membership for *user*.

        Returns a result dict with keys ``action``, ``group``, ``role``
        or ``{"action": "skipped", "reason": ...}`` on soft failures.
        """
        employeetype = oracle_row[8] or ""
        positiondesc = oracle_row[7] or ""
        child_org_name = oracle_row[11] or ""
        parent_org_name = oracle_row[12] or ""

        # --- Resolve role ---
        role = self._resolve_role(positiondesc, employeetype, user.username)
        if role is None:
            return {"action": "skipped", "reason": "no_role"}

        # --- Resolve target group ---
        target_group = self._resolve_group(
            employeetype, positiondesc, child_org_name, parent_org_name, user.username
        )
        if target_group is None:
            return {"action": "skipped", "reason": "no_group"}

        # --- Delegate upsert ---
        return MembershipService.ensure_membership(
            user=user,
            group=target_group,
            role=role,
            existing_memberships=existing_memberships,
            dry_run=dry_run,
        )

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------

    def _resolve_role(
        self, positiondesc: str, employeetype: str, username: str
    ) -> Optional[Role]:
        """Return the Role for *positiondesc*, falling back to 'Staff Member'."""
        normalized = self._normalize_role(positiondesc, employeetype)
        role = self._role_cache.get(normalized)
        if not role:
            role = self._role_cache.get("Staff Member")
            if not role:
                logger.warning(
                    "⚠️  No role found for %s, and no default "
                    "'Staff Member' role exists (user: %s)",
                    normalized,
                    username,
                )
                return None
        return role

    def _resolve_group(
        self,
        employeetype: str,
        positiondesc: str,
        child_org_name: str,
        parent_org_name: str,
        username: str,
    ) -> Optional[Group]:
        """Determine the target group from Oracle data."""
        if employeetype == "Member":
            return self._resolve_member_group(positiondesc)

        return self._resolve_staff_group(child_org_name, parent_org_name, username)

    def _resolve_member_group(self, positiondesc: str) -> Optional[Group]:
        """MP → NA or NCOP based on position description."""
        member_house = (
            positiondesc.split(":")[-1].strip() if ":" in positiondesc else ""
        )
        if "NCOP" in member_house.upper() or "PROVINCES" in member_house.upper():
            return self._group_cache.get("National Council of Provinces")
        return self._group_cache.get("National Assembly")

    def _resolve_staff_group(
        self, child_org_name: str, parent_org_name: str, username: str
    ) -> Optional[Group]:
        """Staff → child org → parent org → Parliament Staff fallback."""
        child_name = self._strip(child_org_name)
        if child_name:
            group = self._group_cache.get(child_name)
            if group:
                return group

        parent_name = self._strip(parent_org_name)
        if parent_name:
            group = self._group_cache.get(parent_name)
            if group:
                return group

        fallback = self._group_cache.get("Parliament Staff")
        if not fallback:
            logger.warning(
                "⚠️  No target group found for user %s (child=%s, parent=%s)",
                username,
                child_org_name,
                parent_org_name,
            )
        return fallback
