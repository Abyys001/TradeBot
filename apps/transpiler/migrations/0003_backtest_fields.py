from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transpiler", "0002_backtest_network"),
    ]

    operations = [
        migrations.AddField(
            model_name="backtest",
            name="initial_balance",
            field=models.FloatField(default=10000.0),
        ),
        migrations.AddField(
            model_name="backtesttrade",
            name="gross_pnl",
            field=models.DecimalField(decimal_places=8, default=0, max_digits=24),
        ),
        migrations.AddField(
            model_name="backtesttrade",
            name="commission",
            field=models.DecimalField(decimal_places=8, default=0, max_digits=24),
        ),
    ]
