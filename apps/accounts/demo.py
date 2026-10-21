"""The demo accounts seed_demo creates, and the one-click sign-in offered for them.

The login page lists these accounts as buttons when ``DEMO_LOGIN`` is on. A button posts the
ordinary login form with the demo password, so sign-in still goes through ``LoginForm``,
django-axes and every other check: there is no second way into the system.
"""
from django.conf import settings

# Every account seed_demo creates, in the order the login page lists them.
# reviewer1 / reviewer2 are the retired generalist accounts: seed_demo still removes them
# with --reset, and they simply do not exist to be listed.
DEMO_USERNAMES = [
    "hod",
    "rev_regulatory",
    "rev_quality",
    "rev_nonclinical",
    "rev_clinical",
    "reviewer1",
    "reviewer2",
    "acme",
    "gulfpharma",
]


def demo_accounts():
    """The seeded demo users that exist, in DEMO_USERNAMES order; empty when demo sign-in is off."""
    if not settings.DEMO_LOGIN:
        return []
    from .models import User

    order = {username: index for index, username in enumerate(DEMO_USERNAMES)}
    users = User.objects.filter(username__in=DEMO_USERNAMES, is_active=True).select_related("company")
    return sorted(users, key=lambda user: order.get(user.username, len(order)))
