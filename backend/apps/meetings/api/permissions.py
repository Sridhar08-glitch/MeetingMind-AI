"""Object-level permissions for meetings."""
from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """Grant access only to the meeting's owner."""

    message = "You do not have permission to access this meeting."

    def has_object_permission(self, request, view, obj) -> bool:
        owner = getattr(obj, "owner", None) or getattr(getattr(obj, "meeting", None), "owner", None)
        return owner is not None and owner == request.user
