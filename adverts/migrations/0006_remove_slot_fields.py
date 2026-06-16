from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("adverts", "0005_alter_createad_brand_objective"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="createad",
            name="slot_cap",
        ),
        migrations.RemoveField(
            model_name="createad",
            name="slots_filled",
        ),
    ]
