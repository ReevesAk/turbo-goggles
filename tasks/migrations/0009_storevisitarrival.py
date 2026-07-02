import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("adverts", "0013_storevisitqrcode_visit_code"),
        ("tasks", "0008_brandverificationresult"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StoreVisitArrival",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted", models.BooleanField(default=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("arrived", "Arrived"),
                            ("no_show", "No Show"),
                            ("completed", "Completed"),
                        ],
                        default="arrived",
                        max_length=20,
                    ),
                ),
                ("otp", models.CharField(blank=True, max_length=6, null=True)),
                ("otp_sent_at", models.DateTimeField(blank=True, null=True)),
                ("otp_verified", models.BooleanField(default=False)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "ad",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="store_arrivals",
                        to="adverts.createad",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="store_arrivals",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "unique_together": {("ad", "user")},
            },
        ),
        migrations.AlterModelOptions(
            name="storevisitarrival",
            options={},
        ),
    ]
