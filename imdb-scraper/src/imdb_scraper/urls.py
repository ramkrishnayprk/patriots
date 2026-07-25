from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

TITLE_PATH = re.compile(r"^/title/(tt\d+)/?$", re.IGNORECASE)
ALLOWED_HOSTS = {"imdb.com", "www.imdb.com"}


def normalize_title_url(value: str) -> tuple[str, str] | None:
    raw = value.strip()
    if not raw or raw.startswith("#"):
        return None
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    match = TITLE_PATH.match(parsed.path)
    if parsed.scheme not in {"http", "https"} or host not in ALLOWED_HOSTS or not match:
        raise ValueError(f"Unsupported IMDb title URL: {raw}")
    imdb_id = match.group(1).lower()
    normalized = urlunparse(
        ("https", "www.imdb.com", f"/title/{imdb_id}/", "", "", "")
    )
    return normalized, imdb_id


def load_seed_urls(path: Path, max_titles: int) -> list[tuple[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Seed URL file does not exist: {path}")
    output: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        try:
            normalized = normalize_title_url(line)
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: {exc}") from exc
        if normalized is None:
            continue
        url, imdb_id = normalized
        if imdb_id in seen:
            continue
        seen.add(imdb_id)
        output.append((url, imdb_id))
        if len(output) == max_titles:
            break
    return output
