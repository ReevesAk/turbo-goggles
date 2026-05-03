import csv
from django.core.management.base import BaseCommand
from waitlist.models import WaitlistModel


class Command(BaseCommand):
    help = "Export all waitlist data to a CSV file."

    def handle(self, *args, **options):
        filename = "waitlist_export.csv"
        fieldnames = [
            "id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "referral_code",
            "referral_count",
            "points",
            "is_student",
            "institution",
            "joined_at",
        ]
        with open(filename, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for user in WaitlistModel.objects.all():
                writer.writerow(
                    {
                        "id": user.id,
                        "first_name": user.f_name,
                        "last_name": user.l_name,
                        "email": user.email,
                        "phone": user.phone,
                        "referral_code": user.referral_code,
                        "referral_count": user.referral_count or 0,
                        "points": user.points,
                        "is_student": user.is_student,
                        "institution": user.institution,
                        "joined_at": (
                            user.joined_at.isoformat() if user.joined_at else ""
                        ),
                    }
                )
        self.stdout.write(self.style.SUCCESS(f"Export complete: {filename}"))
