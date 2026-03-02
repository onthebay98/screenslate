# Film to Books

**[filmtobooks.vercel.app](https://filmtobooks.vercel.app)**

Enter your Letterboxd username, get personalized book recommendations powered by AI.

## How it works

1. Fetches your rated films from Letterboxd (diary entries + all rated films)
2. Prioritizes by rating and recency (recently watched 5-star films matter most)
3. Claude identifies thematic categories from your taste and recommends 2-4 books per category
4. Each category highlights a gold "Top Pick" — the strongest recommendation

## Also in this repo

**Bay's NYC Film Digest** — a twice-weekly email digest of NYC film screenings scraped from [Screen Slate](https://www.screenslate.com), enriched with Letterboxd ratings. Runs on GitHub Actions.

## Setup

### Film to Books (Vercel)

```bash
pip install -r requirements.txt
npx vercel --prod
```

Set `ANTHROPIC_API_KEY` in the Vercel dashboard.

### Film Digest (GitHub Actions)

Runs automatically. To test locally:

```bash
python scraper.py
```

Set `RESEND_API_KEY`, `FROM_EMAIL`, and `RECIPIENT_EMAILS` for email delivery.

## Built with

- [letterboxdpy](https://github.com/nmcassa/letterboxdpy) — Letterboxd scraper
- [Claude API](https://docs.anthropic.com) — AI book recommendations
- [Vercel](https://vercel.com) — hosting
- [Screen Slate](https://www.screenslate.com) — NYC screening data
- [Resend](https://resend.com) — email delivery

## Author

**Bay Hodge** — [GitHub](https://github.com/onthebay98) / [LinkedIn](https://www.linkedin.com/in/bayhodge/)
