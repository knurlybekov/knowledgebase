from django.apps import AppConfig


class InvestigationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "investigations"

    def ready(self):
        from knowledge.api import register_purge_hook
        from organizations.api import register_offboarding_hook

        from .service import cancel_user_investigations, purge_investigations_for_version

        register_purge_hook(purge_investigations_for_version)
        register_offboarding_hook(cancel_user_investigations)
