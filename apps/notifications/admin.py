from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["user", "application", "status", "is_read", "created_at"]
    list_filter = ["is_read", "status"]
