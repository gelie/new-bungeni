"""
Membership validation and correctness checking system.

Provides comprehensive validation for GroupMembership data to prevent
issues like group name collisions and incorrect assignments.
"""

from collections import defaultdict
from typing import Dict, List

from django.db import models
from django.utils import timezone

from workflows.management.commands.sync_base import OracleSyncBase
from workflows.models import Group, GroupMembership, User

from .exceptions import GroupNameCollisionError


class MembershipValidator:
    """Comprehensive membership validation system."""

    def __init__(self):
        self.sync_base = OracleSyncBase()
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.stats: Dict[str, int] = defaultdict(int)

    def validate_all(self) -> Dict:
        """Perform comprehensive validation of all membership data."""
        self.errors.clear()
        self.warnings.clear()
        self.stats.clear()

        print("🔍 Starting comprehensive membership validation...")

        self._check_group_name_collisions()
        self._validate_membership_integrity()
        self._check_orphaned_memberships()
        self._validate_role_assignments()
        self._check_duplicate_memberships()
        self._validate_hierarchical_consistency()

        return self._generate_report()

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_group_name_collisions(self):
        """Check for group name collisions in normalization."""
        print("  🔍 Checking group name collisions...")

        normalized_groups: Dict[str, list] = defaultdict(list)
        for group in Group.objects.all():
            normalized = self.sync_base.strip_group_code_prefix(group.name)
            normalized_groups[normalized].append(group)

        collisions_found = 0
        for normalized, groups_list in normalized_groups.items():
            if len(groups_list) > 1:
                collisions_found += 1
                self.warnings.append(
                    f"Group name collision: {len(groups_list)} groups "
                    f"normalize to '{normalized}'"
                )
                for group in groups_list:
                    self.warnings.append(f"  - {group.name} (ID: {group.id})")

        self.stats["group_collisions"] = collisions_found
        if collisions_found > 0:
            self.warnings.append(
                f"⚠️  Found {collisions_found} group name collisions"
            )
        else:
            print("    ✅ No group name collisions found")

    def _validate_membership_integrity(self):
        """Validate basic membership data integrity."""
        print("  🔍 Validating membership integrity...")

        invalid_users = GroupMembership.objects.filter(user__isnull=True).count()
        invalid_groups = GroupMembership.objects.filter(group__isnull=True).count()
        invalid_roles = GroupMembership.objects.filter(role__isnull=True).count()

        if invalid_users > 0:
            self.errors.append(
                f"Found {invalid_users} memberships with invalid user"
            )
        if invalid_groups > 0:
            self.errors.append(
                f"Found {invalid_groups} memberships with invalid group"
            )
        if invalid_roles > 0:
            self.errors.append(
                f"Found {invalid_roles} memberships with invalid role"
            )

        invalid_dates = GroupMembership.objects.filter(
            end_date__lt=models.F("start_date")
        ).count()
        if invalid_dates > 0:
            self.errors.append(
                f"Found {invalid_dates} memberships with end_date before start_date"
            )

        self.stats["invalid_foreign_keys"] = (
            invalid_users + invalid_groups + invalid_roles
        )
        self.stats["invalid_dates"] = invalid_dates

        if (
            self.stats["invalid_foreign_keys"] == 0
            and self.stats["invalid_dates"] == 0
        ):
            print("    ✅ All membership data integrity checks passed")

    def _check_orphaned_memberships(self):
        """Check for users with multiple active memberships in the same group."""
        print("  🔍 Checking for orphaned memberships...")

        duplicate_active = (
            GroupMembership.objects.values("user", "group")
            .annotate(
                active_count=models.Count(
                    "id", filter=models.Q(is_active=True)
                )
            )
            .filter(active_count__gt=1)
            .count()
        )

        if duplicate_active > 0:
            self.warnings.append(
                f"Found {duplicate_active} users with multiple active "
                f"memberships in same group"
            )

        self.stats["duplicate_active_memberships"] = duplicate_active

        if duplicate_active == 0:
            print("    ✅ No orphaned memberships found")

    def _validate_role_assignments(self):
        """Validate role assignments for consistency."""
        print("  🔍 Validating role assignments...")

        users = User.objects.annotate(
            membership_count=models.Count(
                "memberships", filter=models.Q(memberships__is_active=True)
            )
        ).filter(membership_count__gt=5)

        if users.exists():
            self.warnings.append(
                f"Found {users.count()} users with >5 active memberships"
            )
            for user in users[:5]:
                self.warnings.append(
                    f"  - {user.username}: {user.membership_count} active memberships"
                )

        self.stats["users_many_memberships"] = users.count()

        empty_groups = Group.objects.filter(members__isnull=True).count()
        if empty_groups > 0:
            self.warnings.append(f"Found {empty_groups} groups with no members")
        self.stats["empty_groups"] = empty_groups

        if users.count() == 0 and empty_groups == 0:
            print("    ✅ All role assignments look valid")

    def _check_duplicate_memberships(self):
        """Check for duplicate membership records."""
        print("  🔍 Checking for duplicate memberships...")

        duplicates = (
            GroupMembership.objects.values("user", "group", "role", "start_date")
            .annotate(count=models.Count("id"))
            .filter(count__gt=1)
        )

        duplicate_count = duplicates.count()
        if duplicate_count > 0:
            self.errors.append(
                f"Found {duplicate_count} sets of duplicate membership records"
            )
            for dup in duplicates[:3]:
                self.errors.append(
                    f"  - User {dup['user']}, Group {dup['group']}: "
                    f"{dup['count']} duplicates"
                )
        self.stats["duplicate_memberships"] = duplicate_count

        if duplicate_count == 0:
            print("    ✅ No duplicate memberships found")

    def _validate_hierarchical_consistency(self):
        """Validate hierarchical group consistency."""
        print("  🔍 Validating hierarchical consistency...")

        hierarchy_issues = 0
        for group in Group.objects.exclude(parent=None).select_related("parent"):
            users_in_both = (
                User.objects.filter(
                    memberships__group=group, memberships__is_active=True
                )
                .filter(
                    memberships__group=group.parent,
                    memberships__is_active=True,
                )
                .distinct()
                .count()
            )
            if users_in_both > 0:
                hierarchy_issues += users_in_both
                self.warnings.append(
                    f"Found {users_in_both} users in both "
                    f"'{group.parent.name}' and '{group.name}'"
                )

        self.stats["hierarchy_issues"] = hierarchy_issues
        if hierarchy_issues == 0:
            print("    ✅ No hierarchical consistency issues found")

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _generate_report(self) -> Dict:
        return {
            "timestamp": timezone.now().isoformat(),
            "stats": dict(self.stats),
            "errors": self.errors,
            "warnings": self.warnings,
            "summary": {
                "total_errors": len(self.errors),
                "total_warnings": len(self.warnings),
                "status": (
                    "FAILED"
                    if self.errors
                    else "PASSED"
                    if not self.warnings
                    else "WARNING"
                ),
            },
        }

    def print_report(self, report: Dict):
        """Print validation report to console."""
        print("\n" + "=" * 80)
        print("🔍 MEMBERSHIP VALIDATION REPORT")
        print("=" * 80)
        print(f"📅 Timestamp: {report['timestamp']}")
        print(f"📊 Status: {report['summary']['status']}")

        print("\n📈 STATISTICS:")
        for key, value in report["stats"].items():
            print(f"   {key}: {value}")

        if report["errors"]:
            print(f"\n❌ ERRORS ({len(report['errors'])}):")
            for error in report["errors"]:
                print(f"   • {error}")

        if report["warnings"]:
            print(f"\n⚠️  WARNINGS ({len(report['warnings'])}):")
            for warning in report["warnings"]:
                print(f"   • {warning}")

        if report["summary"]["status"] == "PASSED":
            print("\n✅ All validation checks passed!")

        print("\n" + "=" * 80)


