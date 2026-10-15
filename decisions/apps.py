from django.apps import AppConfig


class DecisionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "decisions"

    def ready(self):
        from knowledge.api import register_publish_hook, register_purge_hook

        from .service import purge_records_for_version
        from .tasks import on_publish

        register_purge_hook(purge_records_for_version)
        register_publish_hook(on_publish)
