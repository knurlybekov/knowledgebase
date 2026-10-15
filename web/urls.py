from django.urls import path

from . import views

app_name = "web"

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("metrics", views.metrics, name="metrics"),
    path("", views.home, name="home"),
    # Filled by later steps; placeholders keep the navigation resolvable.
    path("search/", views.placeholder, name="search"),
    path("investigations/", views.placeholder, name="investigations"),
    path("decisions/", views.placeholder, name="decisions"),
    path("connectors/", views.placeholder, name="connectors"),
    path("administration/", views.placeholder, name="administration"),
]
