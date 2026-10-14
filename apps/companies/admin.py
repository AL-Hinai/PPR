from django.contrib import admin

from .models import Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["name_en", "name_ar", "registration_no", "country", "is_verified"]
    list_filter = ["is_verified", "country"]
    search_fields = ["name_en", "name_ar", "registration_no", "license_no"]
