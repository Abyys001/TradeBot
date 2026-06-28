from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("pro", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(name="TradeJournal"),
        migrations.DeleteModel(name="MarketplacePackage"),
    ]
