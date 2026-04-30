"""State persistence for deduplicating notifications."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from .extractor import Screening

log = logging.getLogger(__name__)

STATE_PATH = Path(__file__).resolve().parent.parent / "state" / "notified.json"


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def make_key(venue_slug: str, title: str, date: str) -> str:
    return f"{venue_slug}|{_slugify(title)}|{date}"


def load_state(path: Path = STATE_PATH) -> dict:
    if not path.exists():
        return {"version": 1, "notified": []}
    return json.loads(path.read_text())


def save_state(state: dict, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n")
    log.info("State saved to %s (%d entries)", path, len(state["notified"]))


def get_notified_keys(state: dict) -> set[str]:
    return {entry["key"] for entry in state["notified"]}


def filter_new_screenings(
    screenings: list[Screening],
    venue_slug: str,
    state: dict,
) -> list[Screening]:
    """Return only screenings not already in the notified state."""
    existing = get_notified_keys(state)
    new = []
    for s in screenings:
        has_new_date = False
        for date in s.dates:
            key = make_key(venue_slug, s.title, date)
            if key not in existing:
                has_new_date = True
        if has_new_date:
            new.append(s)
    return new


def add_to_state(
    state: dict,
    screenings: list[Screening],
    venue_slug: str,
    venue_name: str,
) -> None:
    """Add screenings to the notified state (one entry per venue+title+date)."""
    existing = get_notified_keys(state)
    now = datetime.now(timezone.utc).isoformat()

    for s in screenings:
        for date in s.dates:
            key = make_key(venue_slug, s.title, date)
            if key not in existing:
                state["notified"].append({
                    "key": key,
                    "title": s.title,
                    "venue": venue_name,
                    "date": date,
                    "first_seen": now,
                })
                existing.add(key)
