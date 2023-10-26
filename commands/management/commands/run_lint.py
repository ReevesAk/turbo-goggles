from django.core.management.base import BaseCommand
import subprocess

class Command(BaseCommand):
    help = "Formatting all projects files."

    def handle(self, *args, **options):
        # Define the path where you want to run Black
        project_path = '/'

        try:
            # Run Black using subprocess
            result = subprocess.run(['black', project_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0:
                self.stdout.write(self.style.SUCCESS("Black successfully formatted your code."))
            else:
                self.stdout.write(self.style.ERROR("Black encountered issues during formatting. See the output below:"))
                self.stdout.write(result.stdout)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR("Black is not installed. Please install Black using 'pip install black'."))
