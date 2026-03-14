import datetime
import decimal
import threading

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Attachment, AuditLog, Comment, Workflow

_pre_save_snapshots = threading.local()

# Fields to track per model (FK fields stored as _id suffix)
_WORKFLOW_TRACKED_FIELDS = [
    "title",
    "description",
    "priority",
    "deadline",
    "current_state_id",
    "workflow_type_id",
    "owner_id",
    "referred_to_id",
    "relationship_type_id",
]
_COMMENT_TRACKED_FIELDS = ["text"]
_ATTACHMENT_TRACKED_FIELDS = ["name", "file", "attachment_type"]


def _serialize(value):
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    return value


def _snapshot(instance, fields):
    return {f: _serialize(getattr(instance, f, None)) for f in fields}


def _diff(old, new):
    changes = {}
    for key in old:
        old_val = old[key]
        new_val = new.get(key)
        if old_val != new_val:
            changes[key] = {"from": old_val, "to": new_val}
    return changes


def _log(instance, action, user=None, changes=None):
    AuditLog.objects.create(
        content_type=ContentType.objects.get_for_model(instance),
        object_id=instance.pk,
        action=action,
        user=user,
        changes=changes or {},
    )


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


@receiver(pre_save, sender=Workflow)
def workflow_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
        if not hasattr(_pre_save_snapshots, "workflow"):
            _pre_save_snapshots.workflow = {}
        _pre_save_snapshots.workflow[instance.pk] = _snapshot(
            old, _WORKFLOW_TRACKED_FIELDS
        )
    except sender.DoesNotExist:
        pass


@receiver(post_save, sender=Workflow)
def workflow_post_save(sender, instance, created, **kwargs):
    if created:
        _log(instance, "create", user=instance.owner)
        return

    snapshots = getattr(_pre_save_snapshots, "workflow", {})
    old = snapshots.pop(instance.pk, None)
    changes = _diff(old, _snapshot(instance, _WORKFLOW_TRACKED_FIELDS)) if old else {}
    if changes:
        _log(instance, "update", user=instance.owner, changes=changes)


@receiver(post_delete, sender=Workflow)
def workflow_post_delete(sender, instance, **kwargs):
    _log(instance, "delete", user=instance.owner)


# ---------------------------------------------------------------------------
# Comment
# ---------------------------------------------------------------------------


@receiver(pre_save, sender=Comment)
def comment_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
        if not hasattr(_pre_save_snapshots, "comment"):
            _pre_save_snapshots.comment = {}
        _pre_save_snapshots.comment[instance.pk] = _snapshot(
            old, _COMMENT_TRACKED_FIELDS
        )
    except sender.DoesNotExist:
        pass


@receiver(post_save, sender=Comment)
def comment_post_save(sender, instance, created, **kwargs):
    if created:
        _log(instance, "create", user=instance.user)
        return

    snapshots = getattr(_pre_save_snapshots, "comment", {})
    old = snapshots.pop(instance.pk, None)
    changes = _diff(old, _snapshot(instance, _COMMENT_TRACKED_FIELDS)) if old else {}
    if changes:
        _log(instance, "update", user=instance.user, changes=changes)


@receiver(post_delete, sender=Comment)
def comment_post_delete(sender, instance, **kwargs):
    _log(instance, "delete", user=instance.user)


# ---------------------------------------------------------------------------
# Attachment
# ---------------------------------------------------------------------------


@receiver(pre_save, sender=Attachment)
def attachment_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
        if not hasattr(_pre_save_snapshots, "attachment"):
            _pre_save_snapshots.attachment = {}
        _pre_save_snapshots.attachment[instance.pk] = _snapshot(
            old, _ATTACHMENT_TRACKED_FIELDS
        )
    except sender.DoesNotExist:
        pass


@receiver(post_save, sender=Attachment)
def attachment_post_save(sender, instance, created, **kwargs):
    if created:
        _log(instance, "create")
        return

    snapshots = getattr(_pre_save_snapshots, "attachment", {})
    old = snapshots.pop(instance.pk, None)
    changes = _diff(old, _snapshot(instance, _ATTACHMENT_TRACKED_FIELDS)) if old else {}
    if changes:
        _log(instance, "update", changes=changes)


@receiver(post_delete, sender=Attachment)
def attachment_post_delete(sender, instance, **kwargs):
    _log(instance, "delete")
