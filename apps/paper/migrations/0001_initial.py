import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("strategies", "0006_strategy_credential_optional"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PaperAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("balance", models.DecimalField(decimal_places=8, default=10000, max_digits=24)),
                ("equity", models.DecimalField(decimal_places=8, default=10000, max_digits=24)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "strategy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="paper_accounts",
                        to="strategies.strategy",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="paper_accounts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="PaperTrade",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("side", models.CharField(max_length=8)),
                ("entry_price", models.DecimalField(decimal_places=8, max_digits=24)),
                ("exit_price", models.DecimalField(blank=True, decimal_places=8, max_digits=24, null=True)),
                ("size", models.DecimalField(decimal_places=8, max_digits=24)),
                ("pnl", models.DecimalField(decimal_places=8, default=0, max_digits=24)),
                ("entry_bar", models.IntegerField(default=0)),
                ("exit_bar", models.IntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="trades",
                        to="paper.paperaccount",
                    ),
                ),
            ],
        ),
    ]
