"""Role-based access helpers used by every view."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import User


def role_required(*roles):
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if user.role not in roles:
                raise PermissionDenied
            if user.role == User.Role.COMPANY and not user.company_id:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


company_required = role_required(User.Role.COMPANY)
reviewer_required = role_required(User.Role.REVIEWER)
hod_required = role_required(User.Role.HOD)
staff_required = role_required(User.Role.REVIEWER, User.Role.HOD)
any_role_required = role_required(*User.Role.values)
