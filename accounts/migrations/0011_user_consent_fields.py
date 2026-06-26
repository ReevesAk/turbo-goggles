from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_otp_expires_at_remove_auto_now_add"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="consent_given",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="consent_given_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
