"""Object-level permissions for jobs."""
from rest_framework.permissions import BasePermission


class IsJobOwnerOrAdmin(BasePermission):
    """A user may act on their own jobs; staff/admins on any job."""

    message = "You do not have permission to access this job."

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        return bool(getattr(user, "is_staff", False) or obj.created_by_id == user.id)
