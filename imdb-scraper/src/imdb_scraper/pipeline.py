from __future__ import annotations

import random
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imdb_scraper.client import FetchError, ScraperApiClient
from imdb_scraper.config import Settings
from imdb_scraper.parser import ParseError, parse_title_page
from imdb_scraper.storage import append_jsonl, atomic_write_json, load_state
from imdb_scraper.urls import load_seed_urls


def run_pipeline(
    settings: Settings,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    settings.require_live_access()
    seeds = load_seed_urls(settings.seeds_path, settings.max_titles)
    if not seeds:
        raise ValueError("No IMDb title URLs were found in the seed file.")

    actual_run_id = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = settings.output_dir / actual_run_id
    raw_dir = run_dir / "raw_html"
    records_path = run_dir / "records.jsonl"
    failures_path = run_dir / "failures.jsonl"
    state_path = run_dir / "state.json"
    manifest_path = run_dir / "manifest.json"
    raw_dir.mkdir(parents=True, exist_ok=True)

    state = load_state(state_path)
    completed = set(_strings(state.get("completed")))
    failed = set(_strings(state.get("failed")))
    client = ScraperApiClient(settings)
    started_at = datetime.now(UTC).isoformat()

    for index, (url, imdb_id) in enumerate(seeds):
        if imdb_id in completed:
            continue
        try:
            fetched = client.fetch(url)
            (raw_dir / f"{imdb_id}.html").write_text(
                fetched.html,
                encoding="utf-8",
            )
            record = parse_title_page(fetched.html, url)
            record["http_status"] = fetched.status_code
            record["content_type"] = fetched.content_type
            append_jsonl(records_path, record)
            completed.add(imdb_id)
            failed.discard(imdb_id)
        except (FetchError, ParseError, OSError, ValueError) as exc:
            append_jsonl(
                failures_path,
                {
                    "imdb_id": imdb_id,
                    "url": url,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "failed_at": datetime.now(UTC).isoformat(),
                },
            )
            failed.add(imdb_id)
        finally:
            atomic_write_json(
                state_path,
                {
                    "completed": sorted(completed),
                    "failed": sorted(failed),
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )
        if index < len(seeds) - 1:
            time.sleep(
                random.uniform(
                    settings.min_delay_seconds,
                    settings.max_delay_seconds,
                )
            )

    manifest = {
        "run_id": actual_run_id,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "seed_count": len(seeds),
        "completed_count": len(completed),
        "failed_count": len(failed),
        "records_file": str(records_path),
        "failures_file": str(failures_path),
        "raw_html_dir": str(raw_dir),
        "render_javascript": settings.render_javascript,
        "premium": settings.premium,
        "country_code": settings.country_code,
    }
    atomic_write_json(manifest_path, manifest)
    return manifest


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]
