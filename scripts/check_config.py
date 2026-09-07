#!/usr/bin/env python3
"""Verify every piece of configuration is wired up and actually works.

Run after changing Supabase projects, before deploying, or whenever something
is behaving oddly. Each check does the real thing rather than reading a setting
back — a variable being present says nothing about whether it is correct.

    python scripts/check_config.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "api"))

from sqlalchemy import text  # noqa: E402

from app.core import storage  # noqa: E402
from app.core.certs import default_ssl_context  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import engine  # noqa: E402

OK, BAD, WARN = "  ok  ", " FAIL ", " warn "
failures: list[str] = []


def report(status: str, label: str, detail: str = "") -> None:
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    if status is BAD:
        failures.append(label)


def check_database() -> None:
    settings = get_settings()
    host = settings.database_url.split("@")[-1].split("/")[0]
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
            version = conn.execute(text("show server_version")).scalar()
            applied = conn.execute(text("select version_num from alembic_version")).scalar()
            exercises = conn.execute(text("select count(*) from exercises")).scalar()
    except Exception as exc:  # noqa: BLE001 — the message is the useful part
        report(BAD, "database", f"{host}: {type(exc).__name__}")
        return

    report(OK, "database", f"{host}, postgres {version}")

    if applied is None:
        report(BAD, "migrations", "none applied — run: alembic upgrade head")
    else:
        report(OK, "migrations", f"at {applied}")

    if not exercises:
        report(WARN, "exercise catalogue", "empty — run scripts/seed_exercises.py")
    else:
        report(OK, "exercise catalogue", f"{exercises} exercises")


def check_auth() -> None:
    """The JWKS must be fetchable, or every request 401s with 'Invalid token'."""
    settings = get_settings()
    if "replace-me" in settings.supabase_url:
        report(BAD, "supabase url", "still the placeholder")
        return

    try:
        request = urllib.request.Request(settings.jwks_url)  # noqa: S310
        with urllib.request.urlopen(  # noqa: S310
            request, timeout=15, context=default_ssl_context()
        ) as response:
            keys = json.loads(response.read())["keys"]
    except (urllib.error.URLError, KeyError, ValueError) as exc:
        report(BAD, "auth keys", f"cannot read JWKS: {exc}")
        return

    if not keys:
        report(BAD, "auth keys", "JWKS is empty")
        return

    algs = ", ".join(sorted({k.get("alg", "?") for k in keys}))
    report(OK, "auth keys", f"{len(keys)} key(s), {algs}")


def check_storage() -> None:
    """Confirm the bucket exists, not merely that a name was configured.

    A named bucket that does not exist fails later as an opaque 502, because
    the API deliberately never echoes the provider's response — that body can
    contain the service key. This is a local diagnostic, so it says what is
    actually wrong.
    """
    settings = get_settings()
    if not storage.is_configured():
        report(WARN, "photo storage", "not configured — photo endpoints will return 503")
        return

    wanted = settings.supabase_storage_bucket
    try:
        buckets = storage.list_buckets()
    except Exception as exc:  # noqa: BLE001 — the type is the useful part
        report(BAD, "photo storage", f"cannot reach storage: {type(exc).__name__}")
        return

    if wanted not in buckets:
        found = ", ".join(sorted(buckets)) if buckets else "none exist on this project"
        report(
            BAD,
            "photo storage",
            f"bucket '{wanted}' not found (buckets: {found}) — "
            "create it under Storage -> New bucket, with Public OFF",
        )
        return

    report(OK, "photo storage", f"bucket '{wanted}' exists")


def check_admins() -> None:
    admins = get_settings().admins
    if not admins:
        report(
            WARN,
            "admin metrics",
            "ADMIN_USER_IDS empty — /admin/metrics is closed to everyone",
        )
        return
    report(OK, "admin metrics", f"{len(admins)} admin id(s)")


def check_cors() -> None:
    settings = get_settings()
    if settings.origins:
        report(OK, "cors", f"restricted to {', '.join(settings.origins)}")
    else:
        report(
            WARN,
            "cors",
            "ALLOWED_ORIGINS unset — development fallback only; a deployed site would be blocked",
        )


def main() -> int:
    print(f"config: {REPO_ROOT / 'api' / '.env'}\n")
    check_database()
    check_auth()
    check_storage()
    check_admins()
    check_cors()

    print()
    if failures:
        print(f"{len(failures)} problem(s): {', '.join(failures)}")
        return 1
    print("Configuration is usable. Warnings above are optional features.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
