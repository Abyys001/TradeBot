import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("credentials", "0001_initial"),
        ("strategies", "0005_strategy_market_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="strategy",
            name="credential",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="strategies",
                to="credentials.exchangecredential",
            ),
        ),
    ]
