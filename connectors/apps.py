from django.apps import AppConfig


class ConnectorsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "connectors"

    def ready(self):
        from organizations.api import register_offboarding_hook

        from .api import revoke_user_links

        register_offboarding_hook(revoke_user_links)
