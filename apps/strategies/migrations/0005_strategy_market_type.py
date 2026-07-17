from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("strategies", "0004_strategy_live_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="strategy",
            name="market_type",
            field=models.CharField(
                choices=[("perp", "Perpetual"), ("spot", "Spot")],
                default="perp",
                max_length=8,
            ),
        ),
        migrations.AlterField(
            model_name="strategy",
            name="symbol",
            field=models.CharField(help_text="HL coin e.g. BTC, ETH", max_length=32),
        ),
    ]
