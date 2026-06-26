from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SignumConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("bot_id_enc", models.BinaryField(blank=True, default=b"")),
                ("webhook_url_enc", models.BinaryField(blank=True, default=b"")),
                ("order_size_default", models.CharField(default="80%", max_length=32)),
                ("enabled", models.BooleanField(default=False)),
                ("use_settings_bot_id", models.BooleanField(default=True, help_text="When true, override Pine input bot_id with stored secret.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="signum_config", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
