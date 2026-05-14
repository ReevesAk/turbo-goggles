import csv
from django.core.management.base import BaseCommand
from waitlist.models import WaitlistModel, Referral


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
            "joined_with_referral_code",
            "referrer_name",
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
                # Find the referral where this user is the referred
                ref = (
                    Referral.objects.filter(referred=user)
                    .select_related("referrer")
                    .first()
                )
                referrer_name = None
                joined_with_referral_code = None
                if ref and ref.referrer:
                    referrer_name = f"{ref.referrer.f_name or ''} {ref.referrer.l_name or ''}".strip()
                    joined_with_referral_code = ref.referrer.referral_code
                writer.writerow(
                    {
                        "id": user.id,
                        "first_name": user.f_name,
                        "last_name": user.l_name,
                        "email": user.email,
                        "phone": user.phone,
                        "referral_code": user.referral_code,
                        "joined_with_referral_code": joined_with_referral_code,
                        "referrer_name": referrer_name,
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
