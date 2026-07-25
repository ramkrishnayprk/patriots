import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.structured.repository import StructuredRecordRepository

QueryPath = Literal["structured", "semantic"]
Operation = Literal["list", "count", "summary"]

ENUMERATION_PATTERNS = (
    r"\bhow many\b",
    r"\bcount\b",
    r"\blist\b",
    r"\bshow me\b",
    r"\bwhich\b",
    r"\bwhat (?:movies?|films?)\b",
    r"\ball\b",
    r"\breleased\b",
    r"\breleases\b",
)
SEMANTIC_PATTERNS = (
    r"\bplot\b",
    r"\bstory\b",
    r"\bending\b",
    r"\bwhat happens\b",
    r"\bexplain\b",
    r"\bthemes?\b",
    r"\breception\b",
    r"\btell me about\b",
)
CATALOG_PATTERN = re.compile(r"\b(movie|movies|film|films|release|releases)\b")
GENRE_ALIASES = {
    "action": "Action",
    "adventure": "Adventure",
    "animation": "Animation",
    "comedy": "Comedy",
    "crime": "Crime",
    "documentary": "Documentary",
    "drama": "Drama",
    "family": "Family",
    "fantasy": "Fantasy",
    "history": "History",
    "horror": "Horror",
    "music": "Music",
    "mystery": "Mystery",
    "romance": "Romance",
    "science fiction": "Science Fiction",
    "sci fi": "Science Fiction",
    "scifi": "Science Fiction",
    "thriller": "Thriller",
    "war": "War",
    "western": "Western",
}
STOP_WORDS = {
    "all",
    "and",
    "are",
    "available",
    "count",
    "dataset",
    "directed",
    "film",
    "films",
    "for",
    "from",
    "have",
    "how",
    "in",
    "is",
    "list",
    "many",
    "me",
    "movie",
    "movies",
    "of",
    "released",
    "releases",
    "show",
    "so",
    "star",
    "stars",
    "the",
    "there",
    "this",
    "to",
    "what",
    "which",
    "with",
    "were",
    "yet",
    "far",
    "by",
    "year",
}


@dataclass(frozen=True)
class RouteDecision:
    path: QueryPath
    operation: Operation | None
    filters: dict[str, Any]
    reason: str
    topic_terms: tuple[str, ...] = ()


def route_query(query: str, *, mode: str = "auto") -> RouteDecision:
    if mode not in {"auto", "structured", "semantic"}:
        raise ValueError("mode must be auto, structured, or semantic.")
    normalized = _normalize(query)
    filters = _extract_filters(normalized)
    topic_terms = _topic_terms(normalized, filters)
    operation = _operation(normalized, filters, topic_terms)

    if mode == "semantic":
        return RouteDecision("semantic", None, {}, "forced_semantic")
    if mode == "structured":
        return RouteDecision(
            "structured", operation, filters, "forced_structured", topic_terms
        )
    if any(re.search(pattern, normalized) for pattern in SEMANTIC_PATTERNS):
        return RouteDecision("semantic", None, {}, "plot_or_semantic_intent")
    enumeration = any(re.search(pattern, normalized) for pattern in ENUMERATION_PATTERNS)
    target = bool(CATALOG_PATTERN.search(normalized) or filters or topic_terms)
    if enumeration and target:
        return RouteDecision(
            "structured",
            operation,
            filters,
            "enumeration_or_aggregate_intent",
            topic_terms,
        )
    return RouteDecision("semantic", None, {}, "fact_or_semantic_intent")


def run_structured_query(
    query: str,
    *,
    repository: StructuredRecordRepository,
    decision: RouteDecision,
    max_list_items: int = 50,
) -> dict[str, Any]:
    if decision.path != "structured" or decision.operation is None:
        raise ValueError("A structured route decision is required.")
    if max_list_items < 1:
        raise ValueError("max_list_items must be positive.")

    records = repository.list_records()
    matched = [
        record
        for record in records
        if _matches(record, decision.filters, decision.topic_terms)
    ]
    response_filters = dict(decision.filters)
    if decision.topic_terms:
        response_filters["title_terms"] = list(decision.topic_terms)
    base = {
        "path": "structured",
        "operation": decision.operation,
        "query": query,
        "filters": response_filters,
        "count": len(matched),
        "router": {
            "reason": decision.reason,
            "vector_db_used": False,
            "openai_used": False,
        },
        "diagnostics": {
            "records_scanned": len(records),
            "records_matched": len(matched),
        },
    }
    if not matched and decision.operation != "summary":
        return {
            **base,
            "type": "not_in_sources",
            "answer": "No movies matched those structured filters.",
            "items": [],
            "groups": {},
            "sources": [],
        }
    if decision.operation == "summary":
        groups = _groups(records)
        return {
            **base,
            "type": "structured_answer",
            "answer": _summary_answer(len(records), groups),
            "count": len(records),
            "items": [],
            "groups": groups,
            "sources": [],
        }
    if decision.operation == "count":
        noun = "movie" if len(matched) == 1 else "movies"
        return {
            **base,
            "type": "structured_answer",
            "answer": f"There are {len(matched)} matching {noun}.",
            "items": [],
            "truncated": False,
            "groups": {},
            "sources": [],
        }

    items = [_public_record(record) for record in matched]
    visible = items[:max_list_items]
    titles = ", ".join(item["title"] for item in visible)
    suffix = (
        f" Showing the first {max_list_items}." if len(items) > max_list_items else ""
    )
    return {
        **base,
        "type": "structured_answer",
        "answer": f"Matching movies ({len(items)}): {titles}.{suffix}",
        "items": visible,
        "truncated": len(items) > max_list_items,
        "groups": {},
        "sources": [
            {"n": number, "title": item["title"], "url": item["url"]}
            for number, item in enumerate(visible, start=1)
        ],
    }


