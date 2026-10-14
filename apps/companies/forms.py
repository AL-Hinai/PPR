from django import forms

from apps.core.forms import StyledFormMixin

from .models import Company


class CompanyProfileForm(StyledFormMixin, forms.ModelForm):
    """Contact details a company may edit itself. Legal identifiers are staff-managed."""

    class Meta:
        model = Company
        fields = ["name_ar", "address", "contact_email", "contact_phone"]
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}
