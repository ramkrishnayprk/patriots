import re
from pathlib import Path
from typing import Any

import requests

from app.acquisition.tmdb import _read_json, _session, _write_json_atomic
from app.config import Settings


class WikipediaClient:
    API_URL = "https://en.wikipedia.org/w/api.php"

    def __init__(
        self,
        settings: Settings,
        *,
        cache_dir: Path,
        session: requests.Session | None = None,
    ):
        self.settings = settings
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or _session(settings.user_agent)

    def enrich(self, imdb_id: str, title: str, year: int) -> dict[str, Any]:
        cache_path = self.cache_dir / f"{imdb_id}.json"
        cached = _read_json(cache_path)
        if isinstance(cached, dict):
            return cached

        search = self._get(
            {
                "action": "query",
                "list": "search",
                "srsearch": f'intitle:"{title}" {year} film',
                "srlimit": "5",
                "format": "json",
            }
        )
        results = search.get("query", {}).get("search", [])
        page_title = next(
            (
                item.get("title")
                for item in results
                if isinstance(item, dict)
                and _confident_title(title, year, str(item.get("title") or ""))
            ),
            None,
        )
        if not page_title:
            payload = {"status": "no_match", "imdb_id": imdb_id}
            _write_json_atomic(cache_path, payload)
            return payload

        page = self._get(
            {
                "action": "query",
                "prop": "extracts|info",
                "explaintext": "1",
                "inprop": "url",
                "redirects": "1",
                "titles": page_title,
                "format": "json",
                "formatversion": "2",
            }
        )
        pages = page.get("query", {}).get("pages", [])
        first = pages[0] if isinstance(pages, list) and pages else {}
        extract = str(first.get("extract") or "").strip()
        payload = {
            "status": "matched" if extract else "no_text",
            "imdb_id": imdb_id,
            "title": first.get("title") or page_title,
            "url": first.get("fullurl"),
            "text": extract or None,
        }
        _write_json_atomic(cache_path, payload)
        return payload

    def _get(self, params: dict[str, str]) -> dict[str, Any]:
        response = self.session.get(
            self.API_URL,
            params=params,
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Wikipedia returned a non-object JSON response.")
        return payload


def _confident_title(movie_title: str, year: int, page_title: str) -> bool:
    def normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    movie = normalize(movie_title)
    page = normalize(page_title)
    return movie in page and (str(year) in page or "film" in page)
