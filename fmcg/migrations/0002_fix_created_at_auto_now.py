from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fmcg", "0001_initial"),
    ]

    operations = [
        # Product already has updated_at from BaseModel — only fix created_at
        migrations.AlterField(
            model_name="product",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
    ]
