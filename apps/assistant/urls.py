from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("session/", views.session, name="session"),
    path("ask/", views.ask, name="ask"),
    path("new/", views.new_conversation, name="new"),
]
