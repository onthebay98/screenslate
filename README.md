# Film ↔ Books

**[filmtobooks.vercel.app](https://filmtobooks.vercel.app)**

AI-powered cross-media recommendations. Get book recommendations from your film taste (Letterboxd) or film recommendations from your reading history (Goodreads), powered by Claude.

## Film → Books

Enter your Letterboxd username, get personalized book recommendations.

1. Fetches your rated films from Letterboxd (diary entries + all rated films via `letterboxdpy`)
2. Prioritizes by rating and recency — recent 5-star films carry the most weight, capped at 150 films
3. Claude identifies 4-6 thematic categories from your taste and recommends 2-4 books per category
4. Each category highlights a gold "Top Pick" — the strongest recommendation

## Books → Films

Enter your Goodreads user ID, get personalized film recommendations.

1. Fetches your read books from Goodreads via RSS feed (up to 100 books)
2. Sorts by rating (highest-rated books influence recommendations most)
3. Claude identifies thematic categories from your reading taste and recommends 2-4 films per category
4. Each category highlights a gold "Top Pick" — the strongest recommendation

**Finding your Goodreads ID:** Go to your Goodreads profile — the number in the URL (`goodreads.com/user/show/12345`) is your ID.

## Architecture

### Film ↔ Books (Vercel serverless + vanilla frontend)

```
User enters Letterboxd/Goodreads username
  → Fetch & deduplicate rated films/books
  → Priority sort (rating × recency)
  → Claude Sonnet generates thematic categories + recommendations
  → Render results in Letterboxd-inspired dark UI
```

- **Backend**: Vercel serverless function (`api/recommend.py`) handles scraping and Claude API calls
- **Frontend**: Vanilla HTML/CSS/JS in `public/` — dark theme inspired by Letterboxd, book titles link to Goodreads search
- **Film prioritization**: diary entries (have watch dates) are merged with all rated films and sorted into tiers: recent 5★ > all 5★ > recent 4.5★ > all 4.5★ > etc.

### Bay's NYC Film Digest (GitHub Actions)

A twice-weekly email digest of NYC film screenings scraped from [Screen Slate](https://www.screenslate.com), enriched with Letterboxd ratings.

1. **Scrape screenings** from Screen Slate's API for the upcoming days, deduplicating films by `media_title_ids`
2. **Enrich with Letterboxd ratings** — searches by title+year, caches results in `ratings_cache.json` to avoid redundant lookups
3. **Build HTML email** — films grouped by day, sorted by rating descending, with rotating dark background colors. Unrated films in a separate "Also Playing" section.
4. **Send via Resend** — runs on GitHub Actions (Sun & Thu at 6 PM ET). The workflow auto-commits the updated ratings cache.

## Setup

### Film ↔ Books (Vercel)

```bash
pip install -r requirements.txt
npx vercel --prod
```

Set `ANTHROPIC_API_KEY` in the Vercel dashboard.

### Film Digest (GitHub Actions)

Runs automatically. To test locally:

```bash
python scraper.py

# With config overrides
DAYS_AHEAD=3 RATING_THRESHOLD=3.5 python scraper.py
```

Set `RESEND_API_KEY`, `FROM_EMAIL`, and `RECIPIENT_EMAILS` for email delivery. Falls back to printing HTML if credentials aren't configured.

## Built with

- [Claude API](https://docs.anthropic.com) — AI recommendations
- [letterboxdpy](https://github.com/nmcassa/letterboxdpy) — Letterboxd scraper
- [Vercel](https://vercel.com) — hosting (Python serverless, 60s max duration)
- [Screen Slate](https://www.screenslate.com) — NYC screening data
- [Resend](https://resend.com) — email delivery
