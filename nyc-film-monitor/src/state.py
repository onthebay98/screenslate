"""State persistence for deduplicating notifications."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

STATE_PATH = Path(__file__).resolve().parent.parent / "state" / "notified.json"


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def make_key(venue: str, title: str, date: str) -> str:
    return f"{_slugify(venue)}|{_slugify(title)}|{date}"


def load_state(path: Path = STATE_PATH) -> dict:
    if not path.exists():
        return {"version": 1, "notified": []}
    return json.loads(path.read_text())


def save_state(state: dict, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n")
    log.info("State saved to %s (%d entries)", path, len(state["notified"]))


def _get_notified_keys(state: dict) -> set[str]:
    return {entry["key"] for entry in state["notified"]}


def filter_new(screenings: list[dict], state: dict) -> list[dict]:
    """Return only screenings with at least one new (venue, title, date) tuple."""
    existing = _get_notified_keys(state)
    new = []
    for film in screenings:
        has_new = any(
            make_key(vd["venue"], film["title"], vd["date"]) not in existing
            for vd in film["venue_dates"]
        )
        if has_new:
            new.append(film)
    return new


def add_to_state(state: dict, screenings: list[dict]) -> None:
    """Add screenings to the notified state."""
    existing = _get_notified_keys(state)
    now = datetime.now(timezone.utc).isoformat()

    for film in screenings:
        for vd in film["venue_dates"]:
            key = make_key(vd["venue"], film["title"], vd["date"])
            if key not in existing:
                state["notified"].append({
                    "key": key,
                    "title": film["title"],
                    "venue": vd["venue"],
                    "date": vd["date"],
                    "first_seen": now,
                })
                existing.add(key)
