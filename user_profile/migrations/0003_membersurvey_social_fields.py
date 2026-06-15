from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("user_profile", "0002_add_device_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="membersurvey",
            name="tiktok_handle",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="membersurvey",
            name="tiktok_followers",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="membersurvey",
            name="youtube_handle",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="membersurvey",
            name="youtube_followers",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="membersurvey",
            name="user",
            field=models.OneToOneField(
                on_delete=models.deletion.CASCADE,
                related_name="social_profile",
                to="accounts.user",
            ),
        ),
    ]
