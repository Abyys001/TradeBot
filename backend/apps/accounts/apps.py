from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"

    def ready(self) -> None:
        """Retire a deleted account's warm adapter.

        Adapters are kept alive between actions (``apps.exchanges.pool``) and
        are otherwise invalidated by re-reading the account row, so a *deleted*
        account is the one case nothing would ever notice — its client would sit
        in the pool holding a connection signed with credentials the admin has
        removed. A re-key needs no signal; the fingerprint check catches it.
        """
        from django.db.models.signals import post_delete

        from apps.accounts.models import ConnectedAccount
        from apps.exchanges.pool import evict

        def _retire(sender, instance, **kwargs):  # noqa: ANN001, ARG001
            evict(instance.id)

        # ``weak=False`` is load-bearing, not a precaution. Django holds its
        # receivers weakly by default, and ``_retire`` is a local function with
        # no other reference, so the only thing keeping it alive was a reference
        # cycle that had not been collected yet — the receiver was registered
        # and *dead*, silently, the moment a garbage collection ran during
        # startup. Nothing failed loudly: the adapter simply stayed in the pool
        # holding credentials the admin had deleted. ``dispatch_uid`` already
        # makes re-registration a no-op, so a strong reference cannot duplicate
        # it. Pinned by ``tests/test_adapter_pool.py``.
        post_delete.connect(
            _retire,
            sender=ConnectedAccount,
            dispatch_uid="exchanges.pool.retire",
            weak=False,
        )
