from django.db import migrations


def seed_walk_to_earn(apps, schema_editor):
    PointConfig = apps.get_model("gamification", "PointConfig")
    PointConfig.objects.get_or_create(
        key="walk_to_earn", defaults={"label": "Walk To Earn", "value": 100}
    )


def unseed_walk_to_earn(apps, schema_editor):
    PointConfig = apps.get_model("gamification", "PointConfig")
    PointConfig.objects.filter(key="walk_to_earn").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("gamification", "0011_delete_stepbatchlog"),
    ]

    operations = [
        migrations.RunPython(seed_walk_to_earn, reverse_code=unseed_walk_to_earn),
    ]
