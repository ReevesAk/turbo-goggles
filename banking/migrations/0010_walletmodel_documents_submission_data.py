from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("banking", "0009_corporate_wallet_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="walletmodel",
            name="documents",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="walletmodel",
            name="submission_data",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
