import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0001_initial"),
        ("adverts", "0003_add_task_type_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BrandTaskSubmission",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("screenshot_url", models.CharField(blank=True, max_length=500, null=True)),
                ("notes", models.TextField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("Pending", "Pending"),
                            ("Approved", "Approved"),
                            ("Rejected", "Rejected"),
                            ("Flagged", "Flagged"),
                        ],
                        default="Pending",
                        max_length=20,
                    ),
                ),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("rejection_reason", models.TextField(blank=True, null=True)),
                ("reward_issued", models.BooleanField(default=False)),
                (
                    "ad",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="brand_submissions",
                        to="adverts.createad",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_brand_submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="brand_task_submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "unique_together": {("ad", "user")},
            },
        ),
    ]
