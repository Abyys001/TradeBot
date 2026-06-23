"""Migrate credentials from OKX API keys to Hyperliquid agent keys."""
from django.db import migrations, models


def clear_credentials(apps, schema_editor):
    ExchangeCredential = apps.get_model("credentials", "ExchangeCredential")
    ExchangeCredential.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("credentials", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(clear_credentials, migrations.RunPython.noop),
        migrations.RemoveField(model_name="exchangecredential", name="api_key_enc"),
        migrations.RemoveField(model_name="exchangecredential", name="api_secret_enc"),
        migrations.RemoveField(model_name="exchangecredential", name="passphrase_enc"),
        migrations.RemoveField(model_name="exchangecredential", name="is_demo"),
        migrations.AddField(
            model_name="exchangecredential",
            name="agent_private_key_enc",
            field=models.BinaryField(default=b""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="exchangecredential",
            name="agent_address",
            field=models.CharField(blank=True, default="", max_length=42),
        ),
        migrations.AddField(
            model_name="exchangecredential",
            name="wallet_address",
            field=models.CharField(default="0x0", max_length=42),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="exchangecredential",
            name="network",
            field=models.CharField(
                choices=[("mainnet", "Mainnet"), ("testnet", "Testnet")],
                default="testnet",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="exchangecredential",
            name="exchange",
            field=models.CharField(
                choices=[("hyperliquid", "Hyperliquid")],
                default="hyperliquid",
                max_length=16,
            ),
        ),
    ]
