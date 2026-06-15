from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0003_brandtasksubmission_deleted_and_more"),
        ("user_profile", "0003_membersurvey_social_fields"),
    ]

    operations = [
        migrations.DeleteModel(
            name="SocialProfile",
        ),
    ]
