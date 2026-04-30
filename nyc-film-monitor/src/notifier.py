"""Discord webhook notifications."""

from __future__ import annotations

import logging

import requests

from .extractor import Screening

log = logging.getLogger(__name__)


def build_message(screenings: list[Screening], director_names: list[str]) -> str:
    """Build a Discord message summarizing new screenings."""
    directors_label = ", ".join(director_names)
    lines = [f"**New {directors_label} screenings in NYC**", ""]

    for s in screenings:
        date_str = ", ".join(s.dates) if s.dates else "TBD"
        fmt_str = f", {s.format}" if s.format else ""
        line = f"**{s.title}**\n{s.venue}, {date_str}{fmt_str}"
        if s.url:
            line += f"\n{s.url}"
        if s.notes:
            line += f"\n_{s.notes}_"
        lines.append(line)
        lines.append("")

    msg = "\n".join(lines).strip()
    # Discord message limit is 2000 chars
    if len(msg) > 1900:
        msg = msg[:1900] + "\n...(truncated)"
    return msg


def send_discord(webhook_url: str, message: str) -> None:
    """Post a message to a Discord webhook."""
    r = requests.post(webhook_url, json={"content": message}, timeout=20)
    if not (200 <= r.status_code < 300):
        raise RuntimeError(f"Discord webhook failed: {r.status_code} {r.text[:300]}")
    log.info("Discord notification sent.")


def send_error(webhook_url: str, error_msg: str) -> None:
    """Send an error notification to Discord."""
    msg = f"**Film Monitor Error**\n{error_msg}"
    try:
        send_discord(webhook_url, msg)
    except Exception as e:
        log.error("Failed to send error notification: %s", e)
