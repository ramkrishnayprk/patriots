# UC Degree Scraper

A Docker-only monorepo containing:

- a minimal Next.js frontend;
- a Flask REST API;
- an RQ background worker;
- Redis for scrape-job state;
- a ScraperAPI-based crawling, extraction, and chunking pipeline.

## Configure

Add your ScraperAPI key to the root `.env` file:

```dotenv
SCRAPERAPI_KEY=your_real_key
```

The key is injected at runtime and is never copied into a Docker image.

## Run

```bash
docker compose up --build
```

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:5001/api/v1/health`

## Trigger a scrape

```bash
curl -X POST http://localhost:5001/api/v1/scrapes
```

The response contains a background job ID:

```json
{
  "data": {
    "id": "job-id",
    "status": "queued"
  }
}
```

Check progress:

```bash
curl http://localhost:5001/api/v1/scrapes/job-id
```

Each run writes to `backend/data/runs/<job-id>/`:

- `raw_html/`
- `programs.json`
- `documents.jsonl`
- `chunks.jsonl`
- `failed_urls.json`
- `discovered_urls.json`

The crawler is restricted to `degrees.ucumberlands.edu`, removes tracking
parameters, respects `robots.txt`, prioritizes `/programs/` pages, checkpoints
periodically, and never places the ScraperAPI key in logs or output files.

## Test

Tests also run in Docker:

```bash
docker compose --profile test run --rm backend-tests
```

## Stop

```bash
docker compose down
```

To also remove Redis job history:

```bash
docker compose down -v
```
