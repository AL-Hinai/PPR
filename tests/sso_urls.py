"""URLconf with the OpenID Connect routes, as config/urls.py builds it when SSO is enabled."""
from django.urls import include, path

from config.urls import urlpatterns as base

urlpatterns = [path("oidc/", include("mozilla_django_oidc.urls")), *base]
