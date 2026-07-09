from django.db import migrations


def encrypt_existing_kyc(apps, schema_editor):
    from banking.encryption import encrypt_field, decrypt_field

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT id, bvn, nin, bvn_phone FROM banking_userkyc")
        rows = cursor.fetchall()
        for row_id, bvn, nin, bvn_phone in rows:
            # decrypt_field returns the value unchanged if it is already plaintext
            # (decryption fails gracefully), so calling encrypt_field on plaintext
            # values is safe. Skip if already encrypted (decrypt succeeds and
            # re-encrypting would double-encrypt).
            new_bvn = encrypt_field(bvn) if bvn and bvn == decrypt_field(bvn) else bvn
            new_nin = encrypt_field(nin) if nin and nin == decrypt_field(nin) else nin
            new_phone = (
                encrypt_field(bvn_phone)
                if bvn_phone and bvn_phone == decrypt_field(bvn_phone)
                else bvn_phone
            )
            cursor.execute(
                "UPDATE banking_userkyc SET bvn=%s, nin=%s, bvn_phone=%s WHERE id=%s",
                [new_bvn, new_nin, new_phone, row_id],
            )

    with schema_editor.connection.cursor() as cursor:
        # WalletUpgrade uses multi-table inheritance; its PK column is walletmodel_ptr_id
        cursor.execute("SELECT walletmodel_ptr_id, nin FROM banking_walletupgrade")
        rows = cursor.fetchall()
        for row_id, nin in rows:
            if nin and nin == decrypt_field(nin):
                cursor.execute(
                    "UPDATE banking_walletupgrade SET nin=%s WHERE walletmodel_ptr_id=%s",
                    [encrypt_field(nin), row_id],
                )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("banking", "0011_encrypt_bvn_nin_schema"),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_kyc, reverse_code=noop),
    ]
