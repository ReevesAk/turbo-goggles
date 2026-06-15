from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("adverts", "0003_add_task_type_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="createad",
            name="task_name",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="createad",
            name="task_description",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="createad",
            name="location_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("nationwide", "Nationwide"),
                    ("states", "States"),
                    ("cities", "Cities"),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="createad",
            name="countries",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="createad",
            name="auto_boost",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="createad",
            name="slot_cap",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="createad",
            name="brand_objective",
            field=models.CharField(
                blank=True,
                choices=[
                    ("Brand Awareness", "Brand Awareness"),
                    ("Generate Leads", "Generate Leads"),
                    ("Drive Sales", "Drive Sales"),
                    ("Promote Awareness(Engagement)", "Promote Awareness(Engagement)"),
                ],
                max_length=255,
                null=True,
            ),
        ),
    ]
