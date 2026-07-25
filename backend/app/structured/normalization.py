from typing import Any


def normalize_movie_record(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize the movie schema while preserving source fields."""
    return {
        **record,
        "imdb_id": str(record.get("imdb_id") or record.get("id") or "").strip(),
        "title": str(record.get("title") or "").strip(),
        "year": _integer(record.get("year")),
        "runtime": _integer(record.get("runtime")),
        "genres": _strings(record.get("genres")),
        "imdb_rating": _number(record.get("imdb_rating")),
        "imdb_votes": _integer(record.get("imdb_votes")),
        "tmdb_vote_average": _number(record.get("tmdb_vote_average")),
        "directors": _strings(record.get("directors")),
        "writers": _strings(record.get("writers")),
        "top_cast": _cast(record.get("top_cast")),
        "source_urls": (
            record.get("source_urls") if isinstance(record.get("source_urls"), dict) else {}
        ),
    }


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _cast(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        item
        for item in value
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value not in {None, ""} else None
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in {None, ""} else None
    except (TypeError, ValueError):
        return None
