from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0009_storevisitarrival"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE tasks_storevisitarrival
                DROP COLUMN IF EXISTS otp,
                DROP COLUMN IF EXISTS otp_sent_at,
                DROP COLUMN IF EXISTS otp_verified;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
