"""JSON endpoints, mounted at /o/<slug>/api/v1/."""

from django.urls import path

from . import api_views

urlpatterns = [
    path("search", api_views.api_search, name="api_search"),
    path("answers", api_views.api_answer, name="api_answer"),
]
