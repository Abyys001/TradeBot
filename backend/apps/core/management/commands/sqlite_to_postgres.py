"""Move an existing ``db.sqlite3`` into the configured PostgreSQL database.

This exists once, for the switch. Everything the platform had before the move —
connected accounts and their encrypted credentials, trades and their legs, the
ledger, the downloaded pair catalogue and every archived candle — lives in a
SQLite file that nothing reads any more. Re-creating it by hand is not an option
for the trade history, and `dumpdata | loaddata` falls over on this schema: it
loads the whole table into memory (``StoredCandle`` alone can be millions of
rows) and it cannot resolve the ``ContentType`` rows that ``migrate`` has
already written into the empty target.

So: stream model by model, keep the primary keys, fix the sequences afterwards.

**Credentials survive the trip untouched.** They are Fernet ciphertext in a text
column, copied verbatim; the same ``CREDENTIAL_ENCRYPTION_KEYS`` decrypts them on
the other side. Which is the trap worth naming — a database restored without the
matching ``.env`` is rows nobody can read.
"""

from __future__ import annotations

from pathlib import Path

from django.apps import apps as django_apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import DEFAULT_DB_ALIAS, connections, router, transaction

#: The alias the source file is mounted under for the duration of the command.
SOURCE = "sqlite_legacy"

#: Rows per INSERT, matching the candle backfill's own batch size. Big enough
#: that a million-row table moves quickly, small enough that nothing is ever
#: fully resident.
BATCH = 2000


class Command(BaseCommand):
    help = "Copy every row from a legacy db.sqlite3 into the configured PostgreSQL database."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--source",
            default=str(Path(settings.BASE_DIR) / "db.sqlite3"),
            help="Path to the SQLite file to read (default: backend/db.sqlite3).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would move, per model, and change nothing.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Copy even though the target already holds application rows.",
        )

    def handle(self, *args, **options) -> None:
        source = Path(options["source"])
        if not source.is_file():
            raise CommandError(f"no SQLite database at {source}")

        target = connections[DEFAULT_DB_ALIAS]
        if target.vendor != "postgresql":
            raise CommandError(
                f"the default database is {target.vendor}, not postgresql — "
                "this command only moves data *into* PostgreSQL"
            )

        self._mount(source)
        models = ordered_models()

        counts = {model: self._source_count(model) for model in models}
        populated = {model: n for model, n in counts.items() if n}

        for model in models:
            label = model._meta.label
            self.stdout.write(f"  {label:<45} {counts[model]:>10,}")
        total = sum(counts.values())
        self.stdout.write(f"  {'total':<45} {total:>10,}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("dry run — nothing was written"))
            return

        occupied = self._occupied(models)
        if occupied and not options["force"]:
            raise CommandError(
                "the target database already holds application rows ("
                + ", ".join(f"{m._meta.label}={n}" for m, n in occupied.items())
                + "). Re-run with --force to copy on top of them, or drop and "
                "re-create the database first."
            )

        with transaction.atomic(using=DEFAULT_DB_ALIAS):
            # `migrate` seeds these from the code, so the target already has a
            # full set with primary keys that will not match the source's. Any
            # FK pointing at them (a user's permissions, an admin log entry)
            # would land on the wrong row, so the seeded set is replaced rather
            # than merged. Deferred FKs make the window safe inside this block.
            self._clear_seeded(models)
            written = {model: self._copy(model) for model in populated}

        self._reset_sequences(models)

        moved = sum(written.values())
        self.stdout.write(
            self.style.SUCCESS(f"moved {moved:,} rows across {len(written)} models")
        )
        self.stdout.write(
            self.style.WARNING(
                "Credentials moved as ciphertext: keep the CREDENTIAL_ENCRYPTION_KEYS "
                "from the .env this data was written under, or the connected accounts "
                "restore as rows nobody can decrypt."
            )
        )

    # --- the source database -------------------------------------------------

    def _mount(self, source: Path) -> None:
        """Expose the SQLite file as a second connection for this process only."""
        settings.DATABASES[SOURCE] = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(source),
            "ATOMIC_REQUESTS": False,
            "AUTOCOMMIT": True,
            "CONN_MAX_AGE": 0,
            "CONN_HEALTH_CHECKS": False,
            "OPTIONS": {},
            "TIME_ZONE": None,
            "USER": "",
            "PASSWORD": "",
            "HOST": "",
            "PORT": "",
            "TEST": {},
        }
        # `settings` is a cached_property on the handler; dropping it is what
        # makes the alias above visible without restarting the process.
        connections.__dict__.pop("settings", None)

    def _source_count(self, model) -> int:
        try:
            return model._default_manager.using(SOURCE).count()
        except Exception as exc:  # noqa: BLE001 - a table the old file never had
            self.stderr.write(f"  {model._meta.label}: unreadable in source ({exc})")
            return 0

    # --- the target ----------------------------------------------------------

    def _occupied(self, models) -> dict:
        """Application models in the target that already hold rows.

        The tables `migrate` fills by itself are not evidence of a previous
        import, so they do not count towards "already populated".
        """
        seeded = _seeded_models()
        return {
            model: n
            for model in models
            if model not in seeded
            and (n := model._default_manager.using(DEFAULT_DB_ALIAS).count())
        }

    def _clear_seeded(self, models) -> None:
        for model in models:
            if model in _seeded_models():
                model._default_manager.using(DEFAULT_DB_ALIAS).all().delete()

    def _copy(self, model) -> int:
        written = 0
        batch = []
        # `.iterator()` is the whole reason this is not dumpdata: a million
        # archived candles stream through in chunks rather than being built into
        # one list first.
        for obj in model._default_manager.using(SOURCE).order_by("pk").iterator(chunk_size=BATCH):
            batch.append(obj)
            if len(batch) >= BATCH:
                written += self._insert(model, batch)
                batch = []
        if batch:
            written += self._insert(model, batch)
        self.stdout.write(f"  {model._meta.label:<45} {written:>10,} copied")
        return written

    def _insert(self, model, batch) -> int:
        model._default_manager.using(DEFAULT_DB_ALIAS).bulk_create(
            batch, batch_size=BATCH, ignore_conflicts=True
        )
        return len(batch)

    def _reset_sequences(self, models) -> None:
        """Point every sequence past the highest copied primary key.

        Without this the first row inserted after the move collides with an id
        that came across from SQLite, and the failure surfaces as a duplicate
        key error on an ordinary save days later.
        """
        connection = connections[DEFAULT_DB_ALIAS]
        statements = connection.ops.sequence_reset_sql(no_style(), list(models))
        if not statements:
            return
        with connection.cursor() as cursor:
            for sql in statements:
                cursor.execute(sql)
        self.stdout.write(f"  reset {len(statements)} sequence(s)")


