"""Organization-free callback routes (providers need one exact redirect URI)."""

from django.urls import path

from . import views

app_name = "connectors"

urlpatterns = [
    path("google/start/<slug:slug>/", views.google_start, name="google_start"),
    path("google/callback/", views.google_callback, name="google_callback"),
    path("microsoft/start/<slug:slug>/", views.microsoft_start, name="microsoft_start"),
    path("microsoft/callback/", views.microsoft_callback, name="microsoft_callback"),
]