class MembershipSyncValidator:
    """Pre-sync readiness checks."""

    def __init__(self):
        self.sync_base = OracleSyncBase()

    def validate_sync_readiness(self) -> bool:
        """Return True if required groups exist and there are no critical collisions."""
        print("🔍 Validating sync readiness...")

        required_groups = [
            "National Assembly",
            "National Council of Provinces",
            "Parliament Staff",
        ]
        missing = [g for g in required_groups if not Group.objects.filter(name=g).exists()]
        if missing:
            print(f"❌ Missing required groups: {', '.join(missing)}")
            return False

        normalized_groups: Dict[str, list] = defaultdict(list)
        for group in Group.objects.all():
            normalized = self.sync_base.strip_group_code_prefix(group.name)
            normalized_groups[normalized].append(group)

        collisions = {k: v for k, v in normalized_groups.items() if len(v) > 1}
        if collisions:
            print(f"⚠️  Found {len(collisions)} group name collisions:")
            for normalized, groups_list in list(collisions.items())[:3]:
                print(f"   - {normalized}: {len(groups_list)} groups")

        print("✅ Sync readiness validation complete")
        return True

    def suggest_oracle_mapping(self, oracle_org_name: str) -> List[str]:
        """Suggest possible group mappings for an Oracle organization name."""
        normalized = self.sync_base.strip_group_code_prefix(oracle_org_name)
        candidates = []
        for group in Group.objects.all():
            group_normalized = self.sync_base.strip_group_code_prefix(group.name)
            if normalized.lower() == group_normalized.lower():
                candidates.append(group.name)
            elif (
                normalized.lower() in group_normalized.lower()
                or group_normalized.lower() in normalized.lower()
            ):
                candidates.append(f"{group.name} (partial match)")
        return candidates if candidates else ["No matches found"]

    def detect_collisions(self) -> List[GroupNameCollisionError]:
        """Return a list of collision exceptions for every normalized name
        that maps to more than one Group."""
        normalized_groups: Dict[str, list] = defaultdict(list)
        for group in Group.objects.all():
            normalized = self.sync_base.strip_group_code_prefix(group.name)
            normalized_groups[normalized].append(group)

        return [
            GroupNameCollisionError(name, groups)
            for name, groups in normalized_groups.items()
            if len(groups) > 1
        ]
