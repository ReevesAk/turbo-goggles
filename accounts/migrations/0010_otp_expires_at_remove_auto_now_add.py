from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_add_transfer_fee_to_txmodel"),
    ]

    operations = [
        migrations.AlterField(
            model_name="otp",
            name="expires_at",
            field=models.DateTimeField(),
        ),
    ]
