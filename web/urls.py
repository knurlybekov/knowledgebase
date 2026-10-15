from django.urls import include, path

from connectors.api import org_urlpatterns as connector_urls
from investigations.api import org_urlpatterns as investigation_urls

from . import admin_views, views

app_name = "web"

urlpatterns = [
    *connector_urls(),
    *investigation_urls(),
    path("healthz", views.healthz, name="healthz"),
    path("metrics", views.metrics, name="metrics"),
    path("", views.home, name="home"),
    # Filled by later steps; placeholders keep the navigation resolvable.
    path("search/", views.search_page, name="search"),
    path("answers/<uuid:answer_id>/", views.answer_detail, name="answer_detail"),
    path("api/v1/", include("web.api_urls")),
    path("decisions/", views.placeholder, name="decisions"),
    path("administration/", admin_views.administration, name="administration"),
]
