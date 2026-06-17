from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gamification", "0005_alter_pointconfig_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="streakchallenge",
            name="is_cancelled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="streakchallenge",
            name="schedule_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("once", "Once"),
                    ("weekly", "Weekly"),
                    ("monthly", "Monthly"),
                    ("every_three_months", "Every Three Months"),
                    ("every_six_months", "Every Six Months"),
                    ("yearly", "Yearly"),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="streakchallenge",
            name="scheduled_start_time",
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="streakchallenge",
            name="participant_cap",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
