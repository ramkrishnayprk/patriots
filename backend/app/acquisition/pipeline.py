import hashlib
import json
import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from rq import get_current_job

from app.acquisition.chunking import create_movie_chunks
from app.acquisition.imdb import assemble_imdb_records, download_datasets
from app.acquisition.storage import MovieRunStorage
from app.acquisition.tmdb import TmdbClient
from app.acquisition.wikipedia import WikipediaClient
from app.config import Settings

logger = logging.getLogger(__name__)


def run_acquisition_job() -> dict[str, Any]:
    job = get_current_job()
    run_id = job.id if job else str(uuid.uuid4())
    return acquire_movies(run_id=run_id, job=job)


def acquire_movies(
    *,
    run_id: str,
    job=None,
    today: date | None = None,
    dataset_paths=None,
    tmdb_client=None,
    wikipedia_client=None,
) -> dict[str, Any]:
    """Build the structured and semantic movie corpora for the configured window."""
    settings = Settings.from_env()
    settings.require_tmdb_api_key()
    window_end = today or date.today()
    if window_end < settings.movie_window_start:
        raise ValueError("The current date precedes MOVIE_WINDOW_START.")
    storage = MovieRunStorage(settings.data_dir, run_id)
    snapshot = window_end.isoformat()

    _progress(job, phase="downloading_imdb", completed=0, total=6)
    paths = dataset_paths or download_datasets(settings, snapshot_date=snapshot)
    _progress(job, phase="joining_imdb", completed=0)
    imdb_records, imdb_stats = assemble_imdb_records(
        paths,
        year=settings.movie_window_start.year,
        title_types=settings.movie_title_types,
        include_adult=settings.movie_include_adult,
        region_preference=settings.movie_region_preference,
        top_cast_limit=settings.movie_top_cast_limit,
    )
    imdb_records = sorted(imdb_records, key=lambda item: item["imdb_id"])[
        : settings.movie_max_candidates
    ]
    imdb_stats["imdb_candidates_selected"] = len(imdb_records)
    imdb_stats["imdb_candidates_skipped_by_limit"] = max(
        0,
        imdb_stats["imdb_candidates"] - len(imdb_records),
    )

    cache_root = settings.data_dir / "enrichment_cache"
    tmdb = tmdb_client or TmdbClient(
        settings,
        cache_dir=cache_root / "tmdb",
    )
    wikipedia = None
    if settings.enable_wikipedia:
        wikipedia = wikipedia_client or WikipediaClient(
            settings,
            cache_dir=cache_root / "wikipedia",
        )

    movies: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    counters = {
        "tmdb_enriched": 0,
        "tmdb_no_match": 0,
        "join_mismatch": 0,
        "outside_window": 0,
        "missing_release_date": 0,
        "no_overview": 0,
        "no_rating_yet": 0,
        "wikipedia_matches": 0,
    }
    fetched_at = datetime.now(UTC).isoformat()

    for index, base in enumerate(imdb_records, 1):
        imdb_id = base["imdb_id"]
        try:
            enrichment = tmdb.enrich(imdb_id)
        except Exception:
            logger.error("TMDb enrichment failed | imdb_id=%s", imdb_id)
            enrichment = {"status": "request_failed", "imdb_id": imdb_id}
            missing.append(
                {"imdb_id": imdb_id, "title": base["title"], "reason": "tmdb_request_failed"}
            )

        status = enrichment.get("status")
        if status == "matched":
            release_date = _date_or_none(enrichment.get("release_date"))
            if release_date is None:
                counters["missing_release_date"] += 1
                missing.append(
                    {
                        "imdb_id": imdb_id,
                        "title": base["title"],
                        "reason": "missing_release_date",
                    }
                )
                continue
            if not settings.movie_window_start <= release_date <= window_end:
                counters["outside_window"] += 1
                missing.append(
                    {
                        "imdb_id": imdb_id,
                        "title": base["title"],
                        "reason": "outside_window",
                        "release_date": release_date.isoformat(),
                    }
                )
                continue
            counters["tmdb_enriched"] += 1
            movie = _merge_tmdb(base, enrichment, release_date)
            movie["window_status"] = "verified"
        elif status == "no_match":
            counters["tmdb_no_match"] += 1
            missing.append(
                {"imdb_id": imdb_id, "title": base["title"], "reason": "no_tmdb_match"}
            )
            movie = _structured_only(base)
        else:
            if status == "join_mismatch":
                counters["join_mismatch"] += 1
            missing.append(
                {
                    "imdb_id": imdb_id,
                    "title": base["title"],
                    "reason": status or "tmdb_unknown_error",
                }
            )
            movie = _structured_only(base)

        wiki_payload = None
        if wikipedia is not None:
            try:
                wiki_payload = wikipedia.enrich(imdb_id, movie["title"], movie["year"])
            except Exception:
                logger.exception("Wikipedia enrichment failed | imdb_id=%s", imdb_id)
            if wiki_payload and wiki_payload.get("status") == "matched":
                counters["wikipedia_matches"] += 1

        movie = _finalize_movie(movie, wiki_payload, fetched_at=fetched_at)
        if movie["imdb_rating"] is None:
            counters["no_rating_yet"] += 1
        if not movie["overview"]:
            counters["no_overview"] += 1
            missing.append(
                {"imdb_id": imdb_id, "title": movie["title"], "reason": "no_overview"}
            )
        movies.append(movie)
        if movie["sections"]:
            documents.append(movie)
            chunks.extend(
                create_movie_chunks(
                    movie,
                    chunk_size=settings.chunk_size,
                    chunk_overlap=settings.chunk_overlap,
                )
            )
        _progress(
            job,
            phase="enriching",
            completed=index,
            total=len(imdb_records),
            movies=len(movies),
            chunks=len(chunks),
        )

    movies = _deduplicate(movies, "imdb_id")
    chunks = _deduplicate(chunks, "id")
    qa_report = {
        "window_start": settings.movie_window_start.isoformat(),
        "window_end": window_end.isoformat(),
        **imdb_stats,
        **counters,
        "structured_movies": len(movies),
        "semantic_movies": len(documents),
        "chunks": len(chunks),
    }
    manifest = {
        "run_id": run_id,
        "snapshot_date": snapshot,
        "window_start": settings.movie_window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "title_types": list(settings.movie_title_types),
        "include_adult": settings.movie_include_adult,
        "region_preference": settings.movie_region_preference,
        "max_candidates": settings.movie_max_candidates,
        "wikipedia_enabled": settings.enable_wikipedia,
        "imdb_datasets": sorted(paths),
        "tmdb_attribution": (
            "This product uses the TMDB API but is not endorsed or certified by TMDB."
        ),
        "generated_at": fetched_at,
    }
    storage.save(
        movies=movies,
        documents=documents,
        chunks=chunks,
        missing_report=missing,
        qa_report=qa_report,
        manifest=manifest,
    )
    summary = {
        "run_id": run_id,
        "movies": len(movies),
        "semantic_movies": len(documents),
        "chunks": len(chunks),
        "missing_report_entries": len(missing),
        "artifacts": storage.relative_run_path(),
        "qa": qa_report,
    }
    _progress(job, phase="completed", **summary)
    logger.info("Movie acquisition complete | %s", json.dumps(summary, separators=(",", ":")))
    return summary


