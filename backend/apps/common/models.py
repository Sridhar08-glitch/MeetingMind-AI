"""Abstract base models shared across the project.

Every domain model inherits from :class:`BaseModel`, guaranteeing UUID primary
keys (never expose sequential ids), automatic timestamps, audit columns, and
soft-delete support.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from .managers import AllObjectsManager, SoftDeleteManager
from .middleware import get_current_user


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditModel(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, hard: bool = False):
        """Soft-delete by default; pass ``hard=True`` to remove permanently."""
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
        return None

    def restore(self) -> None:
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


class BaseModel(UUIDModel, TimeStampedModel, AuditModel, SoftDeleteModel):
    """Canonical base combining UUID, timestamps, audit and soft-delete."""

    class Meta:
        abstract = True
        ordering = ("-created_at",)

    def set_acting_user(self, user) -> None:
        """Explicitly set the user attributed to the next save (services use this)."""
        self._acting_user = user

    def _resolve_actor(self):
        actor = getattr(self, "_acting_user", None)
        if actor is None:
            actor = get_current_user()
        return actor if getattr(actor, "is_authenticated", False) else None

    def save(self, *args, **kwargs):
        actor = self._resolve_actor()
        if actor is not None:
            if self._state.adding and self.created_by_id is None:
                self.created_by = actor
            self.updated_by = actor
        super().save(*args, **kwargs)
