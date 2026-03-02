import json
import os
import re
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler

import anthropic
from letterboxdpy.user import User

RECENT_CUTOFF_DAYS = 90


def get_rated_films(username, max_films=150):
    """Fetch rated films from diary (with dates) + all films (no dates), with priority sorting."""
    user = User(username)
    cutoff = (datetime.now() - timedelta(days=RECENT_CUTOFF_DAYS)).strftime("%Y-%m-%d")

    # 1. Get diary entries (have dates)
    diary = user.get_diary()
    diary_slugs = {}
    for log_id, entry in diary.get("entries", {}).items():
        rating = entry.get("actions", {}).get("rating")
        slug = entry.get("slug", "")
        if rating is not None and rating >= 3.5 and slug not in diary_slugs:
            date = entry.get("date", {})
            date_str = f"{date.get('year', '')}-{date.get('month', 0):02d}-{date.get('day', 0):02d}"
            diary_slugs[slug] = {
                "name": entry["name"],
                "year": entry.get("release"),
                "rating": rating,
                "slug": slug,
                "date": date_str,
                "recent": date_str >= cutoff,
            }

    # 2. Get all films (no dates) — only include 4.5+ that aren't already in diary
    all_films = user.get_films()
    non_diary = {}
    for slug, film in all_films.get("movies", {}).items():
        rating = film.get("rating")
        if rating is not None and rating >= 4.5 and slug not in diary_slugs:
            non_diary[slug] = {
                "name": film["name"],
                "year": film.get("year"),
                "rating": rating,
                "slug": slug,
                "date": None,
                "recent": False,
            }

    # 3. Priority sort: recent 5s > all 5s > recent 4.5s > all 4.5s > recent 4s > all 4s > ...
    combined = list(diary_slugs.values()) + list(non_diary.values())
    combined.sort(key=lambda f: (f["rating"], f["recent"]), reverse=True)
    return combined[:max_films]


def build_prompt(films, username):
    """Build the Claude prompt with the user's film list."""
    film_lines = []
    for f in films:
        year_str = f" ({f['year']})" if f.get("year") else ""
        date_str = f" — watched {f['date']}" if f["date"] else ""
        recent_tag = " [RECENT]" if f["recent"] else ""
        film_lines.append(f"- {f['name']}{year_str} — rated {f['rating']}/5{date_str}{recent_tag}")

    film_list = "\n".join(film_lines)

    return f"""You are a well-read literary expert who also loves cinema. A Letterboxd user (@{username}) has shared their highly-rated films. Based on their taste, recommend 10 books they would love.

The films are ordered by priority. Films rated higher should influence recommendations more than lower-rated ones (5/5 matters most, then 4.5, then 4, etc.). Films marked [RECENT] were watched in the last 3 months and reflect the user's current interests — prioritize these over older films at the same rating level.

Here are their films:

{film_list}

For each book recommendation, provide:
1. **title**: The book title
2. **author**: The author's name
3. **description**: 2-3 sentences explaining why this reader would love this book, connecting it to specific films from their list
4. **related_films**: A list of 2-4 film titles from their list that connect to this book
5. **link**: A Goodreads search URL in the format "https://www.goodreads.com/search?q=[title]+[author]" (URL-encoded)

Respond with ONLY valid JSON in this exact format, no other text:
{{
  "recommendations": [
    {{
      "title": "Book Title",
      "author": "Author Name",
      "description": "Why they'd love it...",
      "related_films": ["Film 1", "Film 2"],
      "link": "https://www.goodreads.com/search?q=Book+Title+Author+Name"
    }}
  ]
}}"""


def get_recommendations(films, username):
    """Call Claude to generate book recommendations."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = build_prompt(films, username)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text
    # Extract JSON from response (handle potential markdown fences)
    json_match = re.search(r'\{[\s\S]*\}', text)
    if not json_match:
        raise ValueError("No JSON found in Claude response")
    return json.loads(json_match.group())


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))
            username = body.get("username", "").strip().lower()

            if not username:
                self._respond(400, {"error": "Username is required"})
                return

            if not re.match(r'^[a-zA-Z0-9_]+$', username):
                self._respond(400, {"error": "Invalid username format"})
                return

            films = get_rated_films(username)
            if not films:
                self._respond(404, {
                    "error": f"No rated films found for @{username}. Make sure the profile is public and has rated films."
                })
                return

            result = get_recommendations(films, username)
            result["film_count"] = len(films)
            result["username"] = username
            self._respond(200, result)

        except anthropic.APIError as e:
            self._respond(502, {"error": "AI service temporarily unavailable. Please try again."})
        except Exception as e:
            error_msg = str(e)
            if "User not found" in error_msg or "404" in error_msg:
                self._respond(404, {"error": f"Letterboxd user '{username}' not found. Check the username and try again."})
            else:
                self._respond(500, {"error": "Something went wrong. Please try again."})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
