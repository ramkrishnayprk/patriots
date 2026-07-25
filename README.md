# Movie RAG

A Docker-only movie acquisition and hybrid retrieval system. IMDb bulk datasets
provide complete title enumeration and structured facts; TMDb supplies exact
release dates and plot overviews; optional Wikipedia enrichment supplies deeper
prose. The existing local Chroma, BM25, reranking, and guarded OpenAI answer
stages remain in place.

## Data policy

- The default window is `2026-01-01` through the day an acquisition runs.
- Each acquisition enriches at most 2,500 IMDb candidates by default, then
  completes the remaining storage and chunking stages normally.
- IMDb `title.basics` is filtered before the much larger credits/name files are
  joined.
- TMDb release dates enforce the precise date window.
- A movie without a TMDb match remains available as an unverified
  structured-only row, but does not produce semantic chunks without real text.
- Records are deduplicated by IMDb `tconst`.
- Adult titles are excluded by default.
- TMDb enrichment is cached by IMDb ID across runs.

IMDb datasets are for personal/non-commercial use. Do not redistribute the raw
files or deploy them commercially. This product uses the TMDB API but is not
endorsed or certified by TMDB. Wikipedia content is CC BY-SA and its source URL
is retained when enabled.

## Configure

Copy values into the ignored root `.env` file:

```dotenv
TMDB_API_KEY=your_tmdb_key
OPENAI_API_KEY=your_openai_key
```

Important optional settings:

```dotenv
MOVIE_WINDOW_START=2026-01-01
MOVIE_TITLE_TYPES=movie
MOVIE_INCLUDE_ADULT=false
MOVIE_REGION_PREFERENCE=US
MOVIE_MAX_CANDIDATES=2500
ENABLE_WIKIPEDIA=false
TMDB_RATE_LIMIT=37
TMDB_RATE_WINDOW_SECONDS=10
```

## Run

```bash
docker compose up --build
```

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:5001/api/v1/health`

## Local sessions

Sessions are hardcoded JSON documents stored under the ignored
`backend/data/sessions/` directory. Create, list, and delete them with:

```bash
curl -X POST http://localhost:5001/api/v1/sessions
curl http://localhost:5001/api/v1/sessions
curl -X DELETE http://localhost:5001/api/v1/sessions/SESSION_ID
```

Each new session contains a UUID, the title `New Session`, an empty `messages`
array, and creation/update timestamps.

## Acquire the movie dataset

```bash
curl -X POST http://localhost:5001/api/v1/acquisitions
```

The request queues the resumable IMDb/TMDb job and returns an ID. Check it with:

```bash
curl http://localhost:5001/api/v1/acquisitions/JOB_ID
```

Each run writes under `backend/data/runs/JOB_ID/`:

- `movies_2026.csv` and `movies_2026.jsonl`: canonical structured movie rows;
- `documents.jsonl`: narrative movie documents for re-chunking;
- `movie_chunks.jsonl` and `chunks.jsonl`: identical RAG-ready chunk streams;
- `missing_report.json`: no-match, no-date, no-overview, and window anomalies;
- `qa_report.json`: acquisition counts and data-quality totals;
- `acquisition_manifest.json`: source snapshot and configuration provenance.

Daily IMDb snapshots live under `backend/data/sources/imdb/YYYY-MM-DD/`.
Cross-run API responses are cached under `backend/data/enrichment_cache/`.

## Rebuild chunks

```bash
curl "http://localhost:5001/api/v1/runs/JOB_ID/chunks/rebuild?strategy=section_aware"
```

Supported parameters are `strategy`, `chunk_size`, `overlap`, `min_chunk`, and
`embed_prefix`. This stage is local and reads only `documents.jsonl`.

## Build vector and BM25 indexes

Download the embedding and reranking models once:

```bash
docker compose --profile model run --rm embedding-model-download
```

Then build the local Chroma and SQLite FTS5 indexes:

```bash
curl "http://localhost:5001/api/v1/runs/JOB_ID/vectors/rebuild"
```

The embedding stage retains IMDb ID, title, year, genres, rating, section, and
source URL as chunk metadata.

## Search

```bash
curl -X POST "http://localhost:5001/api/v1/runs/JOB_ID/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"a science fiction plot about changing the future"}'
```

Search combines local dense retrieval, BM25, Reciprocal Rank Fusion, and a local
cross-encoder reranker.

## Hybrid answers

Use one endpoint for both structured catalog questions and semantic plot
questions:

```bash
curl -X POST "http://localhost:5001/api/v1/runs/JOB_ID/answer" \
  -H "Content-Type: application/json" \
  -d '{"query":"How many 2026 science fiction movies are rated above 7?"}'
```

Enumeration, count, and filtering questions use `movies_2026.jsonl` and do not
touch Chroma or OpenAI. Plot/story questions use the existing retrieval and
guarded cited-generation flow.

Automatic routing is the default. Override it when needed:

```json
{"query": "List all horror movies", "mode": "structured"}
```

```json
{"query": "Explain the ending of The Future Film", "mode": "semantic"}
```

The structured query service depends on a repository protocol. JSONL is the
current adapter; a later SQL or API implementation can replace it without
changing routing or response logic.

## Test

```bash
docker compose --profile test run --rm --build backend-tests
docker compose --profile test run --rm backend-tests ruff check app tests
```

## Stop

```bash
docker compose down
```
