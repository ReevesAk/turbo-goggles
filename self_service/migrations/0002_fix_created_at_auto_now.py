from django.db import migrations, models

MODELS = [
    "restaurantbooking",
    "gymsubcription",
    "cinemabooking",
    "courierservice",
    "consumableservice",
    "landtravels",
    "hotels",
]


class Migration(migrations.Migration):

    dependencies = [
        ("self_service", "0001_initial"),
    ]

    operations = [
        op
        for name in MODELS
        for op in [
            migrations.AlterField(
                model_name=name,
                name="created_at",
                field=models.DateTimeField(auto_now_add=True, null=True),
            ),
            migrations.AddField(
                model_name=name,
                name="updated_at",
                field=models.DateTimeField(auto_now=True),
            ),
        ]
    ]
