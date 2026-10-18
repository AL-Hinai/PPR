"""Optional single sign-on for department staff through the Ministry's OpenID Connect provider.

Switched on by setting OIDC_RP_CLIENT_ID (see docs/sso.md). Accounts are still issued in PPR: a provider
login only signs in an existing, active reviewer or Head of Department whose email matches. Company
applicants keep their PPR passwords.
"""
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from .models import User

STAFF_ROLES = (User.Role.REVIEWER, User.Role.HOD)


class StaffOIDCBackend(OIDCAuthenticationBackend):
    def filter_users_by_claims(self, claims):
        email = (claims.get("email") or claims.get("upn") or claims.get("preferred_username") or "").strip()
        if not email or "@" not in email:
            return self.UserModel.objects.none()
        return self.UserModel.objects.filter(email__iexact=email, is_active=True, role__in=STAFF_ROLES)

    def create_user(self, claims):  # never: OIDC_CREATE_USER is False, this is the second lock
        return None
