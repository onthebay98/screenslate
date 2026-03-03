import json
import os
import re
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler

import anthropic
import requests

GOODREADS_RSS_URL = "https://www.goodreads.com/review/list_rss/{user_id}?shelf=read"


def parse_user_id(raw_input):
    """Extract numeric Goodreads user ID from a URL or plain ID."""
    raw_input = raw_input.strip()
    # Match URLs like goodreads.com/user/show/12345-username or goodreads.com/user/show/12345
    match = re.search(r'goodreads\.com/user/show/(\d+)', raw_input)
    if match:
        return match.group(1)
    # Plain numeric ID
    if re.match(r'^\d+$', raw_input):
        return raw_input
    return None


def fetch_books(user_id):
    """Fetch books from Goodreads RSS feed and parse XML."""
    url = GOODREADS_RSS_URL.format(user_id=user_id)
    resp = requests.get(url, timeout=15)

    if resp.status_code == 404:
        raise ValueError("User not found")

    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    channel = root.find("channel")

    if channel is None:
        raise ValueError("Invalid RSS feed")

    items = channel.findall("item")
    if not items:
        raise ValueError("No books found on read shelf")

    books = []
    for item in items:
        title = item.findtext("title", "").strip()
        author = item.findtext("author_name", "").strip()
        user_rating = item.findtext("user_rating", "0").strip()
        book_published = item.findtext("book_published", "").strip()

        try:
            rating = int(user_rating)
        except ValueError:
            rating = 0

        books.append({
            "title": title,
            "author": author,
            "rating": rating,
            "year": book_published if book_published else None,
        })

    # Sort: rated highest first, then unrated
    books.sort(key=lambda b: b["rating"], reverse=True)
    return books


def build_prompt(books, user_id):
    """Build the Claude prompt with the user's book list."""
    book_lines = []
    for b in books:
        year_str = f" ({b['year']})" if b.get("year") else ""
        rating_str = f" — rated {b['rating']}/5" if b["rating"] > 0 else " — unrated"
        book_lines.append(f"- {b['title']} by {b['author']}{year_str}{rating_str}")

    book_list = "\n".join(book_lines)

    return f"""You are a cinephile with deep knowledge of film history who also loves literature. A Goodreads user (ID: {user_id}) has shared their read books. Based on their reading taste, recommend films they would love, organized into thematic categories.

Books rated higher should influence recommendations more than lower-rated or unrated ones (5/5 matters most). Unrated books still indicate interest in their subject matter.

Here are their books:

{book_list}

First, identify 4-6 thematic categories that emerge from this user's reading taste. Categories should be insightful and specific — not generic labels like "Drama" or "Action", but something that captures a real pattern (e.g. "Fractured Identity", "The Weight of History", "Quiet Devastation"). Be creative and perceptive.

For each category, recommend 2-4 films. Mark exactly one film per category as "top_pick": true — this is the single highest-confidence recommendation in that category. The top pick should be listed first.

For each film, provide:
- **title**: The film title
- **director**: The director's name
- **year**: The release year
- **description**: 2-3 sentences explaining why this reader would love this film, connecting it to specific books from their list
- **related_books**: A list of 2-4 book titles from their list that connect to this film
- **link**: A Letterboxd search URL in the format "https://letterboxd.com/search/[title+year]/" (URL-encoded)
- **top_pick**: true if this is the #1 recommendation in its category, false otherwise

Respond with ONLY valid JSON in this exact format, no other text:
{{
  "categories": [
    {{
      "name": "Category Name",
      "films": [
        {{
          "title": "Film Title",
          "director": "Director Name",
          "year": 2020,
          "description": "Why they'd love it...",
          "related_books": ["Book 1", "Book 2"],
          "link": "https://letterboxd.com/search/Film+Title+2020/",
          "top_pick": true
        }}
      ]
    }}
  ]
}}"""


def get_recommendations(books, user_id):
    """Call Claude to generate film recommendations."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = build_prompt(books, user_id)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text
    json_match = re.search(r'\{[\s\S]*\}', text)
    if not json_match:
        raise ValueError("No JSON found in Claude response")
    return json.loads(json_match.group())


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))
            raw_input = body.get("user_id", "").strip()

            if not raw_input:
                self._respond(400, {"error": "Goodreads user ID is required"})
                return

            user_id = parse_user_id(raw_input)
            if not user_id:
                self._respond(400, {"error": "Invalid Goodreads user ID or URL. Enter your numeric ID or profile URL."})
                return

            books = fetch_books(user_id)

            result = get_recommendations(books, user_id)
            result["book_count"] = len(books)
            result["user_id"] = user_id
            self._respond(200, result)

        except anthropic.APIError:
            self._respond(502, {"error": "AI service temporarily unavailable. Please try again."})
        except ValueError as e:
            error_msg = str(e)
            if "User not found" in error_msg:
                self._respond(404, {"error": "Goodreads user not found. Check the ID and try again."})
            elif "No books found" in error_msg:
                self._respond(404, {"error": "No books found on the read shelf. Make sure you have books marked as read."})
            elif "Invalid RSS" in error_msg:
                self._respond(400, {"error": "Could not read this profile. It may be private."})
            else:
                self._respond(500, {"error": "Something went wrong. Please try again."})
        except ET.ParseError:
            self._respond(400, {"error": "Could not read this profile. It may be private."})
        except Exception:
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
