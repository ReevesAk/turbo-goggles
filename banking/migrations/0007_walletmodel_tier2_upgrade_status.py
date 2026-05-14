from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("banking", "0006_rename_tranaction_reference_cashback_transaction_reference"),
    ]

    operations = [
        migrations.AddField(
            model_name="walletmodel",
            name="tier2_upgrade_status",
            field=models.CharField(
                blank=True,
                choices=[("PENDING", "Pending"), ("APPROVED", "Approved")],
                max_length=10,
                null=True,
            ),
        ),
    ]
