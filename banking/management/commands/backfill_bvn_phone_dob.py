import time

from django.core.management.base import BaseCommand
from django.db.models import Q

from banking.controllers import KYC
from banking.helpers import cloudinary_to_base64
from banking.models import UserKYC
from banking.utils import normalize_ng_phone, parse_dojah_dob


class Command(BaseCommand):
    help = (
        "Backfill UserKYC.bvn_phone/bvn_dob for users who verified BVN before "
        "bvn_phone/bvn_dob existed, by re-running Dojah BVN verification. "
        "Calls Dojah once per affected user (billed) - use --dry-run first."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List affected users without calling Dojah or writing anything.",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=1.0,
            help="Seconds to sleep between Dojah calls (default: 1.0).",
        )

    def handle(self, *args, **options):
        affected = (
            UserKYC.objects.exclude(bvn__isnull=True)
            .exclude(bvn="")
            .filter(
                Q(bvn_phone__isnull=True)
                | Q(bvn_phone="")
                | Q(bvn_dob__isnull=True)
                | Q(bvn_dob="")
            )
            .select_related("user")
        )

        total = affected.count()
        self.stdout.write(
            f"Found {total} BVN-verified users missing bvn_phone/bvn_dob."
        )

        if options["dry_run"]:
            for kyc in affected:
                self.stdout.write(f"  user_id={kyc.user_id}")
            return

        sleep_seconds = options["sleep"]
        succeeded = 0
        failed = 0

        for kyc in affected:
            user = kyc.user

            try:
                selfie_image = cloudinary_to_base64(url=user.profile_img_url)
            except Exception as e:
                self.stderr.write(
                    f"user_id={user.id}: could not load profile image ({e}) - skipping"
                )
                failed += 1
                continue

            response = KYC.verify_bvn(img_file=selfie_image, bvn=kyc.bvn)

            if response is None or response.status_code != 200:
                status_code = getattr(response, "status_code", None)
                self.stderr.write(
                    f"user_id={user.id}: Dojah call failed (status={status_code}) - skipping"
                )
                failed += 1
                time.sleep(sleep_seconds)
                continue

            entity = response.json().get("entity", {})
            entity.pop("image", None)

            img_resp = entity.get("selfie_verification") or {}
            confidence = img_resp.get("confidence_value")

            if (
                img_resp.get("match") is not True
                or not isinstance(confidence, (int, float))
                or confidence < 90
            ):
                self.stderr.write(
                    f"user_id={user.id}: selfie no longer matches "
                    f"(match={img_resp.get('match')}, confidence={confidence!r}) - "
                    "skipping, needs manual re-verification"
                )
                failed += 1
                time.sleep(sleep_seconds)
                continue

            normalized_phone = normalize_ng_phone(entity.get("phone_number1"))
            parsed_dob = parse_dojah_dob(entity.get("date_of_birth"))

            if not normalized_phone or not parsed_dob:
                self.stderr.write(
                    f"user_id={user.id}: Dojah returned unusable phone/DOB "
                    f"(phone={entity.get('phone_number1')!r}, "
                    f"dob={entity.get('date_of_birth')!r}) - skipping"
                )
                failed += 1
                time.sleep(sleep_seconds)
                continue

            kyc.bvn_phone = normalized_phone
            kyc.bvn_dob = parsed_dob.isoformat()
            kyc.save(update_fields=["bvn_phone", "bvn_dob"])

            self.stdout.write(f"user_id={user.id}: backfilled.")
            succeeded += 1
            time.sleep(sleep_seconds)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {succeeded} backfilled, {failed} skipped/failed out of {total}."
            )
        )
