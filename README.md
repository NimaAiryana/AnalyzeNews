# Crypto News Analysis Engine

A fully headless backend engine that crawls crypto news sites in the background (no browser window ever opens), stores articles in MongoDB with deduplication, and uses an LLM (OpenAI or Anthropic) to produce a concise fundamental analysis of a given coin.

## What it does

1. You register coins (symbols) in a dynamic collection — the "enum" of accepted coins.
2. You call `POST /api/v1/analyze` with a symbol (e.g. `BTC`) and a time window.
3. The engine crawls the configured news sites **in parallel**, purely over HTTP (RSS/HTML), and stores results in MongoDB. Already-seen articles are skipped (dedup by URL hash).
4. All relevant news is fed to the AI in **one unified prompt**.
5. The AI returns a 1–3 paragraph summary, the coin's status, and overall market sentiment — stored in an `analyses` collection.
6. The API responds immediately with a `job_id`; you poll for the result.

## Tech stack

- **FastAPI** + **Uvicorn** — async API
- **httpx** + **BeautifulSoup** + **feedparser** — headless crawling (no browser)
- **Motor** — async MongoDB driver
- **OpenAI** / **Anthropic** — pluggable AI provider (set via `AI_PROVIDER`)

## Sites crawled (hardcoded, per-site strategy)

| Site | Strategy |
|------|----------|
| `cryptopanic.com` | Official API (if `CRYPTOPANIC_API_TOKEN` set) → RSS fallback |
| `crypto.news` | Coin tag RSS feed + global RSS feed (keyword filtered) |
| `cryptonews.com` | RSS feeds → HTML listing fallback |

Add a new site: implement a `BaseCrawler` subclass in `app/crawlers/` and register it in `app/crawlers/registry.py`.

## Setup

```bash
# 1. Create a virtualenv and install deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
#   - set AI_PROVIDER=openai (or anthropic)
#   - set OPENAI_API_KEY (or ANTHROPIC_API_KEY)
#   - ensure MongoDB is running at MONGO_URI

# 3. Run
python run.py
```

Open the interactive API docs at `http://localhost:8000/docs`.

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/symbols` | Register a coin |
| `GET` | `/api/v1/symbols` | List coins |
| `PATCH` | `/api/v1/symbols/{symbol}` | Update a coin |
| `DELETE` | `/api/v1/symbols/{symbol}` | Remove a coin |
| `POST` | `/api/v1/analyze` | Start an analysis job → returns `job_id` |
| `GET` | `/api/v1/jobs/{job_id}` | Poll job status + result |
| `GET` | `/api/v1/news?symbol=BTC` | Inspect stored news |
| `GET` | `/api/v1/analyses/{symbol}/latest` | Latest stored analysis |

### Example

```bash
# Register a coin (BTC & ETH are seeded automatically on first boot)
curl -X POST localhost:8000/api/v1/symbols \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"SOL","name":"Solana","aliases":["solana","sol"]}'

# Start analysis for the last 7 days
curl -X POST localhost:8000/api/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"BTC","days":7}'
# -> {"job_id":"...","symbol":"BTC","status":"pending"}

# Poll the job
curl localhost:8000/api/v1/jobs/<job_id>
```

## MongoDB collections

- `symbols` — registered coins (unique on `symbol`)
- `news` — crawled articles (unique on `url_hash` for dedup; `symbols[]` links to coins)
- `analyses` — AI results with sources snapshot
- `jobs` — async job lifecycle + results
