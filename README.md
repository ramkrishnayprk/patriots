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

## Rebuild chunks without crawling

Re-chunk an existing run exclusively from its `documents.jsonl`:

```bash
curl "http://localhost:5001/api/v1/runs/JOB_ID/chunks/rebuild?strategy=section_aware"
```

Available query parameters:

- `strategy`: `section_aware` or `recursive`
- `chunk_size`: target character count, default `1200`
- `overlap`: character overlap, default `200`
- `min_chunk`: smallest standalone chunk, default `150`
- `embed_prefix`: prepend the program name and first-chunk quick facts, default `true`

The endpoint atomically replaces that run's `chunks.jsonl`, increments the
generation, and writes `chunk_manifest.json`, `chunk_report.json`, and
`chunk_errors.log`. It does not read `raw_html/` or make network requests.

## Build the local vector indexes

Download the embedding model once into the Docker volume:

```bash
docker compose --profile model run --rm embedding-model-download
```

After that completes, embedding runs fully locally:

```bash
curl "http://localhost:5001/api/v1/runs/JOB_ID/vectors/rebuild"
```

This stage streams `chunks.jsonl`, reuses embeddings by `content_hash`, and
atomically synchronizes:

- a persistent cosine-space Chroma collection under `vector_db/`;
- a SQLite FTS5 BM25 index in `bm25.sqlite3`;
- `embedding_manifest.json`, `embedding_report.json`, and
  `embedding_errors.log`.

The manifest records the binding model, dimension, normalization, passage
prefix, and query instruction. Query-time retrieval must reuse that contract.

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
