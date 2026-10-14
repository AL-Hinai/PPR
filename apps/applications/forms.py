from django import forms
from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.core.forms import StyledFormMixin

from .models import Application, Decision, Review


class ApplicationForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Application
        fields = [
            "application_type",
            "product_name",
            "active_ingredients",
            "dosage_form",
            "strength",
            "route",
            "atc_code",
        ]
        help_texts = {
            "active_ingredients": _("Separate multiple ingredients with commas."),
            "atc_code": _("WHO Anatomical Therapeutic Chemical code, e.g. N02BE01."),
        }


class SequenceUploadForm(StyledFormMixin, forms.Form):
    package = forms.FileField(
        label=_("eCTD package (.zip)"),
        validators=[FileExtensionValidator(["zip"])],
        help_text=_("A zip file containing one sequence folder (e.g. 0000/) with index.xml at its root."),
    )

    def clean_package(self):
        package = self.cleaned_data["package"]
        limit = settings.ECTD_MAX_UPLOAD_MB * 1024 * 1024
        if package.size > limit:
            raise forms.ValidationError(
                _("The package is larger than %(limit)s MB.") % {"limit": settings.ECTD_MAX_UPLOAD_MB}
            )
        return package


class ResponseUploadForm(SequenceUploadForm):
    note = forms.CharField(
        label=_("Response summary"),
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Briefly describe how the questions are answered."),
    )


class AssignReviewerForm(StyledFormMixin, forms.Form):
    reviewer = forms.ModelChoiceField(
        label=_("Reviewer"), queryset=User.objects.filter(role=User.Role.REVIEWER, is_active=True)
    )


class ReviewForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Review
        fields = ["section", "assessment", "comments"]
        widgets = {"comments": forms.Textarea(attrs={"rows": 4})}


class InfoRequestForm(StyledFormMixin, forms.Form):
    questions = forms.CharField(label=_("Questions to the applicant"), widget=forms.Textarea(attrs={"rows": 5}))
    due_date = forms.DateField(label=_("Response due"), required=False, widget=forms.DateInput(attrs={"type": "date"}))


class CompleteReviewForm(StyledFormMixin, forms.Form):
    recommendation = forms.ChoiceField(
        label=_("Recommendation"), choices=Application.Recommendation.choices, widget=forms.RadioSelect
    )
    summary = forms.CharField(label=_("Assessment summary"), widget=forms.Textarea(attrs={"rows": 4}))


class DecisionForm(StyledFormMixin, forms.Form):
    outcome = forms.ChoiceField(label=_("Decision"), choices=Decision.Outcome.choices, widget=forms.RadioSelect)
    justification = forms.CharField(label=_("Justification"), widget=forms.Textarea(attrs={"rows": 4}))


class ReturnForm(StyledFormMixin, forms.Form):
    note = forms.CharField(
        label=_("What should the reviewer re-examine?"), widget=forms.Textarea(attrs={"rows": 3})
    )
