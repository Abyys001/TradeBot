from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transpiler", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="backtest",
            name="network",
            field=models.CharField(default="mainnet", max_length=16),
        ),
    ]
