from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("dropdown/", views.dropdown, name="dropdown"),
    path("<int:pk>/", views.open_notification, name="open"),
    path("read-all/", views.mark_all_read, name="read_all"),
]
