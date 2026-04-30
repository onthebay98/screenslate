"""Venue list and page fetching for NYC repertory cinemas."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

USER_AGENT = "nyc-film-monitor/1.0 (screening-alerts)"


@dataclass
class Venue:
    name: str
    slug: str
    urls: list[str]


# fmt: off
VENUES: list[Venue] = [
    # Venue-specific calendars
    Venue("Film Forum", "film_forum", [
        "https://filmforum.org/now_playing",
        "https://filmforum.org/coming_soon",
    ]),
    Venue("Metrograph", "metrograph", [
        "https://metrograph.com/calendar/",
    ]),
    Venue("IFC Center", "ifc_center", [
        "https://www.ifccenter.com/",
    ]),
    Venue("Film at Lincoln Center", "film_lincoln_center", [
        "https://www.filmlinc.org/films/",
    ]),
    Venue("Museum of the Moving Image", "momi", [
        "https://movingimage.us/programs/",
    ]),
    Venue("Anthology Film Archives", "anthology", [
        "https://anthologyfilmarchives.org/film_screenings/calendar",
    ]),
    Venue("Paris Theater", "paris_theater", [
        "https://www.paristheaternyc.com/",
    ]),
    Venue("Roxy Cinema", "roxy_cinema", [
        "https://www.roxycinemanewyork.com/",
    ]),
    Venue("Quad Cinema", "quad_cinema", [
        "https://quadcinema.com/calendar/",
    ]),
]
# fmt: on


def fetch_page_text(url: str, timeout: int = 30) -> str:
    """Fetch a URL and return its text content with nav/footer stripped."""
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Strip nav, footer, script, style to save tokens
    for tag in soup.find_all(["nav", "footer", "script", "style", "noscript", "header"]):
        tag.decompose()

    return soup.get_text(separator="\n", strip=True)


def fetch_venue(venue: Venue, timeout: int = 30) -> list[tuple[str, str]]:
    """Fetch all URLs for a venue. Returns list of (url, page_text) tuples."""
    results = []
    for url in venue.urls:
        try:
            text = fetch_page_text(url, timeout=timeout)
            results.append((url, text))
            log.info("Fetched %s (%d chars)", url, len(text))
        except Exception as e:
            log.warning("Failed to fetch %s: %s", url, e)
    return results
