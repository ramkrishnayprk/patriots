# Standalone IMDb ScraperAPI Pipeline

This directory is intentionally independent from the Flask backend, acquisition
jobs, Chroma, embeddings, and frontend. It accepts an explicit list of IMDb
title-page URLs, fetches each page through ScraperAPI, stores the raw HTML, and
extracts normalized JSON-LD metadata.

IMDb's published policy prohibits automated scraping without prior written
permission. The pipeline therefore refuses live execution unless
`IMDB_SCRAPER_AUTHORIZED=true` is set. Only enable it for URLs you are
authorized to access.

## Configuration

The standalone Compose file reads `SCRAPERAPI_KEY` from the repository's root
`.env`. Add these optional settings there:

```dotenv
IMDB_SCRAPER_AUTHORIZED=false
IMDB_SCRAPER_MAX_TITLES=25
IMDB_SCRAPER_TIMEOUT_SECONDS=90
IMDB_SCRAPER_MIN_DELAY_SECONDS=2
IMDB_SCRAPER_MAX_DELAY_SECONDS=5
IMDB_SCRAPER_RENDER=false
IMDB_SCRAPER_PREMIUM=false
IMDB_SCRAPER_COUNTRY_CODE=us
```

Add one authorized title URL per line to `config/seed_urls.txt`. Search, review,
registration, and other IMDb paths are rejected.

## Commands

Validate configuration and seeds without making network requests:

```bash
docker compose -f imdb-scraper/compose.yaml run --rm scraper --validate-only
```

Run only after permission is established and the authorization setting is true:

```bash
docker compose -f imdb-scraper/compose.yaml run --rm scraper
```

Resume a named run:

```bash
docker compose -f imdb-scraper/compose.yaml run --rm scraper \
  --run-id 20260725T120000Z
```

Run the offline parser tests:

```bash
docker compose -f imdb-scraper/compose.yaml --profile test run --rm tests
```

## Output

Each run writes under `imdb-scraper/data/<run-id>/`:

- `raw_html/<imdb-id>.html`: original response body.
- `records.jsonl`: normalized title records.
- `failures.jsonl`: typed fetch or parsing failures.
- `state.json`: atomic resume checkpoint.
- `manifest.json`: run counts, configuration, and output paths.

The entire `imdb-scraper/data/` directory is ignored by Git.
