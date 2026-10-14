from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.accounts.permissions import company_required

from .forms import CompanyProfileForm


@company_required
def profile(request):
    company = request.user.company
    form = CompanyProfileForm(request.POST or None, instance=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Company profile updated."))
        return redirect("companies:profile")
    return render(request, "companies/profile.html", {"company": company, "form": form})
