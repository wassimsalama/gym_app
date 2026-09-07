#!/usr/bin/env python3
"""Seed the `exercises` table from the free-exercise-db dataset.

Usage:
    python scripts/seed_exercises.py                # download (cached) and seed
    python scripts/seed_exercises.py --file x.json  # seed from a local copy
    python scripts/seed_exercises.py --dry-run      # report what would change

Idempotent: exercises are keyed on (lower(name), source='seed'), so re-running
updates muscle_group/equipment in place rather than inserting duplicates.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "api"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.certs import default_ssl_context  # noqa: E402
from app.core.db import engine  # noqa: E402
from app.models import MUSCLE_GROUPS, Exercise  # noqa: E402

DATA_URL = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"
CACHE_PATH = REPO_ROOT / "scripts" / ".cache" / "exercises.json"

# free-exercise-db uses its own muscle vocabulary; collapse it onto the
# muscle_group enum from spec §5. Order matters only for readability.
MUSCLE_MAP: dict[str, str] = {
    "chest": "chest",
    "lats": "back",
    "middle back": "back",
    "lower back": "back",
    "traps": "back",
    "neck": "other",
    "shoulders": "shoulders",
    "biceps": "biceps",
    "forearms": "biceps",
    "triceps": "triceps",
    "quadriceps": "quads",
    "hamstrings": "hamstrings",
    "glutes": "glutes",
    "adductors": "quads",
    "abductors": "glutes",
    "calves": "calves",
    "abdominals": "core",
}


def load_raw(file: Path | None) -> list[dict[str, Any]]:
    if file is not None:
        return json.loads(file.read_text())

    if CACHE_PATH.exists():
        print(f"Using cached dataset at {CACHE_PATH}")
        return json.loads(CACHE_PATH.read_text())

    print(f"Downloading {DATA_URL}")
    with urllib.request.urlopen(  # noqa: S310
        DATA_URL, timeout=60, context=default_ssl_context()
    ) as resp:
        payload = resp.read().decode("utf-8")
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(payload)
    return json.loads(payload)


def to_muscle_group(entry: dict[str, Any]) -> str:
    for muscle in entry.get("primaryMuscles") or []:
        mapped = MUSCLE_MAP.get(muscle.strip().lower())
        if mapped:
            return mapped
    return "other"


def normalise(raw: list[dict[str, Any]]) -> list[dict[str, str | None]]:
    """Collapse the dataset to our columns, de-duplicating on lowercased name."""
    seen: dict[str, dict[str, str | None]] = {}
    for entry in raw:
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        equipment = (entry.get("equipment") or "").strip() or None
        record = {
            "name": name,
            "muscle_group": to_muscle_group(entry),
            "equipment": equipment,
        }
        assert record["muscle_group"] in MUSCLE_GROUPS
        seen.setdefault(name.lower(), record)
    return sorted(seen.values(), key=lambda r: r["name"] or "")


def seed(records: list[dict[str, str | None]], dry_run: bool) -> tuple[int, int]:
    inserted = updated = 0
    with Session(engine) as session:
        existing = {
            (e.name or "").lower(): e
            for e in session.scalars(select(Exercise).where(Exercise.source == "seed"))
        }
        for record in records:
            current = existing.get((record["name"] or "").lower())
            if current is None:
                inserted += 1
                if not dry_run:
                    session.add(Exercise(source="seed", **record))
            elif (
                current.muscle_group != record["muscle_group"]
                or current.equipment != record["equipment"]
            ):
                updated += 1
                if not dry_run:
                    current.muscle_group = record["muscle_group"] or "other"
                    current.equipment = record["equipment"]
        if not dry_run:
            session.commit()
    return inserted, updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, help="seed from a local JSON file")
    parser.add_argument("--dry-run", action="store_true", help="report changes without writing")
    args = parser.parse_args()

    records = normalise(load_raw(args.file))
    inserted, updated = seed(records, args.dry_run)

    prefix = "[dry-run] would insert" if args.dry_run else "inserted"
    print(f"{len(records)} exercises in dataset; {prefix} {inserted}, updated {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