def _extract_filters(query: str) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", query)
    if year_match:
        filters["year"] = int(year_match.group(1))
    for phrase, genre in sorted(
        GENRE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if re.search(rf"\b{re.escape(phrase)}\b", query):
            filters["genre"] = genre
            break
    rating = re.search(
        r"\b(?:imdb\s+)?rat(?:ed|ing)?\s*(>=|>|at least|above|over)\s*(\d(?:\.\d+)?)",
        query,
    )
    if rating:
        filters["min_imdb_rating"] = float(rating.group(2))
    maximum_rating = re.search(
        r"\b(?:imdb\s+)?rat(?:ed|ing)?\s*(<=|<|at most|below|under)\s*(\d(?:\.\d+)?)",
        query,
    )
    if maximum_rating:
        filters["max_imdb_rating"] = float(maximum_rating.group(2))
    return filters


def _operation(
    query: str, filters: dict[str, Any], topic_terms: tuple[str, ...]
) -> Operation:
    if re.search(r"\b(how many|count|number of)\b", query):
        return "count"
    broad = not filters and not topic_terms
    if broad and re.search(r"\b(what (?:movies?|films?)|all (?:movies?|films?))\b", query):
        return "summary"
    return "list"


def _topic_terms(query: str, filters: dict[str, Any]) -> tuple[str, ...]:
    value = query
    for phrase, genre in GENRE_ALIASES.items():
        if filters.get("genre") == genre:
            value = re.sub(rf"\b{re.escape(phrase)}\b", " ", value)
    tokens = re.findall(r"[a-z0-9]+", value)
    year = str(filters.get("year") or "")
    rating = str(filters.get("min_imdb_rating") or filters.get("max_imdb_rating") or "")
    rating_parts = set(rating.split("."))
    ignored = STOP_WORDS | {
        "rating",
        "rated",
        "imdb",
        "above",
        "over",
        "below",
        "under",
        "least",
        "most",
        "at",
    }
    return tuple(
        token
        for token in tokens
        if token not in ignored
        and token != year
        and token not in rating_parts
        and len(token) > 1
    )


def _matches(
    record: dict[str, Any],
    filters: dict[str, Any],
    topic_terms: tuple[str, ...],
) -> bool:
    if filters.get("year") is not None and record.get("year") != filters["year"]:
        return False
    if "genre" in filters:
        genres = {_normalize(value) for value in record.get("genres", [])}
        if _normalize(filters["genre"]) not in genres:
            return False
    rating = record.get("imdb_rating")
    if "min_imdb_rating" in filters:
        if rating is None or rating < filters["min_imdb_rating"]:
            return False
    if "max_imdb_rating" in filters:
        if rating is None or rating > filters["max_imdb_rating"]:
            return False
    if topic_terms:
        searchable = _normalize(
            " ".join(
                [
                    str(record.get("title") or ""),
                    str(record.get("original_title") or ""),
                    " ".join(record.get("directors") or []),
                    " ".join(
                        str(item.get("name") or "")
                        for item in record.get("top_cast", [])
                        if isinstance(item, dict)
                    ),
                ]
            )
        )
        if not all(term in searchable for term in topic_terms):
            return False
    return True


def _groups(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    years = Counter(record.get("year") or "Unknown" for record in records)
    genres = Counter(
        genre
        for record in records
        for genre in (record.get("genres") or ["Uncategorized"])
    )
    return {
        "year": [
            {"value": value, "count": count}
            for value, count in sorted(years.items(), key=lambda item: str(item[0]))
        ],
        "genre": [
            {"value": value, "count": count}
            for value, count in sorted(genres.items())
        ],
    }


def _summary_answer(total: int, groups: dict[str, list[dict[str, Any]]]) -> str:
    top_genres = sorted(
        groups["genre"], key=lambda item: (-item["count"], item["value"])
    )[:8]
    genres = ", ".join(f"{item['value']}: {item['count']}" for item in top_genres)
    return (
        f"There are {total} movies in the current dataset. Top genres: {genres}. "
        "Ask for a year, genre, rating threshold, title, director, or cast member."
    )


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    source_urls = record.get("source_urls") or {}
    return {
        "imdb_id": record.get("imdb_id"),
        "title": record.get("title"),
        "original_title": record.get("original_title"),
        "release_date": record.get("release_date"),
        "year": record.get("year"),
        "runtime": record.get("runtime"),
        "genres": record.get("genres", []),
        "imdb_rating": record.get("imdb_rating"),
        "imdb_votes": record.get("imdb_votes"),
        "tmdb_vote_average": record.get("tmdb_vote_average"),
        "directors": record.get("directors", []),
        "writers": record.get("writers", []),
        "top_cast": record.get("top_cast", []),
        "overview": record.get("overview"),
        "url": source_urls.get("imdb") or record.get("url", ""),
        "source_urls": source_urls,
    }


def _normalize(value: str) -> str:
    value = re.sub(r"[-_/]+", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def decision_as_dict(decision: RouteDecision) -> dict[str, Any]:
    return asdict(decision)