def _merge_tmdb(
    base: dict[str, Any], enrichment: dict[str, Any], release_date: date
) -> dict[str, Any]:
    genres = enrichment.get("genres") or base.get("genres") or []
    return {
        **base,
        "title": enrichment.get("title") or base["title"],
        "original_title": enrichment.get("original_title") or base.get("original_title"),
        "release_date": release_date.isoformat(),
        "runtime": enrichment.get("runtime") or base.get("runtime"),
        "genres": genres,
        "tmdb_id": enrichment.get("tmdb_id"),
        "tmdb_vote_average": enrichment.get("tmdb_vote_average"),
        "overview": enrichment.get("overview"),
        "tagline": enrichment.get("tagline"),
    }


def _structured_only(base: dict[str, Any]) -> dict[str, Any]:
    return {
        **base,
        "release_date": None,
        "tmdb_id": None,
        "tmdb_vote_average": None,
        "overview": None,
        "tagline": None,
        "window_status": "unverified",
    }


def _finalize_movie(
    movie: dict[str, Any],
    wikipedia: dict[str, Any] | None,
    *,
    fetched_at: str,
) -> dict[str, Any]:
    imdb_id = movie["imdb_id"]
    imdb_url = f"https://www.imdb.com/title/{imdb_id}/"
    source_urls = {"imdb": imdb_url}
    if movie.get("tmdb_id"):
        source_urls["tmdb"] = f"https://www.themoviedb.org/movie/{movie['tmdb_id']}"
    if wikipedia and wikipedia.get("url"):
        source_urls["wikipedia"] = wikipedia["url"]

    sections = []
    if movie.get("overview"):
        sections.append({"heading": "Overview", "content": movie["overview"]})
    wikipedia_text = wikipedia.get("text") if wikipedia else None
    if wikipedia_text:
        sections.append({"heading": "Wikipedia", "content": wikipedia_text})
    text = "\n\n".join(
        f"{section['heading']}\n\n{section['content']}" for section in sections
    )
    quick_facts = {
        "release_date": movie.get("release_date"),
        "year": movie.get("year"),
        "runtime": movie.get("runtime"),
        "genres": ", ".join(movie.get("genres") or []),
        "imdb_rating": movie.get("imdb_rating"),
        "directors": ", ".join(movie.get("directors") or []),
    }
    result = {
        **movie,
        "id": imdb_id,
        "document_type": "movie",
        "url": source_urls.get("tmdb", imdb_url),
        "source_urls": source_urls,
        "wikipedia_text": wikipedia_text,
        "sections": sections,
        "text": text,
        "text_length": len(text),
        "quick_facts": quick_facts,
        "fetched_at": fetched_at,
    }
    hash_payload = {
        key: value
        for key, value in result.items()
        if key not in {"content_hash", "fetched_at"}
    }
    result["content_hash"] = hashlib.sha256(
        json.dumps(
            hash_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return result


def _date_or_none(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _deduplicate(records: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return list({record[key]: record for record in records}.values())


def _progress(job, **progress: Any) -> None:
    if job is not None:
        job.meta["progress"] = progress
        job.save_meta()
