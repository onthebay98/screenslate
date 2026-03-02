# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Two projects in one repo:

1. **Film Digest** (`scraper.py`) — scrapes NYC film screenings from Screen Slate, looks up Letterboxd ratings, and emails a curated digest via Resend. Runs twice weekly on GitHub Actions (Sun & Thu at 6pm ET).

2. **Film to Books** (`api/` + `public/`) — a web app where users enter their Letterboxd username and get AI-generated book recommendations based on their film taste. Deployed on Vercel at filmtobooks.vercel.app.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run scraper locally (prints HTML to stdout if email creds aren't set)
python scraper.py

# Run scraper with config overrides
DAYS_AHEAD=3 RATING_THRESHOLD=3.5 python scraper.py

# Run scraper with email delivery
RESEND_API_KEY=... FROM_EMAIL=... RECIPIENT_EMAILS=a@b.com,c@d.com python scraper.py

# Deploy Film to Books to Vercel
npx vercel --prod
```

There are no tests, linter, or build steps.

## Architecture

### Film Digest (`scraper.py`)

Single-file pipeline:

1. **Fetch screenings** — hits Screen Slate date endpoint for each day in range, collects screening node IDs, then batch-fetches details (50 at a time). Films are keyed by `media_title_ids` to deduplicate across days/showtimes.

2. **Enrich with Letterboxd ratings** — for each unique film, searches `letterboxdpy` by title+year, then scrapes only the profile page for the rating (via `MovieProfile.get_rating()`, not the full `Movie()` constructor which hits 6+ pages). Results cached in `ratings_cache.json` (committed to repo by CI).

3. **Build HTML email** — rated films grouped by day with rotating dark background colors, sorted by rating descending within each day. Unrated films in a separate "Also Playing" section. Theater names link to ticket URLs.

4. **Send via Resend API** — falls back to printing HTML if credentials aren't configured.

### Film to Books (`api/recommend.py`)

Vercel serverless function + vanilla frontend:

1. **Fetch films** — combines `User.get_diary()` (rated >= 3.5, has watch dates) with `User.get_films()` (rated >= 4.5 only, no dates) via `letterboxdpy`. Deduplicates by slug, keeps diary dates where available.

2. **Priority sort** — recent 5s (last 90 days) > all 5s > recent 4.5s > all 4.5s > recent 4s > etc. Capped at 150 films.

3. **Generate recommendations** — sends film list to Claude Sonnet, which identifies 4-6 thematic categories from the user's taste and recommends 2-4 books per category with a gold-highlighted top pick each.

4. **Frontend** — vanilla HTML/CSS/JS in `public/`. Letterboxd-inspired dark theme. Book titles link to Goodreads search pages.

## Key Details

### Film Digest
- **Screen Slate API**: date endpoint returns node IDs + times; detail endpoint returns film metadata. Director is detected by a `\n` in the first `<span>` of `media_title_info`. The screenings endpoint does NOT return exhibitions (those are a separate `/api/exhibitions/` endpoint).
- **Ratings cache** (`ratings_cache.json`): keyed by lowercased title. Committed to repo by GitHub Actions after each run. Films with no Letterboxd match are stored as `{}` to avoid re-lookups.
- **`RATING_THRESHOLD` env var** (default 3.8): films below this rating are excluded from the main digest.
- **GitHub Actions workflow** (`.github/workflows/daily-digest.yml`): has `contents: write` permission to auto-commit the updated cache.

### Film to Books
- **Vercel config** (`vercel.json`): Python runtime, 60s max duration for the serverless function.
- **Environment variable**: `ANTHROPIC_API_KEY` (set in Vercel dashboard).
- **letterboxdpy**: `User.get_diary()` returns entries with watch dates; `User.get_films()` returns all rated films without dates. Diary only includes logged/reviewed films, not all rated ones.
- **Deployed at**: filmtobooks.vercel.app (alias of screenslate.vercel.app).
