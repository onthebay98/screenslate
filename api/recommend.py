import json
import os
import re
from http.server import BaseHTTPRequestHandler

import anthropic
from letterboxdpy.user import User


def get_rated_films(username, min_rating=3.5, max_films=150):
    """Fetch a user's rated films from Letterboxd diary, sorted by recency."""
    user = User(username)
    result = user.get_diary()
    # Deduplicate by slug, keeping most recent entry
    seen = {}
    for log_id, entry in result.get("entries", {}).items():
        rating = entry.get("actions", {}).get("rating")
        slug = entry.get("slug", "")
        if rating is not None and rating >= min_rating and slug not in seen:
            date = entry.get("date", {})
            seen[slug] = {
                "name": entry["name"],
                "year": entry.get("release"),
                "rating": rating,
                "slug": slug,
                "date": f"{date.get('year', '')}-{date.get('month', ''):02d}-{date.get('day', ''):02d}",
            }
    # Sort by date descending (most recent first)
    films = sorted(seen.values(), key=lambda f: f["date"], reverse=True)
    return films[:max_films]


def build_prompt(films, username):
    """Build the Claude prompt with the user's film list."""
    film_lines = []
    for f in films:
        year_str = f" ({f['year']})" if f.get("year") else ""
        film_lines.append(f"- {f['name']}{year_str} — rated {f['rating']}/5 — watched {f['date']}")

    film_list = "\n".join(film_lines)

    return f"""You are a well-read literary expert who also loves cinema. A Letterboxd user (@{username}) has shared their highly-rated films, ordered from most recently watched to oldest. Based on their taste, recommend 10 books they would love.

IMPORTANT: Give higher priority to more recently watched films, as they better reflect the user's current interests. The list is ordered by date (most recent first).

Here are their top-rated films (rated 3.5/5 or higher):

{film_list}

For each book recommendation, provide:
1. **title**: The book title
2. **author**: The author's name
3. **description**: 2-3 sentences explaining why this reader would love this book, connecting it to specific films from their list
4. **related_films**: A list of 2-4 film titles from their list that connect to this book
5. **link**: A Google search URL for "buy [title] by [author]" (URL-encoded)

Respond with ONLY valid JSON in this exact format, no other text:
{{
  "recommendations": [
    {{
      "title": "Book Title",
      "author": "Author Name",
      "description": "Why they'd love it...",
      "related_films": ["Film 1", "Film 2"],
      "link": "https://www.google.com/search?q=buy+Book+Title+by+Author+Name"
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
