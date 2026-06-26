from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exchange", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="historydownload",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("running", "Running"),
                    ("done", "Done"),
                    ("partial", "Partial"),
                    ("failed", "Failed"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
    ]
