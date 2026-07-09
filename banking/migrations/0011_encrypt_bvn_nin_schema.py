from django.db import migrations
import banking.models


class Migration(migrations.Migration):

    dependencies = [
        ("banking", "0010_walletmodel_documents_submission_data"),
    ]

    operations = [
        # bvn and nin max_length unchanged (already 100); field class changes to EncryptedCharField
        migrations.AlterField(
            model_name="userkyc",
            name="bvn",
            field=banking.models.EncryptedCharField(
                max_length=100, null=True, unique=True
            ),
        ),
        migrations.AlterField(
            model_name="userkyc",
            name="nin",
            field=banking.models.EncryptedCharField(
                max_length=100, null=True, unique=True
            ),
        ),
        # bvn_phone: max_length grows 15 → 100 to hold base64-encoded ciphertext
        migrations.AlterField(
            model_name="userkyc",
            name="bvn_phone",
            field=banking.models.EncryptedCharField(max_length=100, null=True),
        ),
        # WalletUpgrade.nin: max_length grows 20 → 100
        migrations.AlterField(
            model_name="walletupgrade",
            name="nin",
            field=banking.models.EncryptedCharField(max_length=100, null=True),
        ),
    ]
