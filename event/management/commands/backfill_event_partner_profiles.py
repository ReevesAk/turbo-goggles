"""
Backfill EventPartnerProfile rows for partners who were already verified
under the legacy `User.business_verified` flag.

Without this, every pre-existing verified partner gets a 403 on their next
event-creation call after the new gate goes live, until they redo NIN+bank
verification through the new flow.

This command follows the same shape as
`banking/management/commands/backfill_bvn_phone_dob.py`:
  - --dry-run lets you inspect who would be affected before touching the DB
  - logs each row so ops can audit what changed
  - is idempotent: re-running skips users who already have a profile

Backfilled rows are marked APPROVED with sentinel values in `nin` and
`bank_account_number` so ops can tell them apart from profiles that went
through the real verification flow. The sentinel in `nin` embeds the user's
UUID to satisfy the unique constraint added in event/0003.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from event.models import EventPartnerProfile

SENTINEL_PREFIX = "BACKFILLED-"
# nin and bank_account_number are EncryptedCharField (fixed-IV AES-CBC), so
# encryption is deterministic and exact-match lookups work — but __startswith
# does NOT, since ciphertext of a substring is never a prefix of the
# ciphertext of the full string. bank_account_number is a constant sentinel
# (unlike nin, which embeds the user id), so it's the one we can filter on.
SENTINEL_BANK_ACCOUNT_NUMBER = "BACKFILLED"


class Command(BaseCommand):
    help = (
        "Create APPROVED EventPartnerProfile rows for partners who were "
        "verified under the legacy User.business_verified flag but have not "
        "gone through the new NIN + bank account verification flow. Without "
        "this, they will get a 403 on the next event-creation attempt."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "List affected users without creating any profile rows. "
                "Run this first."
            ),
        )
        parser.add_argument(
            "--revoke-sentinel",
            action="store_true",
            help=(
                "Reverse mode: delete all profiles whose nin starts with "
                "'BACKFILLED-' (i.e. undo a previous backfill). Use this "
                "when you're ready to force everyone through the new "
                "verification flow."
            ),
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="bulk_create batch size (default: 500).",
        )

    def handle(self, *args, **options):
        if options["revoke_sentinel"]:
            return self._revoke_sentinel(dry_run=options["dry_run"])
        return self._backfill(
            dry_run=options["dry_run"],
            batch_size=options["batch_size"],
        )

    # ===========
    # Backfill
    # -==========

    def _backfill(self, dry_run: bool, batch_size: int) -> None:
        # Exclude anyone who already has a profile — either they went
        # through the new flow, or they were already backfilled.
        existing_user_ids = EventPartnerProfile.objects.values_list(
            "user_id", flat=True
        )

        candidates = (
            User.objects.filter(
                business_verified=True,
                active_role="Partner",
            )
            .exclude(id__in=existing_user_ids)
            .only("id", "email", "first_name", "last_name")
        )

        total = candidates.count()
        self.stdout.write(
            f"Found {total} partner(s) with business_verified=True "
            "and no EventPartnerProfile yet."
        )

        if dry_run:
            if total == 0:
                self.stdout.write("Nothing to do.")
                return
            self.stdout.write("")
            self.stdout.write("Would backfill the following users:")
            for user in candidates.iterator(chunk_size=500):
                self.stdout.write(
                    f"  user_id={user.id}  email={user.email}  "
                    f"name={user.first_name} {user.last_name}"
                )
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "Dry run — no rows created. Re-run without --dry-run " "to apply."
                )
            )
            return

        if total == 0:
            self.stdout.write("Nothing to do.")
            return

        created = 0
        failed = 0

        # Bulk create in chunks so we don't hold a single huge transaction.
        buffer = []
        for user in candidates.iterator(chunk_size=batch_size):
            try:
                buffer.append(
                    EventPartnerProfile(
                        user_id=user.id,
                        nin=f"{SENTINEL_PREFIX}{user.id}",
                        nin_verified=False,
                        nin_name=f"{user.first_name} {user.last_name}".strip(),
                        nin_dob="",
                        bank_code="",
                        bank_name="",
                        bank_account_number=SENTINEL_BANK_ACCOUNT_NUMBER,
                        bank_verified=False,
                        status=EventPartnerProfile.Status.APPROVED,
                        rejection_reason="",
                        reviewed_by_id=None,
                        reviewed_at=None,
                    )
                )
            except Exception as exc:
                self.stderr.write(
                    f"user_id={user.id}: failed to prepare row ({exc}) — skipping"
                )
                failed += 1
                continue

            if len(buffer) >= batch_size:
                created += self._flush(buffer)
                buffer = []

        if buffer:
            created += self._flush(buffer)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {created} profile(s) backfilled, "
                f"{failed} failed, {total} candidate(s) total."
            )
        )

    def _flush(self, buffer: list) -> int:
        """Insert a batch; return the count successfully created."""
        try:
            with transaction.atomic():
                EventPartnerProfile.objects.bulk_create(buffer, batch_size=len(buffer))
            for profile in buffer:
                self.stdout.write(
                    f"  user_id={profile.user_id}: backfilled as APPROVED."
                )
            return len(buffer)
        except Exception as exc:
            # If a batch fails (e.g. race with a submit), fall back to
            # per-row inserts so a single bad row doesn't kill the batch.
            self.stderr.write(
                f"  batch of {len(buffer)} failed ({exc}) — retrying row by row"
            )
            succeeded = 0
            for profile in buffer:
                try:
                    with transaction.atomic():
                        profile.save()
                    self.stdout.write(
                        f"  user_id={profile.user_id}: backfilled as APPROVED."
                    )
                    succeeded += 1
                except Exception as row_exc:
                    self.stderr.write(
                        f"  user_id={profile.user_id}: failed ({row_exc}) — skipping"
                    )
            return succeeded

    # ===========
    # Revoke
    # ===========

    def _revoke_sentinel(self, dry_run: bool) -> None:
        sentinel_rows = EventPartnerProfile.objects.filter(
            bank_account_number=SENTINEL_BANK_ACCOUNT_NUMBER
        )
        total = sentinel_rows.count()
        self.stdout.write(
            f"Found {total} backfilled EventPartnerProfile row(s) "
            f"(bank_account_number == '{SENTINEL_BANK_ACCOUNT_NUMBER}')."
        )

        if total == 0:
            self.stdout.write("Nothing to do.")
            return

        if dry_run:
            for profile in sentinel_rows.iterator(chunk_size=500):
                self.stdout.write(
                    f"  profile_id={profile.id} user_id={profile.user_id}"
                )
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "Dry run — no rows deleted. Re-run without --dry-run " "to apply."
                )
            )
            return

        deleted, _ = sentinel_rows.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {deleted} row(s) deleted. Affected partners will "
                "now be gated by the new verification flow."
            )
        )
