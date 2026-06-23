from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("strategies", "0003_live_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="strategy",
            name="live_config",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Operational config: symbols[], timeframes[], risk{}.",
            ),
        ),
    ]
