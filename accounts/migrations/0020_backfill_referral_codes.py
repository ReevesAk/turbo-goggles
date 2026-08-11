import random
import string

from django.db import migrations

CODE_RANDOM_LENGTH = 6
BATCH_SIZE = 500


def _generate_code(prefix_source, existing_codes, model):
    prefix = (prefix_source or "USER").upper().replace(" ", "")[:5]
    while True:
        suffix = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=CODE_RANDOM_LENGTH)
        )
        code = f"{prefix}{suffix}"
        if code in existing_codes:
            continue
        if model.objects.filter(referral_code=code).exists():
            continue
        return code


def backfill_referral_codes(apps, schema_editor):
    User = apps.get_model("accounts", "User")

    issued_codes = set()
    users = list(User.objects.only("id", "first_name").iterator())

    for start in range(0, len(users), BATCH_SIZE):
        batch = users[start : start + BATCH_SIZE]
        for user in batch:
            code = _generate_code(user.first_name, issued_codes, User)
            issued_codes.add(code)
            user.referral_code = code
        User.objects.bulk_update(batch, ["referral_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0019_user_referral_count_and_code_index"),
    ]

    operations = [
        migrations.RunPython(backfill_referral_codes, migrations.RunPython.noop),
    ]
