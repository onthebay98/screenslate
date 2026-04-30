"""Claude API extraction of screening listings."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import anthropic

log = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_INPUT_CHARS = 80_000  # truncate page text to stay within token budget


@dataclass
class Screening:
    title: str
    director: str
    venue: str
    dates: list[str]  # ISO date strings
    format: str | None = None
    url: str | None = None
    notes: str | None = None


def build_prompt(venue_name: str, director_list: list[str], page_text: str) -> str:
    directors_str = ", ".join(director_list)
    return (
        f"You are extracting cinema screening listings. Given the text below from "
        f"{venue_name}, return a JSON array of any upcoming screenings of films "
        f"directed by any of: {directors_str}.\n\n"
        f"For each screening, return:\n"
        f'{{"title": str, "director": str, "venue": str, "dates": [ISO date strings], '
        f'"format": str or null, "url": str or null, "notes": str or null}}\n\n'
        f"If no matching screenings appear, return [].\n"
        f"Do not include screenings already past.\n"
        f"Return ONLY the JSON array, no prose.\n\n"
        f"--- PAGE TEXT ---\n{page_text[:MAX_INPUT_CHARS]}"
    )


def extract_screenings(
    client: anthropic.Anthropic,
    venue_name: str,
    director_list: list[str],
    page_text: str,
    retries: int = 1,
) -> list[Screening]:
    """Send page text to Claude and parse the structured JSON response."""
    prompt = build_prompt(venue_name, director_list, page_text)

    for attempt in range(1 + retries):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3].strip()

            results = json.loads(raw)
            if not isinstance(results, list):
                log.warning("Expected list from Claude, got %s", type(results).__name__)
                return []

            screenings = []
            for item in results:
                try:
                    screenings.append(Screening(
                        title=str(item["title"]),
                        director=str(item["director"]),
                        venue=str(item.get("venue", venue_name)),
                        dates=[str(d) for d in item.get("dates", [])],
                        format=item.get("format"),
                        url=item.get("url"),
                        notes=item.get("notes"),
                    ))
                except (KeyError, TypeError) as e:
                    log.warning("Skipping malformed screening entry: %s — %s", item, e)

            log.info("Extracted %d screening(s) from %s", len(screenings), venue_name)
            return screenings

        except (anthropic.APIError, json.JSONDecodeError) as e:
            if attempt < retries:
                log.warning("Attempt %d failed for %s: %s — retrying", attempt + 1, venue_name, e)
                time.sleep(2)
            else:
                log.error("All attempts failed for %s: %s", venue_name, e)
                return []

    return []
