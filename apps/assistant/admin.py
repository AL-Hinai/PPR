from django.contrib import admin

from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ("role", "content", "application", "document_path", "provider", "prompt_tokens", "completion_tokens")
    readonly_fields = fields


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "updated_at")
    list_filter = ("user",)
    inlines = [MessageInline]
