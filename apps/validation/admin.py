from django.contrib import admin

from .models import Finding, ValidationJob, ValidationRun


class FindingInline(admin.TabularInline):
    model = Finding
    extra = 0
    readonly_fields = ["layer", "rule_code", "severity", "file_path", "location", "detail"]
    can_delete = False


@admin.register(ValidationRun)
class ValidationRunAdmin(admin.ModelAdmin):
    list_display = ["pk", "sequence", "started_at", "error_count", "warning_count", "validator_version"]
    readonly_fields = [f.name for f in ValidationRun._meta.fields]
    inlines = [FindingInline]


@admin.register(ValidationJob)
class ValidationJobAdmin(admin.ModelAdmin):
    list_display = ["pk", "sequence", "kind", "status", "attempts", "created_at", "finished_at"]
    list_filter = ["status", "kind"]
    readonly_fields = [f.name for f in ValidationJob._meta.fields if f.name != "status"]
    actions = ["requeue"]

    @admin.action(description="Queue again")
    def requeue(self, request, queryset):
        queryset.update(status=ValidationJob.Status.QUEUED, attempts=0, error="")
