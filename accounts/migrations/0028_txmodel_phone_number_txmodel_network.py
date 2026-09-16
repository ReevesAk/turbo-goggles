from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0027_user_active_session_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="txmodel",
            name="phone_number",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="txmodel",
            name="network",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
