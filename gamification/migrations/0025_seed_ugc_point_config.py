from django.db import migrations

UGC_POINTS_SEED = {
    "make_a_video": ("Make a video", 50),
    "take_a_picture": ("Take a picture", 50),
}


def seed_ugc_point_configs(apps, schema_editor):
    PointConfig = apps.get_model("gamification", "PointConfig")
    for key, (label, value) in UGC_POINTS_SEED.items():
        PointConfig.objects.get_or_create(
            key=key, defaults={"label": label, "value": value}
        )


def unseed_ugc_point_configs(apps, schema_editor):
    PointConfig = apps.get_model("gamification", "PointConfig")
    PointConfig.objects.filter(key__in=UGC_POINTS_SEED.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("gamification", "0024_alter_streakchallenge_mission_category"),
    ]

    operations = [
        migrations.RunPython(
            seed_ugc_point_configs, reverse_code=unseed_ugc_point_configs
        ),
    ]
