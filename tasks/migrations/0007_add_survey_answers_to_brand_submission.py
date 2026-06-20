from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0006_add_target_content_hint_and_target_matched"),
    ]

    operations = [
        migrations.AddField(
            model_name="brandtasksubmission",
            name="survey_answers",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
