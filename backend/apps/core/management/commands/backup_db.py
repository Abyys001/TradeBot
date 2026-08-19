"""Dump and restore the PostgreSQL database.

`docs/deploy.md` carried backup as two hand-written `pg_dump` lines with the
credentials spelled out in them. That is fine until the day it is needed, when
whoever runs it is not the person who wrote it and the password is now different.
This reads the connection out of the same settings Django uses, so a backup
cannot be taken against the wrong database or with a stale password, and it can
be put in cron next to `prune_logs`.

**A dump is not a backup on its own.** Connected-account credentials are Fernet
ciphertext; without the matching ``CREDENTIAL_ENCRYPTION_KEYS`` from ``.env``
they restore as rows nobody can decrypt. The command says so every time rather
than trusting the runbook to be read.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from shutil import which

from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections


class Command(BaseCommand):
    help = "Write a pg_dump of the configured database, or restore one with --restore."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--out",
            default="",
            help="File to write (default: backup-<db>-<UTC timestamp>.sql in the cwd).",
        )
        parser.add_argument(
            "--restore",
            metavar="FILE",
            default="",
            help="Restore this dump into the configured database instead of writing one.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the confirmation prompt on --restore.",
        )

    def handle(self, *args, **options) -> None:
        config = connections[DEFAULT_DB_ALIAS].settings_dict
        if connections[DEFAULT_DB_ALIAS].vendor != "postgresql":
            raise CommandError("only a PostgreSQL database can be dumped by this command")

        if options["restore"]:
            self._restore(config, Path(options["restore"]), confirmed=options["yes"])
        else:
            self._dump(config, options["out"])

    # --- dump ----------------------------------------------------------------

    def _dump(self, config: dict, out: str) -> None:
        binary = _tool("pg_dump")
        name = config["NAME"]
        target = Path(out) if out else Path(
            f"backup-{name}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.sql"
        )

        command = [
            binary,
            *_connection_flags(config),
            # --no-owner/--no-acl so the dump restores into a database owned by
            # whatever role the *target* deployment uses, which is rarely the
            # role it was taken under.
            "--no-owner",
            "--no-acl",
            "--file",
            str(target),
            name,
        ]
        self._run(command, config)
        size = target.stat().st_size
        self.stdout.write(self.style.SUCCESS(f"wrote {target} ({size / 1e6:.1f} MB)"))
        self.stdout.write(
            self.style.WARNING(
                "Back up .env separately and keep it with this file: without "
                "CREDENTIAL_ENCRYPTION_KEYS the connected accounts in it cannot be read."
            )
        )

    # --- restore -------------------------------------------------------------

    def _restore(self, config: dict, source: Path, *, confirmed: bool) -> None:
        if not source.is_file():
            raise CommandError(f"no dump at {source}")
        binary = _tool("psql")
        name = config["NAME"]

        if not confirmed:
            answer = input(
                f"Restore {source} into {name} at {config['HOST']}:{config['PORT']}? "
                "Existing rows in the restored tables are replaced. [y/N] "
            )
            if answer.strip().lower() not in {"y", "yes"}:
                raise CommandError("cancelled")

        command = [
            binary,
            *_connection_flags(config),
            # Without this psql reports the failure and keeps going, leaving a
            # half-restored database that looks like it worked.
            "--set",
            "ON_ERROR_STOP=on",
            "--single-transaction",
            "--file",
            str(source),
            name,
        ]
        self._run(command, config)
        self.stdout.write(self.style.SUCCESS(f"restored {source} into {name}"))

    # --- running the tool ----------------------------------------------------

    def _run(self, command: list[str], config: dict) -> None:
        env = os.environ.copy()
        # The password goes in the environment, never on the command line, where
        # it would be readable in `ps` by every user on the box.
        if config.get("PASSWORD"):
            env["PGPASSWORD"] = config["PASSWORD"]
        try:
            subprocess.run(command, env=env, check=True)
        except subprocess.CalledProcessError as exc:
            raise CommandError(
                f"{Path(command[0]).name} failed with exit code {exc.returncode}"
            ) from exc


def _tool(name: str) -> str:
    path = which(name)
    if not path:
        raise CommandError(
            f"{name} is not installed. Inside the stack, run this through the db "
            f"container: docker compose exec db {name} ..."
        )
    return path


def _connection_flags(config: dict) -> list[str]:
    flags = []
    if config.get("HOST"):
        flags += ["--host", str(config["HOST"])]
    if config.get("PORT"):
        flags += ["--port", str(config["PORT"])]
    if config.get("USER"):
        flags += ["--username", str(config["USER"]), "--no-password"]
    return flags
