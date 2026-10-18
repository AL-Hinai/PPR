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


class ReviewTeamForm(StyledFormMixin, forms.Form):
    """The HOD assigns one specialist per CTD module and names the lead reviewer.

    Each module only offers reviewers specialised in it; modules required for the
    application type are mandatory.
    """

    def __init__(self, application, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.application = application
        reviewers = list(User.objects.filter(role=User.Role.REVIEWER, is_active=True).order_by("first_name", "username"))
        current = {a.section: a.reviewer_id for a in application.assignments.all()}
        required = application.required_sections()
        for value, label in Review.Section.choices:
            qualified = [r.pk for r in reviewers if r.can_review(value)]
            self.fields[f"section_{value}"] = forms.ModelChoiceField(
                label=label,
                queryset=User.objects.filter(pk__in=qualified).order_by("first_name", "username"),
                required=value in required,
                initial=current.get(value) or (qualified[0] if len(qualified) == 1 else None),
                empty_label=_("— not assigned —") if value not in required else "---------",
            )
            self.fields[f"section_{value}"].label_from_instance = lambda u: f"{u.display_name} ({u.get_specialties_display()})"
        self.fields["lead"] = forms.ModelChoiceField(
            label=_("Lead reviewer"),
            queryset=User.objects.filter(pk__in=[r.pk for r in reviewers]),
            initial=application.assigned_reviewer_id,
            help_text=_("Coordinates the module reviewers, sends questions to the applicant and the recommendation to you."),
        )
        self.fields["lead"].label_from_instance = lambda u: u.display_name
        # Added after StyledFormMixin ran, so style them here.
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "input")

    def section_fields(self):
        return [self[f"section_{value}"] for value in Review.Section.values]

    def sections(self):
        return {value: self.cleaned_data.get(f"section_{value}") for value in Review.Section.values}


class ReviewForm(StyledFormMixin, forms.ModelForm):
    """A module assessment; the reviewer can only pick the modules assigned to them."""

    class Meta:
        model = Review
        fields = ["section", "assessment", "comments"]
        widgets = {"comments": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, sections=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["section"].choices = [(v, l) for v, l in Review.Section.choices if v in sections]


class InfoRequestForm(StyledFormMixin, forms.Form):
    sections = forms.MultipleChoiceField(
        label=_("Modules concerned"),
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Their reviewers must assess the applicant's answer before you can complete the review."),
    )
    questions = forms.CharField(label=_("Questions to the applicant"), widget=forms.Textarea(attrs={"rows": 5}))
    due_date = forms.DateField(label=_("Response due"), required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, application, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sections"].choices = [(a.section, a.section) for a in application.assignments.all()]


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
