from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exchange", "0002_historydownload_partial_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="historydownload",
            name="data_types",
            field=models.JSONField(default=list),
        ),
    ]
