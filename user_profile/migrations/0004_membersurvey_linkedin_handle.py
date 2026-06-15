from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("user_profile", "0003_membersurvey_social_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="membersurvey",
            name="linkedin_handle",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