def _seeded_models() -> set:
    """Models `migrate` fills by itself, which the copy therefore replaces."""
    out = set()
    for label in ("contenttypes.ContentType", "auth.Permission"):
        try:
            out.add(django_apps.get_model(label))
        except LookupError:
            continue
    return out


def ordered_models() -> list:
    """Every concrete table, parents before children.

    Django creates its foreign keys ``DEFERRABLE INITIALLY DEFERRED``, so a copy
    inside one transaction would survive any order — but the ordering costs
    nothing, and it keeps the per-model progress readable as the graph rather
    than as whatever order the app registry happened to yield.

    ``include_auto_created`` is what catches the many-to-many through tables
    (a user's groups and permissions); leaving them out silently drops every
    group membership. ``django_migrations`` is absent by construction — the
    recorder's model is never registered — so the target keeps its own migration
    state rather than inheriting the source's.
    """
    models = [
        model
        for model in django_apps.get_models(include_auto_created=True)
        if model._meta.managed
        and not model._meta.proxy
        and router.allow_migrate_model(DEFAULT_DB_ALIAS, model)
    ]
    known = set(models)

    pending = {
        model: {
            field.related_model
            for field in model._meta.get_fields()
            if (field.many_to_one or field.one_to_one)
            and field.related_model in known
            and field.related_model is not model
        }
        for model in models
    }

    ordered: list = []
    while pending:
        ready = [model for model, deps in pending.items() if not deps - set(ordered)]
        if not ready:
            # A cycle between two tables. Deferred constraints make it harmless;
            # emit what is left so nothing is dropped.
            ordered.extend(pending)
            break
        ready.sort(key=lambda m: m._meta.label)
        ordered.extend(ready)
        for model in ready:
            pending.pop(model)
    return ordered
