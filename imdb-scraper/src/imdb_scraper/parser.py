from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup

from imdb_scraper.urls import normalize_title_url

ISO_DURATION = re.compile(
    r"^P(?:\d+D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?)?$"
)


class ParseError(ValueError):
    """The fetched HTML did not contain usable IMDb title metadata."""


def parse_title_page(html: str, source_url: str) -> dict[str, Any]:
    normalized = normalize_title_url(source_url)
    if normalized is None:
        raise ParseError("A title URL is required.")
    canonical_url, imdb_id = normalized
    soup = BeautifulSoup(html, "lxml")
    payload = _movie_json_ld(soup)
    if not payload:
        raise ParseError("No Movie JSON-LD object was found.")

    aggregate = _mapping(payload.get("aggregateRating"))
    directors = _names(payload.get("director"))
    creators = _names(payload.get("creator"))
    actors = _names(payload.get("actor"))
    canonical_tag = soup.select_one('link[rel="canonical"]')
    canonical = (
        str(canonical_tag.get("href")).strip()
        if canonical_tag and canonical_tag.get("href")
        else canonical_url
    )
    genres = payload.get("genre")
    if isinstance(genres, str):
        genres = [genres]
    elif not isinstance(genres, list):
        genres = []

    return {
        "imdb_id": imdb_id,
        "title": _text(payload.get("name")),
        "original_title": _text(payload.get("alternateName")),
        "description": _text(payload.get("description")),
        "content_rating": _text(payload.get("contentRating")),
        "date_published": _text(payload.get("datePublished")),
        "duration_iso8601": _text(payload.get("duration")),
        "runtime_minutes": _duration_minutes(payload.get("duration")),
        "genres": [str(value).strip() for value in genres if str(value).strip()],
        "keywords": _keywords(payload.get("keywords")),
        "directors": directors,
        "creators": creators,
        "actors": actors,
        "rating": _float(aggregate.get("ratingValue")),
        "rating_count": _integer(aggregate.get("ratingCount")),
        "best_rating": _float(aggregate.get("bestRating")),
        "worst_rating": _float(aggregate.get("worstRating")),
        "image_url": _text(payload.get("image")),
        "canonical_url": canonical,
        "source_url": source_url,
        "raw_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "scraped_at": datetime.now(UTC).isoformat(),
    }


def _movie_json_ld(soup: BeautifulSoup) -> dict[str, Any] | None:
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text()
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for candidate in _json_ld_objects(value):
            object_type = candidate.get("@type")
            types = object_type if isinstance(object_type, list) else [object_type]
            if any(str(value).lower() in {"movie", "tvseries"} for value in types):
                return candidate
    return None


def _json_ld_objects(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        graph = value.get("@graph")
        if isinstance(graph, list):
            return [item for item in graph if isinstance(item, dict)]
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _names(value: Any) -> list[str]:
    items = value if isinstance(value, list) else [value]
    output = []
    for item in items:
        if isinstance(item, dict):
            name = _text(item.get("name"))
        else:
            name = _text(item)
        if name and name not in output:
            output.append(name)
    return output


def _keywords(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = value.split(",")
    else:
        items = []
    return [str(item).strip() for item in items if str(item).strip()]


def _duration_minutes(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    match = ISO_DURATION.match(value)
    if not match:
        return None
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    return hours * 60 + minutes


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


def _integer(value: Any) -> int | None:
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
