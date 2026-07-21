from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("strategies", "0007_strategy_is_master_strategy_published"),
    ]

    operations = [
        migrations.AddField(
            model_name="strategystate",
            name="sl_confirmed",
            field=models.BooleanField(default=False),
        ),
    ]
