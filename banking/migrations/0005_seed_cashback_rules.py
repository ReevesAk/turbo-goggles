from django.db import migrations


def seed_cashback_rules(apps, schema_editor):
    CashbackRule = apps.get_model("banking", "CashbackRule")
    rules = [
        {"service_type": "airtime", "percentage": 1.00},
        {"service_type": "data", "percentage": 1.00},
    ]
    for rule in rules:
        CashbackRule.objects.get_or_create(
            service_type=rule["service_type"],
            defaults={"percentage": rule["percentage"], "is_active": True},
        )


def reverse_seed(apps, schema_editor):
    CashbackRule = apps.get_model("banking", "CashbackRule")
    CashbackRule.objects.filter(service_type__in=["airtime", "data"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("banking", "0004_add_nin_name_to_userkyc"),
    ]

    operations = [
        migrations.RunPython(seed_cashback_rules, reverse_code=reverse_seed),
    ]
