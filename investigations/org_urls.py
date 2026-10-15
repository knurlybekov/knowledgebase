from django.urls import path

from . import views

urlpatterns = [
    path("investigations/", views.investigations_list, name="investigations"),
    path("investigations/start/", views.investigations_start, name="investigation_start"),
    path(
        "investigations/<uuid:investigation_id>/",
        views.investigation_detail,
        name="investigation_detail",
    ),
    path(
        "investigations/<uuid:investigation_id>/cancel/",
        views.investigation_cancel,
        name="investigation_cancel",
    ),
    path(
        "api/v1/investigations/<uuid:investigation_id>",
        views.investigation_json,
        name="api_investigation",
    ),
]
