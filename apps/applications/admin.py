from django.contrib import admin

from .models import (
    Application, Decision, DocumentNote, InfoRequest, Review, ReviewAssignment, Sequence, StatusHistory,
)


class SequenceInline(admin.TabularInline):
    model = Sequence
    extra = 0
    fields = ["number", "validation_status", "original_filename", "size", "uploaded_by", "uploaded_at"]
    readonly_fields = fields
    can_delete = False


class StatusHistoryInline(admin.TabularInline):
    model = StatusHistory
    extra = 0
    fields = ["created_at", "from_status", "to_status", "actor", "note"]
    readonly_fields = fields
    can_delete = False


class ReviewAssignmentInline(admin.TabularInline):
    model = ReviewAssignment
    extra = 0
    fields = ["section", "reviewer", "assigned_by", "assigned_at"]
    readonly_fields = fields
    can_delete = False


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ["reference_no", "product_name", "company", "application_type", "status", "assigned_reviewer", "updated_at"]
    list_filter = ["status", "application_type"]
    search_fields = ["reference_no", "product_name", "active_ingredients", "company__name_en"]
    readonly_fields = ["reference_no", "status", "created_at", "updated_at", "submitted_at"]
    inlines = [ReviewAssignmentInline, SequenceInline, StatusHistoryInline]


admin.site.register(Review)
admin.site.register(InfoRequest)
admin.site.register(Decision)


@admin.register(DocumentNote)
class DocumentNoteAdmin(admin.ModelAdmin):
    """Read-only: notes belong to their authors and are changed in the document viewer."""

    list_display = ["application", "path", "page", "section", "author", "created_at"]
    list_filter = ["section"]
    search_fields = ["application__reference_no", "body", "path"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
