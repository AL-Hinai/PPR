from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("v1/applications/", views.application_list, name="applications"),
    path("v1/applications/<str:reference_no>/", views.application_detail, name="application"),
]
