from django.apps import AppConfig


class AnswersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "answers"

    def ready(self):
        from knowledge.api import register_purge_hook

        from .service import purge_answers_for_version

        register_purge_hook(purge_answers_for_version)
