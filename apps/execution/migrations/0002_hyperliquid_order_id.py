from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("execution", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="orderrecord",
            old_name="okx_order_id",
            new_name="exchange_order_id",
        ),
        migrations.AlterField(
            model_name="orderrecord",
            name="raw",
            field=models.JSONField(blank=True, default=dict, help_text="Raw exchange payload."),
        ),
    ]
