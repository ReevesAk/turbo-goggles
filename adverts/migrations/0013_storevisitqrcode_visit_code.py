from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("adverts", "0012_storevisitqrcode"),
    ]

    operations = [
        migrations.AddField(
            model_name="storevisitqrcode",
            name="visit_code",
            field=models.CharField(blank=True, max_length=20, unique=True, default=""),
            preserve_default=False,
        ),
    ]
