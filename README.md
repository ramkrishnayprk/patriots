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

The optional `model` field selects the OpenAI generation model. It must be
listed in `OPENAI_ALLOWED_MODELS`; requests without it use `OPENAI_MODEL`.
The UI model selector is populated from the same allowlist.

```json
{
  "query": "What is Project Hail Mary about?",
  "model": "gpt-5.6-terra"
}
```

The endpoint accepts up to 12 prior `history` messages. The chat server forwards
the latest eight stored messages so obvious references can be resolved without
an LLM call:

```json
{
  "query": "Explain more about the movie",
  "history": [
    {
      "role": "assistant",
      "content": "Laggam Time is about...",
      "sources": [
        {
          "title": "Laggam Time",
          "url": "https://www.imdb.com/title/tt34464200/"
        }
      ]
    }
  ]
}
```

When the latest assistant response has exactly one movie source, references
such as `it`, `the movie`, `explain more`, and `its director` are rewritten to
that canonical title before routing. Multi-movie responses are left unresolved
rather than guessed.

Person searches, rankings, counts, and genre/date filters use
`movies_2026.jsonl` and do not touch Chroma or OpenAI. Examples include
`Paul Walker movies`, `top rated movies`, `how many action movies?`, and
`movies released in June`. Plot/story questions use the existing retrieval and
guarded cited-generation flow.

Direct entity requests such as `Show me details of Laggam Time` first use a
fuzzy title index over `title`, `original_title`, `akas`, and the curated
`backend/config/title_aliases.json` map. A confident title match returns the
structured movie record directly. A weak semantic request with a recognizable
title is retried once with its canonical title.

Only if retrieval remains weak does the pipeline call OpenAI for three query
variations and one HyDE passage. It searches every variation, uses the HyDE
passage for unfiltered dense/hybrid retrieval, and fuses the grounded result
lists with reciprocal-rank fusion. The hypothetical passage is never sent to
the final answer as evidence. Strong initial retrieval and successful fuzzy
title retries do not incur this additional model call.

Tune the ladder in `.env`:

```dotenv
TITLE_LOOKUP_MIN_SCORE=86
TITLE_LOOKUP_AMBIGUITY_MARGIN=3
TITLE_ALIASES_PATH=/app/config/title_aliases.json
QUERY_EXPANSION_ENABLED=true
QUERY_EXPANSION_MODEL=gpt-5.6-terra
QUERY_EXPANSION_VARIATIONS=3
QUERY_EXPANSION_HYDE_ENABLED=true
QUERY_EXPANSION_MAX_OUTPUT_TOKENS=500
QUERY_EXPANSION_RRF_K=60
```

Future acquisition runs preserve IMDb alternate titles in `akas`. New chunks
also include title, original title, and alternate-title text so both dense and
BM25 retrieval have access to entity names.

IMDb rating rankings require at least 1,000 votes by default so a movie with
one high rating does not top the results. Tune ranking behavior in `.env`:

```dotenv
STRUCTURED_MIN_RATING_VOTES=1000
STRUCTURED_DEFAULT_RANK_LIMIT=10
STRUCTURED_MAX_LIST_ITEMS=50
```

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

Every valid answer request writes an append-only entry to
`backend/data/query_logs/queries.jsonl`, including the decision, route,
retrieval scores, title match, and escalation details. Review recent entries:

```bash
curl "http://localhost:5001/api/v1/query-logs?limit=100"
curl "http://localhost:5001/api/v1/query-logs?decision=refused"
curl "http://localhost:5001/api/v1/query-logs?triage_bucket=recall_miss_recovered"
```

Refusals are marked `needs_review` so they can be classified as
`out_of_scope`, `recall_miss`, or `data_gap` during review. Confirmed aliases
belong in `backend/config/title_aliases.json`; regression cases belong in
`backend/config/golden_queries.json`.

## Chat UI and session files

Open `http://localhost:3000/chat` after starting Docker. The Next.js server
connects to Flask over the internal Docker network and automatically selects
the newest run containing `movies_2026.jsonl`. Set `BACKEND_RUN_ID` in `.env`
to pin chat to a specific run.

Clicking **New chat** opens an unsaved welcome screen. The first session file
is created only after the answer pipeline returns successfully. Each session
is stored as `backend/data/sessions/<uuid>.json` and subsequent exchanges are
appended to the same file. The UI hides internal `[n]` grounding markers and
shows citations as clickable source links beneath each answer.

Flask session endpoints:

- `GET /api/v1/sessions` — list saved chats
- `POST /api/v1/sessions` — create a session
- `GET /api/v1/sessions/<id>` — load one chat
- `POST /api/v1/sessions/<id>/messages` — append messages
- `PATCH /api/v1/sessions/<id>` — rename a chat
- `DELETE /api/v1/sessions/<id>` — delete a chat

## Test

```bash
docker compose --profile test run --rm --build backend-tests
docker compose --profile test run --rm backend-tests ruff check app tests
```

## Stop

```bash
docker compose down
```
