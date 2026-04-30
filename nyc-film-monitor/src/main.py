"""NYC Film Screening Monitor — uses Screen Slate API to find director screenings."""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .state import load_state, save_state, filter_new, add_to_state
from .notifier import send_discord, send_error

log = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
SCREENSLATE_BASE = "https://www.screenslate.com"
CITY_ID = "10969"  # NYC
DAYS_AHEAD = 14


def load_directors() -> list[str]:
    path = CONFIG_DIR / "directors.txt"
    if not path.exists():
        return ["John Ford"]
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def strip_html(html_str: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", html_str)).strip()


def parse_director(info_html: str) -> str | None:
    """Extract director from media_title_info. Director span contains a newline."""
    soup = BeautifulSoup(info_html, "html.parser")
    spans = [s.get_text(strip=True) for s in soup.find_all("span")]
    if not spans:
        return None
    raw_spans = re.findall(r"<span>(.*?)</span>", info_html, re.DOTALL)
    if raw_spans and "\n" in raw_spans[0]:
        return spans[0].strip()
    return None


def parse_year(info_html: str) -> int | None:
    """Extract year from media_title_info."""
    soup = BeautifulSoup(info_html, "html.parser")
    spans = [s.get_text(strip=True) for s in soup.find_all("span")]
    raw_spans = re.findall(r"<span>(.*?)</span>", info_html, re.DOTALL)

    idx = 0
    if raw_spans and "\n" in raw_spans[0]:
        idx = 1
    if idx < len(spans) and re.match(r"^\d{4}$", spans[idx]):
        return int(spans[idx])
    return None


def fetch_director_screenings(directors: list[str]) -> list[dict]:
    """
    Fetch all NYC screenings from Screen Slate for the next DAYS_AHEAD days.
    Return only screenings matching one of the target directors.
    """
    director_set = {d.lower() for d in directors}
    today = datetime.now()

    # Step 1: collect nids + date info from date endpoints
    all_date_items = []
    nid_set = set()

    for offset in range(DAYS_AHEAD):
        day = today + timedelta(days=offset)
        date_str = day.strftime("%Y%m%d")
        url = (
            f"{SCREENSLATE_BASE}/api/screenings/date"
            f"?_format=json&date={date_str}&field_city_target_id={CITY_ID}"
        )
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                log.warning("Date endpoint returned %d for %s", resp.status_code, date_str)
                continue
            for item in resp.json():
                nid = item["nid"]
                nid_set.add(nid)
                all_date_items.append({
                    "nid": nid,
                    "time": item.get("field_time", ""),
                    "date": day.strftime("%Y-%m-%d"),
                    "date_label": day.strftime("%a %b %-d"),
                })
        except Exception as e:
            log.warning("Failed to fetch date %s: %s", date_str, e)

    if not nid_set:
        log.info("No screenings found in date range.")
        return []

    log.info("Found %d unique screening nids across %d days.", len(nid_set), DAYS_AHEAD)

    # Step 2: batch-fetch screening details
    nid_list = list(nid_set)
    details_map = {}
    batch_size = 50

    for i in range(0, len(nid_list), batch_size):
        batch = nid_list[i:i + batch_size]
        nid_str = "+".join(batch)
        url = f"{SCREENSLATE_BASE}/api/screenings/id/{nid_str}?_format=json"
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                log.warning("Detail endpoint returned %d", resp.status_code)
                continue
            for item in resp.json():
                details_map[item["nid"]] = item
        except Exception as e:
            log.warning("Failed to fetch details batch: %s", e)

    # Step 3: filter by director
    matches = {}  # keyed by media_title_ids

    for date_item in all_date_items:
        detail = details_map.get(date_item["nid"])
        if not detail:
            continue

        info_html = detail.get("media_title_info", "")
        director = parse_director(info_html)
        if not director or director.lower() not in director_set:
            continue

        media_id = detail.get("media_title_ids", date_item["nid"])
        title = strip_html(detail.get("media_title_labels", ""))
        if not title:
            continue

        venue = strip_html(detail.get("venue_title", ""))
        ticket_url = detail.get("field_url", "")
        year = parse_year(info_html)

        if media_id not in matches:
            matches[media_id] = {
                "title": title,
                "director": director,
                "year": year,
                "venue_dates": [],
            }

        matches[media_id]["venue_dates"].append({
            "venue": venue,
            "date": date_item["date"],
            "date_label": date_item["date_label"],
            "time": date_item["time"],
            "ticket_url": ticket_url,
        })

    log.info("Found %d matching film(s) for directors: %s",
             len(matches), ", ".join(directors))
    return list(matches.values())


def build_found_message(new_screenings: list[dict], directors: list[str]) -> str:
    """Build Discord message for new screenings found."""
    directors_label = ", ".join(directors)
    lines = [f"**New {directors_label} screenings in NYC**", ""]

    for film in new_screenings:
        year_str = f" ({film['year']})" if film.get("year") else ""
        lines.append(f"**{film['title']}**{year_str}")
        lines.append(f"Dir. {film['director']}")

        # Group by venue
        by_venue = defaultdict(list)
        for vd in film["venue_dates"]:
            by_venue[(vd["venue"], vd.get("ticket_url", ""))].append(
                f"{vd['date_label']}" + (f" {vd['time']}" if vd["time"] else "")
            )

        for (venue, ticket_url), dates in by_venue.items():
            date_str = ", ".join(dates)
            if ticket_url:
                lines.append(f"{venue}: {date_str}\n{ticket_url}")
            else:
                lines.append(f"{venue}: {date_str}")
        lines.append("")

    msg = "\n".join(lines).strip()
    if len(msg) > 1900:
        msg = msg[:1900] + "\n...(truncated)"
    return msg


def build_heartbeat_message(directors: list[str]) -> str:
    """Build a short all-clear heartbeat message."""
    directors_label = ", ".join(directors)
    return f"**NYC Film Monitor** -- no new {directors_label} screenings this week."


def run(dry_run: bool = False, baseline: bool = False) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    directors = load_directors()
    log.info("Monitoring directors: %s", ", ".join(directors))

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    state = load_state()

    try:
        all_screenings = fetch_director_screenings(directors)
    except Exception as e:
        error_msg = f"Screen Slate fetch failed: {e}"
        log.error(error_msg)
        if webhook_url and not dry_run:
            send_error(webhook_url, error_msg)
        sys.exit(1)

    new_screenings = filter_new(all_screenings, state)
    if new_screenings:
        log.info("Found %d new screening(s).", len(new_screenings))
        add_to_state(state, new_screenings)

    save_state(state)

    # Build message
    if new_screenings and not baseline:
        message = build_found_message(new_screenings, directors)
    elif baseline:
        log.info("Baseline mode: state updated, no notification sent.")
        return
    else:
        message = build_heartbeat_message(directors)

    # Send
    if dry_run:
        print("\n--- DRY RUN: Discord message ---")
        print(message)
        print("--- END ---\n")
    elif webhook_url:
        send_discord(webhook_url, message)
    else:
        log.warning("No DISCORD_WEBHOOK_URL set, printing message:")
        print(message)


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
