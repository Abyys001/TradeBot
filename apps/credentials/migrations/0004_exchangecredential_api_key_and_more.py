# Reconciled after merge of origin/main: the sibling migration
# 0004_exchangecredential_api_key_enc_and_more (from main) is canonical — it
# matches models.py (api_key_enc, api_secret_enc default=b"", and the AlterFields).
# This migration is re-parented onto it and reduced to its one unique field
# (api_key), so the two former conflicting leaves become a single linear chain.
# The filename is kept because copytrading/migrations/0001_initial depends on it.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('credentials', '0004_exchangecredential_api_key_enc_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='exchangecredential',
            name='api_key',
            field=models.CharField(blank=True, default='', help_text='Public API key (Tabdeal and other Binance-style exchanges).', max_length=128),
        ),
    ]
