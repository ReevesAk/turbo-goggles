from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("adverts", "0002_add_brand_socials"),
    ]

    operations = [
        migrations.AddField(
            model_name="createad",
            name="task_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("watch_video", "Watch Video"),
                    ("social_engage", "Social Engage"),
                    ("website_visit", "Website Visit"),
                    ("store_visit", "Store Visit"),
                    ("survey", "Survey"),
                    ("app_download", "App Download"),
                ],
                max_length=30,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="createad",
            name="task_details",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="createad",
            name="reward_points",
            field=models.PositiveIntegerField(blank=True, default=0, null=True),
        ),
        migrations.AddField(
            model_name="createad",
            name="slot_cap",
            field=models.PositiveIntegerField(blank=True, default=0, null=True),
        ),
        migrations.AddField(
            model_name="createad",
            name="slots_filled",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
