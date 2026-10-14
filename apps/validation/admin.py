from django.contrib import admin

from .models import Finding, ValidationRun


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
