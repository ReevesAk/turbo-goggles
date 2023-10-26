from django.core.management.base import BaseCommand
import subprocess

class Command(BaseCommand):
    help = "Enforcing a style guide on all files using Flake8."

    def handle(self, *args, **options):
        # Define the path where you want to run Flake8
        project_path = '/'

        try:
            # Run Flake8 using subprocess
            result = subprocess.run(['flake8', project_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0:
                self.stdout.write(self.style.SUCCESS("Flake8 passed without issues."))
            else:
                self.stdout.write(self.style.ERROR("Flake8 found issues in your code. See the output below:"))
                self.stdout.write(result.stdout)
                print(result.stdout)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR("Flake8 is not installed. Please install Flake8 using 'pip install flake8'."))
