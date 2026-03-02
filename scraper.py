#!/usr/bin/env python3
"""
Screen Slate → Letterboxd NYC Film Digest

Scrapes Screen Slate for upcoming NYC film screenings, cross-references
each film with its Letterboxd rating, and emails a digest sorted by day
then by rating (descending).

Runs twice weekly via GitHub Actions:
  - Sunday night: covers Mon–Sun
  - Thursday night: covers Fri–Thu
"""

import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "onboarding@resend.dev")
RECIPIENT_EMAILS = [
    e.strip() for e in os.environ.get("RECIPIENT_EMAILS", "").split(",") if e.strip()
]
DAYS_AHEAD = int(os.environ.get("DAYS_AHEAD", "7"))
CITY_ID = os.environ.get("CITY_ID", "10969")  # NYC

SCREENSLATE_BASE = "https://www.screenslate.com"
CACHE_FILE = Path(__file__).parent / "ratings_cache.json"

# ---------------------------------------------------------------------------
# Screen Slate helpers
# ---------------------------------------------------------------------------

def strip_html(html_str: str) -> str:
    """Remove HTML tags and decode entities."""
    return unescape(re.sub(r"<[^>]+>", "", html_str)).strip()


def parse_media_title_info(info_html: str) -> dict:
    """
    Parse the media_title_info field which contains <span> elements
    in order: director (optional), year, runtime, format (optional).
    Director spans contain a newline before the name.
    """
    soup = BeautifulSoup(info_html, "html.parser")
    spans = [s.get_text(strip=True) for s in soup.find_all("span")]

    result = {"director": None, "year": None, "runtime": None, "format": None}
    if not spans:
        return result

    idx = 0
    raw_spans = re.findall(r"<span>(.*?)</span>", info_html, re.DOTALL)
    if raw_spans and "\n" in raw_spans[0]:
        result["director"] = spans[idx].strip()
        idx += 1

    if idx < len(spans) and re.match(r"^\d{4}$", spans[idx]):
        result["year"] = int(spans[idx])
        idx += 1

    if idx < len(spans) and re.match(r"^\d+M$", spans[idx], re.IGNORECASE):
        result["runtime"] = spans[idx]
        idx += 1

    if idx < len(spans):
        result["format"] = spans[idx]

    return result


def fetch_screenings(days_ahead: int = DAYS_AHEAD) -> list[dict]:
    """
    Fetch all NYC screenings for the next `days_ahead` days from Screen Slate.
    Returns a list of film dicts with showtimes grouped by date.
    """
    today = datetime.now()
    all_date_items = []
    nid_set = set()

    for offset in range(days_ahead):
        day = today + timedelta(days=offset)
        date_str = day.strftime("%Y%m%d")
        url = (
            f"{SCREENSLATE_BASE}/api/screenings/date"
            f"?_format=json&date={date_str}&field_city_target_id={CITY_ID}"
        )
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            print(f"  Warning: date endpoint returned {resp.status_code} for {date_str}")
            continue

        for item in resp.json():
            nid = item["nid"]
            nid_set.add(nid)
            all_date_items.append({
                "nid": nid,
                "time": item.get("field_time", ""),
                "timestamp": item.get("field_timestamp", ""),
                "date": day.strftime("%a %b %-d"),
                "date_sort": day.strftime("%Y%m%d"),
            })

    if not nid_set:
        print("No screenings found for the given date range.")
        return []

    print(f"Found {len(nid_set)} unique screening nids across {days_ahead} days.")

    # Batch-fetch screening details
    nid_list = list(nid_set)
    details_map = {}
    batch_size = 50

    for i in range(0, len(nid_list), batch_size):
        batch = nid_list[i : i + batch_size]
        nid_str = "+".join(batch)
        url = f"{SCREENSLATE_BASE}/api/screenings/id/{nid_str}?_format=json"
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            print(f"  Warning: detail endpoint returned {resp.status_code}")
            continue
        for item in resp.json():
            details_map[item["nid"]] = item

    # Merge and group by film
    films = {}

    for date_item in all_date_items:
        nid = date_item["nid"]
        detail = details_map.get(nid)
        if not detail:
            continue

        media_id = detail.get("media_title_ids", nid)
        title = strip_html(detail.get("media_title_labels", ""))
        if not title:
            continue

        info = parse_media_title_info(detail.get("media_title_info", ""))
        venue = strip_html(detail.get("venue_title", ""))
        ticket_url = detail.get("field_url", "")

        if media_id not in films:
            films[media_id] = {
                "media_id": media_id,
                "title": title,
                "director": info["director"],
                "year": info["year"],
                "runtime": info["runtime"],
                "format": info["format"],
                "showtimes": [],
            }

        films[media_id]["showtimes"].append({
            "date": date_item["date"],
            "date_sort": date_item["date_sort"],
            "time": date_item["time"],
            "venue": venue,
            "ticket_url": ticket_url,
        })

    return list(films.values())


