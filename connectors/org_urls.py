"""Routes under the organization prefix."""

from django.urls import path

from . import views

urlpatterns = [
    path("connectors/", views.connectors_page, name="connectors"),
    path("connectors/<uuid:link_id>/select/", views.sharepoint_select, name="connector_select"),
    path("connectors/<uuid:link_id>/unlink/", views.unlink, name="connector_unlink"),
    path("connectors/<uuid:link_id>/sync/", views.sync_now, name="connector_sync"),
]
