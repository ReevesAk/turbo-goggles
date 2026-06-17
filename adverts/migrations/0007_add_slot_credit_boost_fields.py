from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("adverts", "0006_remove_slot_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="createad",
            name="slot_cap",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="createad",
            name="slots_filled",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="createad",
            name="ads_credit",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="createad",
            name="auto_boost_points",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
