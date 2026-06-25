from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exchange", "0003_historydownload_data_types"),
    ]

    operations = [
        migrations.CreateModel(
            name="Candle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("network", models.CharField(default="mainnet", max_length=16)),
                ("asset", models.CharField(max_length=32)),
                ("timeframe", models.CharField(max_length=8)),
                ("timestamp", models.BigIntegerField()),
                ("open", models.DecimalField(decimal_places=8, max_digits=24)),
                ("high", models.DecimalField(decimal_places=8, max_digits=24)),
                ("low", models.DecimalField(decimal_places=8, max_digits=24)),
                ("close", models.DecimalField(decimal_places=8, max_digits=24)),
                ("volume", models.DecimalField(decimal_places=8, max_digits=24)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["network", "asset", "timeframe", "timestamp"], name="exchange_ca_network_0a8f2d_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="FundingRate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("network", models.CharField(default="mainnet", max_length=16)),
                ("asset", models.CharField(max_length=32)),
                ("timestamp", models.BigIntegerField()),
                ("funding_rate", models.DecimalField(decimal_places=12, max_digits=24)),
                ("premium", models.DecimalField(decimal_places=12, default=0, max_digits=24)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["network", "asset", "timestamp"], name="exchange_fu_network_6e3b1a_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="OpenInterest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("network", models.CharField(default="mainnet", max_length=16)),
                ("asset", models.CharField(max_length=32)),
                ("timestamp", models.BigIntegerField()),
                ("value", models.DecimalField(decimal_places=8, max_digits=24)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["network", "asset", "timestamp"], name="exchange_op_network_9d4c7e_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="candle",
            constraint=models.UniqueConstraint(fields=("network", "asset", "timeframe", "timestamp"), name="uniq_candle_ntf_ts"),
        ),
        migrations.AddConstraint(
            model_name="fundingrate",
            constraint=models.UniqueConstraint(fields=("network", "asset", "timestamp"), name="uniq_funding_nt_ts"),
        ),
        migrations.AddConstraint(
            model_name="openinterest",
            constraint=models.UniqueConstraint(fields=("network", "asset", "timestamp"), name="uniq_oi_nt_ts"),
        ),
    ]
