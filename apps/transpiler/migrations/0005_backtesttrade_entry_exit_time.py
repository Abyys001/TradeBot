from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transpiler", "0004_backtesttrade_missing_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="backtesttrade",
            name="entry_time",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="backtesttrade",
            name="exit_time",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
