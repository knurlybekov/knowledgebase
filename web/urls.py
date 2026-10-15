from django.urls import path

from connectors.org_urls import urlpatterns as connector_urls

from . import views

app_name = "web"

urlpatterns = [
    *connector_urls,
    path("healthz", views.healthz, name="healthz"),
    path("metrics", views.metrics, name="metrics"),
    path("", views.home, name="home"),
    # Filled by later steps; placeholders keep the navigation resolvable.
    path("search/", views.placeholder, name="search"),
    path("investigations/", views.placeholder, name="investigations"),
    path("decisions/", views.placeholder, name="decisions"),
    path("administration/", views.placeholder, name="administration"),
]
