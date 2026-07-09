import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vas", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="valueaddedservices",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name="valueaddedservices",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
