from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "email", "first_name", "last_name", "role", "company", "is_active"]
    list_filter = ["role", "is_active", "company"]
    fieldsets = (
        *BaseUserAdmin.fieldsets,
        (_("PPR"), {"fields": ("role", "company", "preferred_language")}),
    )
    add_fieldsets = (
        *BaseUserAdmin.add_fieldsets,
        (_("PPR"), {"fields": ("email", "first_name", "last_name", "role", "company")}),
    )
