from django.core.management.base import BaseCommand

from accounts.models import User


class Command(BaseCommand):
    help = "Check is a super admin exists."

    def handle(self, *args, **options):
        active_role = "SuperAdmin"
        try:
            User.objects.get(active_role=active_role)
            self.stdout.write(
                self.style.SUCCESS(f'A user with account type "{active_role}" exists.')
            )
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f'A user with account type "{active_role}" does not exist.'
                )
            )
