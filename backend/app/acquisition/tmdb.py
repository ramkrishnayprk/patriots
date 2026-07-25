import json
import os
import time
from collections import deque
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import Settings


class TmdbClient:
    def __init__(
        self,
        settings: Settings,
        *,
        cache_dir: Path,
        session: requests.Session | None = None,
    ):
        settings.require_tmdb_api_key()
        self.settings = settings
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or _session(settings.user_agent)
        self.request_times: deque[float] = deque()

    def enrich(self, imdb_id: str) -> dict[str, Any]:
        cache_path = self.cache_dir / f"{imdb_id}.json"
        cached = _read_json(cache_path)
        if isinstance(cached, dict) and (
            cached.get("status") == "matched"
            and cached.get("release_date")
            or _is_fresh(cache_path, self.settings.tmdb_transient_cache_hours)
        ):
            return cached

        found = self._get(
            f"/find/{imdb_id}",
            params={"external_source": "imdb_id"},
        )
        matches = found.get("movie_results") if isinstance(found, dict) else None
        if not isinstance(matches, list) or not matches:
            payload = {"status": "no_match", "imdb_id": imdb_id}
            _write_json_atomic(cache_path, payload)
            return payload

        tmdb_id = matches[0].get("id")
        if not isinstance(tmdb_id, int):
            payload = {"status": "no_match", "imdb_id": imdb_id}
            _write_json_atomic(cache_path, payload)
            return payload

        details = self._get(f"/movie/{tmdb_id}")
        returned_imdb_id = details.get("imdb_id")
        if returned_imdb_id and returned_imdb_id != imdb_id:
            payload = {
                "status": "join_mismatch",
                "imdb_id": imdb_id,
                "tmdb_id": tmdb_id,
            }
        else:
            payload = {
                "status": "matched",
                "imdb_id": imdb_id,
                "tmdb_id": tmdb_id,
                "title": details.get("title"),
                "original_title": details.get("original_title"),
                "overview": details.get("overview") or None,
                "tagline": details.get("tagline") or None,
                "release_date": details.get("release_date") or None,
                "runtime": details.get("runtime"),
                "genres": [
                    genre.get("name")
                    for genre in details.get("genres", [])
                    if isinstance(genre, dict) and genre.get("name")
                ],
                "tmdb_vote_average": details.get("vote_average"),
            }
        _write_json_atomic(cache_path, payload)
        return payload

    def _get(self, path: str, *, params: dict[str, str] | None = None) -> dict[str, Any]:
        self._wait_for_capacity()
        response = self.session.get(
            f"{self.settings.tmdb_base_url}{path}",
            params={"api_key": self.settings.tmdb_api_key, **(params or {})},
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("TMDb returned a non-object JSON response.")
        return payload

    def _wait_for_capacity(self) -> None:
        now = time.monotonic()
        window = self.settings.tmdb_rate_window_seconds
        while self.request_times and now - self.request_times[0] >= window:
            self.request_times.popleft()
        if len(self.request_times) >= self.settings.tmdb_rate_limit:
            delay = window - (now - self.request_times[0])
            if delay > 0:
                time.sleep(delay)
            now = time.monotonic()
            while self.request_times and now - self.request_times[0] >= window:
                self.request_times.popleft()
        self.request_times.append(time.monotonic())


def _session(user_agent: str) -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=2,
        status_forcelist=(408, 425, 429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount(
        "https://",
        HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4),
    )
    session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
    return session


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _is_fresh(path: Path, hours: float) -> bool:
    if hours <= 0 or not path.is_file():
        return False
    return time.time() - path.stat().st_mtime < hours * 3600


def _write_json_atomic(path: Path, data: Any) -> None:
    temporary_path = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(data, temporary, ensure_ascii=False, separators=(",", ":"))
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
