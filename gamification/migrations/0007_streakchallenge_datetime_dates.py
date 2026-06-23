from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gamification", "0006_streakchallenge_scheduling_and_cap"),
    ]

    operations = [
        migrations.AlterField(
            model_name="streakchallenge",
            name="start_date",
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name="streakchallenge",
            name="end_date",
            field=models.DateTimeField(),
        ),
    ]
