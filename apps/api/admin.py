from django.contrib import admin

from .models import ApiToken


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    """Keys are issued with `manage.py create_api_key` (the key is shown once); here they can be switched off."""

    list_display = ["name", "prefix", "is_active", "created_at", "last_used_at", "created_by"]
    list_filter = ["is_active"]
    readonly_fields = ["name", "prefix", "created_at", "last_used_at", "created_by"]
    fields = ["name", "prefix", "is_active", "created_at", "last_used_at", "created_by"]

    def has_add_permission(self, request):
        return False
