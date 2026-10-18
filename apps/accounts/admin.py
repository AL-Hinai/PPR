from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # Specialties are the Head of Department's decision (Reviewers page), so they are read-only here.
    readonly_fields = ["specialties_display", "specialties_updated_by", "specialties_updated_at"]
    list_display = ["username", "email", "first_name", "last_name", "role", "specialties_display", "company", "is_active"]
    list_filter = ["role", "is_active", "company"]
    fieldsets = (
        *BaseUserAdmin.fieldsets,
        (_("PPR"), {"fields": ("role", "company", "preferred_language")}),
        (_("Review specialties (set by the Head of Department)"),
         {"fields": ("specialties_display", "specialties_updated_by", "specialties_updated_at")}),
    )
    add_fieldsets = (
        *BaseUserAdmin.add_fieldsets,
        (_("PPR"), {"fields": ("email", "first_name", "last_name", "role", "company")}),
    )

    @admin.display(description=_("Specialties"))
    def specialties_display(self, user):
        return user.get_specialties_display() or "—"
