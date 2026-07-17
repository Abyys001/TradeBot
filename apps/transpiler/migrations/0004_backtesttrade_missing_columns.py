from django.db import migrations, models


class Migration(migrations.Migration):
    """Add stop_px / limit_px / exit_reason that were in the model but never migrated."""

    dependencies = [
        ("transpiler", "0003_backtest_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="backtesttrade",
            name="stop_px",
            field=models.DecimalField(decimal_places=8, max_digits=24, null=True, blank=True),
        ),
        migrations.AddField(
            model_name="backtesttrade",
            name="limit_px",
            field=models.DecimalField(decimal_places=8, max_digits=24, null=True, blank=True),
        ),
        migrations.AddField(
            model_name="backtesttrade",
            name="exit_reason",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
    ]
