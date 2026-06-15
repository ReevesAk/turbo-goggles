import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("user_profile", "0004_membersurvey_linkedin_handle"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="membersurvey",
            name="allow_handle_change",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="HandleChangeRequest",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "platform",
                    models.CharField(
                        choices=[
                            ("facebook", "Facebook"),
                            ("twitter", "X (Twitter)"),
                            ("instagram", "Instagram"),
                            ("tiktok", "TikTok"),
                            ("youtube", "YouTube"),
                            ("linkedin", "LinkedIn"),
                        ],
                        max_length=20,
                    ),
                ),
                ("new_handle", models.CharField(max_length=255)),
                ("proof_url", models.URLField(max_length=500)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        default="pending",
                        max_length=10,
                    ),
                ),
                ("admin_note", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="handle_change_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_handle_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
