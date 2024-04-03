from django.core.management.base import BaseCommand
from django.apps import apps

class Command(BaseCommand):
    help = 'Purge data from all models in the myapp app'

    def handle(self, *args, **kwargs):
        app_name = 'banking'

        # Get all models from the specified app
        models = apps.get_app_config(app_name).get_models()

        for model in models:
            model.objects.all().delete()

        self.stdout.write(self.style.SUCCESS(f'Successfully purged data from all models in the {app_name} app.'))
