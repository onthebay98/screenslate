"""Discord webhook notifications."""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)


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