# ---------------------------------------------------------------------------
# Letterboxd helpers
# ---------------------------------------------------------------------------

def get_rating_fast(slug: str) -> float | None:
    """
    Fetch only the Letterboxd profile page for a film and extract its rating.
    Much faster than Movie() which scrapes 6 pages per film.
    """
    from letterboxdpy.pages.movie_profile import MovieProfile
    try:
        profile = MovieProfile(slug)
        return profile.get_rating()
    except Exception:
        return None


def lookup_letterboxd(title: str, year: int | None) -> dict | None:
    """
    Search Letterboxd for a film by title (and year if available).
    Returns {"slug", "rating", "url"} or None.
    """
    from letterboxdpy.search import Search

    query = f"{title} {year}" if year else title
    try:
        search = Search(query, "films")
        results = search.get_results(max=5)
        if not results.get("available"):
            return None

        best = None
        for r in results["results"]:
            if r.get("type") != "film":
                continue
            r_name = r.get("name", "").lower()
            r_year = r.get("year")

            if year and r_year == year and r_name == title.lower():
                best = r
                break
            if r_name == title.lower():
                best = r
                break
            if best is None:
                best = r

        if not best or not best.get("slug"):
            return None

        slug = best["slug"]
        rating = get_rating_fast(slug)
        url = f"https://letterboxd.com/film/{slug}/"
        return {"slug": slug, "rating": rating, "url": url}

    except Exception as e:
        print(f"  Letterboxd lookup error for '{title}': {e}")
        return None


def load_cache() -> dict:
    """Load the persistent ratings cache from disk."""
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_cache(cache: dict) -> None:
    """Save the ratings cache to disk."""
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, sort_keys=True)


