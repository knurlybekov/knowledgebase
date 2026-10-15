from django.urls import path

from . import views

urlpatterns = [
    path("decisions/", views.decisions_list, name="decisions"),
    path("decisions/new/", views.decision_create, name="decision_create"),
    path("decisions/<uuid:record_id>/", views.decision_detail, name="decision_detail"),
    path(
        "decisions/<uuid:record_id>/transition/",
        views.decision_transition,
        name="decision_transition",
    ),
]
