import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


BASE_POINTS_SEED = {
    "daily_login": ("Daily Login", 30),
    "service_purchase": ("Service Purchase", 30),
    "financial_task": ("Financial Task", 175),
    "social_engagement": ("Social Engagement", 175),
    "referral": ("Referral", 300),
    "special_campaign": ("Special Campaign", 300),
    "streak_bonus": ("Streak Bonus", 200),
    "watch_video": ("Watch Video", 50),
    "website_visit": ("Website Visit", 30),
    "store_visit": ("Store Visit", 150),
    "survey_completion": ("Survey Completion", 75),
    "app_download": ("App Download", 100),
    "brand_task": ("Brand Task", 50),
}


def seed_point_configs(apps, schema_editor):
    PointConfig = apps.get_model("gamification", "PointConfig")
    for key, (label, value) in BASE_POINTS_SEED.items():
        PointConfig.objects.get_or_create(key=key, defaults={"label": label, "value": value})


def unseed_point_configs(apps, schema_editor):
    PointConfig = apps.get_model("gamification", "PointConfig")
    PointConfig.objects.filter(key__in=BASE_POINTS_SEED.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("gamification", "0003_alter_pointtransaction_source"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PointConfig",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=50, unique=True)),
                ("label", models.CharField(max_length=100)),
                ("value", models.PositiveIntegerField()),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="point_configs_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="StreakChallenge",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                (
                    "streak_type",
                    models.CharField(
                        choices=[
                            ("daily_login", "Daily Login"),
                            ("service_purchase", "Service Purchase"),
                            ("financial_task", "Financial Task"),
                            ("social_engagement", "Social Engagement"),
                            ("referral", "Referral"),
                            ("special_campaign", "Special Campaign"),
                            ("watch_video", "Watch Video"),
                            ("website_visit", "Website Visit"),
                            ("store_visit", "Store Visit"),
                            ("survey_completion", "Survey Completion"),
                            ("app_download", "App Download"),
                            ("brand_task", "Brand Task"),
                        ],
                        max_length=50,
                    ),
                ),
                ("duration_days", models.PositiveIntegerField()),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("reward_points", models.PositiveIntegerField()),
                ("reminder_time", models.TimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("is_paused", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="streak_challenges_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="UserStreak",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("current_count", models.PositiveIntegerField(default=0)),
                ("longest_count", models.PositiveIntegerField(default=0)),
                ("last_activity_date", models.DateField(blank=True, null=True)),
                ("completed", models.BooleanField(default=False)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("reward_issued", models.BooleanField(default=False)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                (
                    "challenge",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_streaks",
                        to="gamification.streakchallenge",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="streaks",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"unique_together": {("user", "challenge")}},
        ),
        migrations.CreateModel(
            name="StreakHistory",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("streak_count_reached", models.PositiveIntegerField()),
                ("broken_at", models.DateField(blank=True, null=True)),
                ("completed", models.BooleanField(default=False)),
                ("reward_issued", models.BooleanField(default=False)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "challenge",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="streak_histories",
                        to="gamification.streakchallenge",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="streak_histories",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-recorded_at"]},
        ),
        migrations.RunPython(seed_point_configs, reverse_code=unseed_point_configs),
    ]
