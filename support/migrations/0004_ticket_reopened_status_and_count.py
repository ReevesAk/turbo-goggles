from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("support", "0003_alter_ticket_channel"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="reopened_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="ticket",
            name="status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("New", "New"),
                    ("In-Progress", "In-Progress"),
                    ("Awaiting Customer", "Awaiting Customer"),
                    ("Escalated", "Escalated"),
                    ("Resolved", "Resolved"),
                    ("Closed", "Closed"),
                    ("Reopened", "Reopened"),
                ],
                max_length=150,
                null=True,
            ),
        ),
    ]
