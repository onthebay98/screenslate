"""NYC Film Screening Monitor — orchestration."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import anthropic

from .sources import VENUES, fetch_venue
from .extractor import Screening, extract_screenings
from .state import load_state, save_state, filter_new_screenings, add_to_state
from .notifier import build_message, send_discord, send_error

log = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_directors() -> list[str]:
    path = CONFIG_DIR / "directors.txt"
    if not path.exists():
        return ["John Ford"]
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def run(dry_run: bool = False, baseline: bool = False) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    directors = load_directors()
    log.info("Monitoring directors: %s", ", ".join(directors))

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

    if not api_key:
        log.error("ANTHROPIC_API_KEY not set")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    state = load_state()

    all_new: list[Screening] = []
    venues_succeeded = 0
    venues_failed = 0

    for venue in VENUES:
        log.info("Processing %s...", venue.name)
        try:
            pages = fetch_venue(venue)
            if not pages:
                log.warning("No pages fetched for %s", venue.name)
                venues_failed += 1
                continue

            venue_screenings: list[Screening] = []
            for url, page_text in pages:
                screenings = extract_screenings(client, venue.name, directors, page_text)
                venue_screenings.extend(screenings)

            new = filter_new_screenings(venue_screenings, venue.slug, state)
            if new:
                log.info("Found %d new screening(s) at %s", len(new), venue.name)
                all_new.extend(new)
                add_to_state(state, new, venue.slug, venue.name)

            venues_succeeded += 1

        except Exception as e:
            log.error("Error processing %s: %s", venue.name, e)
            venues_failed += 1

    # If every venue failed, send an error ping
    if venues_succeeded == 0 and venues_failed > 0:
        error_msg = f"All {venues_failed} venues failed. Likely a code or network bug."
        log.error(error_msg)
        if webhook_url and not dry_run:
            send_error(webhook_url, error_msg)
        sys.exit(1)

    log.info("Results: %d venue(s) OK, %d failed, %d new screening(s)",
             venues_succeeded, venues_failed, len(all_new))

    # Save state (even if no new screenings, to persist any failed-venue recovery)
    save_state(state)

    # Send notification
    if all_new and not baseline:
        message = build_message(all_new, directors)
        if dry_run:
            print("\n--- DRY RUN: Discord message ---")
            print(message)
            print("--- END ---\n")
        elif webhook_url:
            send_discord(webhook_url, message)
        else:
            log.warning("No DISCORD_WEBHOOK_URL set, printing message:")
            print(message)
    elif baseline:
        log.info("Baseline mode: state updated, no notification sent.")
    else:
        log.info("No new screenings found.")


def main() -> None:
    parser = argparse.ArgumentParser(description="NYC Film Screening Monitor")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print Discord payload instead of posting")
    parser.add_argument("--baseline", action="store_true",
                        help="Populate state without sending notifications")
    args = parser.parse_args()
    run(dry_run=args.dry_run, baseline=args.baseline)


if __name__ == "__main__":
    main()