def enrich_with_ratings(films: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Look up Letterboxd ratings for each film.
    Uses a persistent JSON cache so each film is only scraped once.
    Returns (rated_films, unrated_films).
    """
    cache = load_cache()
    rated = []
    unrated = []
    cache_hits = 0

    for film in films:
        title = film["title"]
        key = title.lower()

        if key in cache:
            lb = cache[key]
            cache_hits += 1
        else:
            print(f"  Looking up: {title} ({film.get('year', '?')})")
            lb = lookup_letterboxd(title, film.get("year"))
            # Store result in cache (None becomes empty dict for JSON)
            cache[key] = lb if lb else {}
            time.sleep(0.5)

        if lb and lb.get("rating"):
            film["lb_rating"] = lb["rating"]
            film["lb_url"] = lb["url"]
            film["lb_slug"] = lb["slug"]
            rated.append(film)
        else:
            if key in cache and not cache[key]:
                pass  # already logged on first lookup
            else:
                print(f"    No rating found for {title}")
            unrated.append(film)

    save_cache(cache)
    new_lookups = len(films) - cache_hits
    print(f"  Cache: {cache_hits} hits, {new_lookups} new lookups, {len(cache)} total entries")
    return rated, unrated


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def _build_venue_html(showtimes: list[dict]) -> str:
    """Build venue + time HTML from a list of showtimes."""
    by_venue = defaultdict(list)
    for st in showtimes:
        by_venue[(st["venue"], st["ticket_url"])].append(st["time"])

    parts = []
    for (venue, ticket_url), times in by_venue.items():
        time_str = ", ".join(t for t in times if t)
        if ticket_url:
            parts.append(
                f'<a href="{ticket_url}" style="color:#40BCF4;text-decoration:none;">{venue}</a>'
                + (f" {time_str}" if time_str else "")
            )
        else:
            parts.append(f"{venue}" + (f" {time_str}" if time_str else ""))
    return "<br>".join(parts)


def build_email_html(rated: list[dict], unrated: list[dict], date_range: str) -> str:
    """
    Build an HTML email body grouped by day, sorted by rating within each day.
    Unrated films are listed in an 'Also Playing' section at the end.
    """
    if not rated and not unrated:
        return "<p>No films found for this period.</p>"

    # --- Rated films: grouped by day, sorted by rating ---
    day_films = defaultdict(list)

    for film in rated:
        by_date = defaultdict(list)
        for st in film["showtimes"]:
            by_date[(st["date_sort"], st["date"])].append(st)

        for (date_sort, date_label), sts in by_date.items():
            day_films[date_sort].append({
                "film": film,
                "date_label": date_label,
                "showtimes": sts,
            })

    html_sections = []
    for date_sort in sorted(day_films.keys()):
        entries = day_films[date_sort]
        date_label = entries[0]["date_label"]
        entries.sort(key=lambda e: e["film"].get("lb_rating", 0), reverse=True)

        rows = []
        for entry in entries:
            film = entry["film"]
            rating = f'{film["lb_rating"]:.1f}'
            director_str = film.get("director") or ""
            venue_html = _build_venue_html(entry["showtimes"])

            rows.append(f"""
            <tr>
              <td style="padding:8px 0;border-bottom:1px solid #2a2a2a;">
                <div>
                  <a href="{film.get('lb_url', '#')}" style="color:#fff;text-decoration:none;font-weight:bold;">
                    {film['title']}</a>
                  <span style="color:#00e054;margin-left:4px;">★ {rating}</span>
                </div>
                <div style="color:#999;font-size:13px;">{director_str}</div>
                <div style="font-size:13px;margin-top:4px;">{venue_html}</div>
              </td>
            </tr>""")

        html_sections.append(f"""
        <tr>
          <td style="padding:16px 0 8px 0;">
            <h3 style="margin:0;color:#00e054;font-size:15px;text-transform:uppercase;letter-spacing:1px;">
              {date_label}
            </h3>
          </td>
        </tr>
        {''.join(rows)}""")

    # --- Unrated films: simple list at the bottom ---
    unrated_html = ""
    if unrated:
        unrated_rows = []
        for film in sorted(unrated, key=lambda f: f["title"]):
            director_str = film.get("director") or ""
            # Collect all unique venues
            venues = set()
            for st in film["showtimes"]:
                venues.add(st["venue"])
            venue_str = ", ".join(sorted(venues))

            unrated_rows.append(f"""
            <tr>
              <td style="padding:6px 0;border-bottom:1px solid #2a2a2a;">
                <span style="color:#ccc;font-weight:bold;">{film['title']}</span>
                <span style="color:#999;font-size:13px;">
                  {(' &middot; ' + director_str) if director_str else ''} &middot; {venue_str}
                </span>
              </td>
            </tr>""")

        unrated_html = f"""
        <tr>
          <td style="padding:24px 0 8px 0;">
            <h3 style="margin:0;color:#999;font-size:15px;text-transform:uppercase;letter-spacing:1px;">
              Also Playing (No Letterboxd Rating)
            </h3>
          </td>
        </tr>
        {''.join(unrated_rows)}"""

    total = len(rated) + len(unrated)
    return f"""
    <html>
    <body style="font-family:Helvetica,Arial,sans-serif;max-width:600px;margin:0 auto;background:#1a1a1a;color:#ddd;padding:20px;">
      <h2 style="color:#00e054;margin-bottom:4px;">NYC Film Digest</h2>
      <p style="color:#999;font-size:13px;margin-top:0;">{date_range} &middot; {total} films</p>
      <table style="width:100%;border-collapse:collapse;">
        {''.join(html_sections)}
        {unrated_html}
      </table>
      <p style="color:#666;font-size:11px;margin-top:24px;">
        Data from <a href="https://www.screenslate.com" style="color:#666;">Screen Slate</a>
        &amp; <a href="https://letterboxd.com" style="color:#666;">Letterboxd</a>
      </p>
    </body>
    </html>
    """


def send_email(html_body: str, date_range: str) -> None:
    """Send the digest email via Resend API."""
    if not all([RESEND_API_KEY, RECIPIENT_EMAILS]):
        print("Email credentials not configured. Printing HTML to stdout instead.")
        print(html_body)
        return

    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json={
            "from": FROM_EMAIL,
            "to": RECIPIENT_EMAILS,
            "subject": f"NYC Film Digest — {date_range}",
            "html": html_body,
        },
    )

    if resp.status_code == 200:
        print(f"Email sent to {', '.join(RECIPIENT_EMAILS)}")
    else:
        print(f"Email failed ({resp.status_code}): {resp.text}")
        resp.raise_for_status()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    today = datetime.now()
    end = today + timedelta(days=DAYS_AHEAD - 1)
    date_range = f"{today.strftime('%b %-d')}–{end.strftime('%b %-d')}"

    print(f"Fetching screenings for {date_range} ...")
    films = fetch_screenings()

    print(f"\nFound {len(films)} unique films. Looking up Letterboxd ratings ...")
    rated, unrated = enrich_with_ratings(films)

    print(f"\n{len(rated)} rated, {len(unrated)} unrated.")
    html = build_email_html(rated, unrated, date_range)
    send_email(html, date_range)


if __name__ == "__main__":
    main()
