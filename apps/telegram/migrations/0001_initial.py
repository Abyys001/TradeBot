from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramConfig",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("bot_token_enc", models.BinaryField(blank=True, default=b"", help_text="AES-256-GCM encrypted Bot API token")),
                ("enabled", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="telegram_config", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Telegram Configuration",
                "verbose_name_plural": "Telegram Configurations",
            },
        ),
        migrations.CreateModel(
            name="AlertWhitelist",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chat_id", models.BigIntegerField(help_text="Telegram Chat ID (user or group)")),
                ("label", models.CharField(blank=True, default="", help_text="Friendly label for this chat", max_length=64)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="telegram_whitelist", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Alert Whitelist Entry",
                "verbose_name_plural": "Alert Whitelist Entries",
                "unique_together": {("user", "chat_id")},
            },
        ),
    ]
