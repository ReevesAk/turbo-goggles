from django.core.management.base import BaseCommand

from accounts.models import User


class Command(BaseCommand):
    help = "Check is a super admin exists."

    def handle(self, *args, **options):
        account_type = "SuperAdmin"
        try:
            User.objects.get(account_type=account_type)
            self.stdout.write(
                self.style.SUCCESS(f'A user with account type "{account_type}" exists.')
            )
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f'A user with account type "{account_type}" does not exist.'
                )
            )
