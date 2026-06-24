from django.apps import AppConfig


class FmcgConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fmcg"

    def ready(self):
        from . import signals  # noqa
