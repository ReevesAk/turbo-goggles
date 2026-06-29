from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gamification", "0007_streakchallenge_datetime_dates"),
    ]

    operations = [
        migrations.AddField(
            model_name="streakchallenge",
            name="duration_minutes",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
