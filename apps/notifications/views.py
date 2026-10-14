from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST


@login_required
def notification_list(request):
    items = request.user.notifications.select_related("application")[:100]
    return render(request, "notifications/list.html", {"items": items})


@login_required
def dropdown(request):
    items = request.user.notifications.select_related("application")[:8]
    return render(request, "notifications/_dropdown.html", {"items": items})


@login_required
def open_notification(request, pk):
    item = get_object_or_404(request.user.notifications, pk=pk)
    if not item.is_read:
        item.is_read = True
        item.save(update_fields=["is_read"])
    return redirect(item.application.get_absolute_url())


@login_required
@require_POST
def mark_all_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()):
        target = "notifications:list"
    return redirect(target)
