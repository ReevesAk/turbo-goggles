import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("adverts", "0011_createad_location_alter_createad_latitude_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="StoreVisitQRCode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "token",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                (
                    "qr_image_url",
                    models.CharField(blank=True, max_length=500, null=True),
                ),
                ("scan_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "ad",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="store_visit_qr",
                        to="adverts.createad",
                    ),
                ),
            ],
        ),
    ]
