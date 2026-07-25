import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Literal

from app.structured.repository import StructuredRecordRepository

QueryPath = Literal["structured", "semantic"]
Operation = Literal["list", "count", "summary", "rank"]
SortDirection = Literal["asc", "desc"]

ENUMERATION_PATTERNS = (
    r"\bhow many\b",
    r"\bcount\b",
    r"\bnumber of\b",
    r"\blist\b",
    r"\bshow me\b",
    r"\bwhich\b",
    r"\bwhat\b.*\b(?:movies?|films?)\b",
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
    r"\bwhat(?:'s| is| are)\b.+\babout\b",
    r"\b(?:movies?|films?) about\b",
)
PERSON_PATTERNS = (
    r"\b(?:movies?|films?)\s+(?:directed|written)\s+by\b",
    r"\b(?:movies?|films?)\s+by\b",
    r"\b(?:movies?|films?)\s+(?:with|starring|featuring)\b",
    r"\b(?:movies?|films?)\s+(?:star|stars|feature|features)\b",
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
MONTH_ALIASES = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
STOP_WORDS = {
    "about",
    "all",
    "and",
    "are",
    "at",
    "available",
    "best",
    "by",
    "count",
    "dataset",
    "directed",
    "director",
    "directors",
    "far",
    "feature",
    "features",
    "featuring",
    "film",
    "films",
    "first",
    "for",
    "from",
    "have",
    "highest",
    "how",
    "in",
    "is",
    "latest",
    "list",
    "longest",
    "many",
    "me",
    "most",
    "movie",
    "movies",
    "newest",
    "number",
    "of",
    "or",
    "popular",
    "rated",
    "recent",
    "released",
    "releases",
    "rating",
    "show",
    "shortest",
    "so",
    "star",
    "stars",
    "starring",
    "the",
    "there",
    "this",
    "to",
    "top",
    "voted",
    "what",
    "which",
    "with",
    "were",
    "writer",
    "writers",
    "written",
    "year",
    "yet",
}


@dataclass(frozen=True)
class RouteDecision:
    path: QueryPath
    operation: Operation | None
    filters: dict[str, Any]
    reason: str
    topic_terms: tuple[str, ...] = ()
    sort_by: str | None = None
    sort_direction: SortDirection | None = None
    limit: int | None = None


def route_query(query: str, *, mode: str = "auto") -> RouteDecision:
    if mode not in {"auto", "structured", "semantic"}:
        raise ValueError("mode must be auto, structured, or semantic.")

    normalized = _normalize(query)
    filters = _extract_filters(normalized)
    topic_terms = _topic_terms(normalized, filters)
    ranking = _ranking_spec(normalized)
    person_intent = _has_person_intent(normalized, topic_terms)
    if person_intent:
        filters["person_name"] = " ".join(topic_terms)
        role = _person_role(normalized)
        if role:
            filters["person_role"] = role
        topic_terms = ()

    operation = _operation(normalized, filters, topic_terms, ranking=ranking)
    sort_by, sort_direction = ranking or (None, None)
    limit = _requested_limit(normalized) if ranking else None

    if mode == "semantic":
        return RouteDecision("semantic", None, {}, "forced_semantic")
    if mode == "structured":
        return RouteDecision(
            "structured",
            operation,
            filters,
            "forced_structured",
            topic_terms,
            sort_by,
            sort_direction,
            limit,
        )
    if any(re.search(pattern, normalized) for pattern in SEMANTIC_PATTERNS):
        return RouteDecision("semantic", None, {}, "plot_or_semantic_intent")
    if ranking:
        return RouteDecision(
            "structured",
            "rank",
            filters,
            "ranking_intent",
            topic_terms,
            sort_by,
            sort_direction,
            limit,
        )
    if person_intent:
        return RouteDecision(
            "structured",
            "list",
            filters,
            "person_filter_intent",
        )

    enumeration = any(
        re.search(pattern, normalized) for pattern in ENUMERATION_PATTERNS
    )
    target = bool(CATALOG_PATTERN.search(normalized) or filters or topic_terms)
    if enumeration and target:
        return RouteDecision(
            "structured",
            operation,
            filters,
            "enumeration_or_aggregate_intent",
            topic_terms,
        )
    if filters and CATALOG_PATTERN.search(normalized):
        return RouteDecision(
            "structured",
            operation,
            filters,
            "metadata_filter_intent",
            topic_terms,
        )
    return RouteDecision("semantic", None, {}, "fact_or_semantic_intent")


def run_structured_query(
    query: str,
    *,
    repository: StructuredRecordRepository,
    decision: RouteDecision,
    max_list_items: int = 50,
    min_rating_votes: int = 1_000,
    default_rank_limit: int = 10,
) -> dict[str, Any]:
    if decision.path != "structured" or decision.operation is None:
        raise ValueError("A structured route decision is required.")
    if max_list_items < 1:
        raise ValueError("max_list_items must be positive.")
    if min_rating_votes < 0:
        raise ValueError("min_rating_votes cannot be negative.")
    if default_rank_limit < 1:
        raise ValueError("default_rank_limit must be positive.")

    records = repository.list_records()
    effective_filters = dict(decision.filters)
    if decision.operation == "rank" and decision.sort_by == "imdb_rating":
        effective_filters.setdefault("min_imdb_votes", min_rating_votes)

    matched = [
        record
        for record in records
        if _matches(record, effective_filters, decision.topic_terms)
    ]
    response_filters = _public_filters(effective_filters)
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
    if not matched:
        return {
            **base,
            "type": "not_in_sources",
            "answer": _no_matches_answer(effective_filters, records),
            "items": [],
            "groups": {},
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
    if decision.operation == "rank":
        return _ranked_response(
            base=base,
            records=matched,
            decision=decision,
            max_list_items=max_list_items,
            default_rank_limit=default_rank_limit,
        )

    items = [_public_record(record) for record in matched]
    visible = items[:max_list_items]
    titles = "\n".join(
        f"- {item['title']} [{number}]"
        for number, item in enumerate(visible, start=1)
    )
    suffix = (
        f"\n\nShowing the first {max_list_items} of {len(items)}."
        if len(items) > max_list_items
        else ""
    )
    person = effective_filters.get("person_name")
    answer = (
        f"Here are the movies featuring {_display_name(str(person))} "
        f"in this dataset:\n\n{titles}{suffix}"
        if person
        else f"Here are the {len(items)} matching movies:\n\n{titles}{suffix}"
    )
    return {
        **base,
        "type": "structured_answer",
        "answer": answer,
        "items": visible,
        "truncated": len(items) > max_list_items,
        "groups": {},
        "sources": _sources(visible),
    }


def _ranked_response(
    *,
    base: dict[str, Any],
    records: list[dict[str, Any]],
    decision: RouteDecision,
    max_list_items: int,
    default_rank_limit: int,
) -> dict[str, Any]:
    if not decision.sort_by or not decision.sort_direction:
        raise ValueError("A ranking decision must include a sort field and direction.")

    sortable = [
        (record, _sort_value(record, decision.sort_by)) for record in records
    ]
    sortable = [(record, value) for record, value in sortable if value is not None]
    if not sortable:
        label = _ranking_label(decision.sort_by)
        return {
            **base,
            "type": "not_in_sources",
            "answer": f"No matching movies had a usable {label} for ranking.",
            "count": 0,
            "items": [],
            "truncated": False,
            "groups": {},
            "ranking": {
                "field": decision.sort_by,
                "direction": decision.sort_direction,
                "requested_limit": decision.limit or default_rank_limit,
                "returned": 0,
            },
            "sources": [],
        }
    sortable.sort(key=lambda item: str(item[0].get("title") or "").lower())
    sortable.sort(
        key=lambda item: item[1],
        reverse=decision.sort_direction == "desc",
    )

    requested_limit = decision.limit or default_rank_limit
    limit = min(requested_limit, max_list_items)
    items = [_public_record(record) for record, _value in sortable[:limit]]
    label = _ranking_label(decision.sort_by)
    # The [n] marker ties each row to _sources(items)[n-1] — both enumerate the
    # same list from 1, so the ordinals always line up. The frontend renders
    # these as inline citation badges.
    ranked_titles = "\n".join(
        f"{number}. {item['title']} — "
        f"{_format_rank_value(item, decision.sort_by)} [{number}]"
        for number, item in enumerate(items, start=1)
    )
    vote_note = ""
    min_votes = base["filters"].get("min_imdb_votes")
    if decision.sort_by == "imdb_rating" and min_votes is not None:
        vote_note = f" with at least {int(min_votes):,} IMDb votes"
    if decision.sort_by == "imdb_rating":
        framing = (
            f"Here are the highest-rated matching movies{vote_note}:"
        )
    else:
        framing = f"Here are the top {len(items)} matching movies by {label}:"
    answer = f"{framing}\n\n{ranked_titles}"

    ranking = {
        "field": decision.sort_by,
        "direction": decision.sort_direction,
        "requested_limit": requested_limit,
        "returned": len(items),
    }
    if min_votes is not None:
        ranking["min_imdb_votes"] = min_votes
    return {
        **base,
        "type": "structured_answer",
        "answer": answer,
        "count": len(sortable),
        "items": items,
        "truncated": len(sortable) > len(items),
        "groups": {},
        "ranking": ranking,
        "sources": _sources(items),
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
    release_months = {
        number
        for name, number in MONTH_ALIASES.items()
        if re.search(rf"\b{re.escape(name)}\b", query)
    }
    if len(release_months) == 1:
        filters["release_month"] = release_months.pop()
    elif release_months:
        filters["release_months"] = sorted(release_months)

    rating = re.search(
        r"\b(?:imdb\s+)?rat(?:ed|ing)?\s*(>=|>|at least|above|over)\s*"
        r"(\d(?:\.\d+)?)",
        query,
    )
    if rating:
        filters["min_imdb_rating"] = float(rating.group(2))
    maximum_rating = re.search(
        r"\b(?:imdb\s+)?rat(?:ed|ing)?\s*(<=|<|at most|below|under)\s*"
        r"(\d(?:\.\d+)?)",
        query,
    )
    if maximum_rating:
        filters["max_imdb_rating"] = float(maximum_rating.group(2))
    if re.search(
        r"\b(released|releases|release date|newest|latest|most recent)\b",
        query,
    ):
        filters["has_release_date"] = True
    return filters


def _operation(
    query: str,
    filters: dict[str, Any],
    topic_terms: tuple[str, ...],
    *,
    ranking: tuple[str, SortDirection] | None,
) -> Operation:
    if ranking:
        return "rank"
    if re.search(r"\b(how many|count|number of)\b", query):
        return "count"
    broad = not filters and not topic_terms
    if broad and re.search(
        r"\b(what\b.*\b(?:movies?|films?)|all (?:movies?|films?))\b",
        query,
    ):
        return "summary"
    return "list"


def _ranking_spec(query: str) -> tuple[str, SortDirection] | None:
    if re.search(
        r"\b(top(?:\s+\d+)?[\s-]?rated|highest[\s-]?rated|best)\b",
        query,
    ) or re.search(r"\btop\s+\d{1,3}\s+(?:movies?|films?)\b", query):
        return "imdb_rating", "desc"
    if re.search(r"\b(newest|latest|most recent|recently released)\b", query):
        return "release_date", "desc"
    if re.search(r"\blongest\b", query):
        return "runtime", "desc"
    if re.search(r"\bshortest\b", query):
        return "runtime", "asc"
    if re.search(r"\b(most voted|most popular)\b", query):
        return "imdb_votes", "desc"
    return None


def _requested_limit(query: str) -> int | None:
    match = re.search(r"\btop\s+(\d{1,3})\b", query)
    return max(1, int(match.group(1))) if match else None


def _has_person_intent(query: str, topic_terms: tuple[str, ...]) -> bool:
    if not topic_terms:
        return False
    if any(re.search(pattern, query) for pattern in PERSON_PATTERNS):
        return True
    return bool(
        len(topic_terms) >= 2
        and re.search(r"\b(?:movies?|films?)\s*[?.!]*$", query)
    )


def _person_role(query: str) -> str | None:
    if re.search(r"\bdirected\s+by\b", query):
        return "directors"
    if re.search(r"\bwritten\s+by\b", query):
        return "writers"
    if re.search(
        r"\b(star|stars|starring|feature|features|featuring|with)\b",
        query,
    ):
        return "top_cast"
    return None


def _topic_terms(query: str, filters: dict[str, Any]) -> tuple[str, ...]:
    value = re.sub(r"\btop\s+\d{1,3}\b", "top", query)
    for phrase, genre in GENRE_ALIASES.items():
        if filters.get("genre") == genre:
            value = re.sub(rf"\b{re.escape(phrase)}\b", " ", value)
    selected_months = {
        filters.get("release_month"),
        *(filters.get("release_months") or []),
    }
    for name, number in MONTH_ALIASES.items():
        if number in selected_months:
            value = re.sub(rf"\b{re.escape(name)}\b", " ", value)

    tokens = re.findall(r"[a-z0-9]+", value)
    year = str(filters.get("year") or "")
    ratings = {
        str(filters.get("min_imdb_rating") or ""),
        str(filters.get("max_imdb_rating") or ""),
    }
    rating_parts = {
        part for rating in ratings for part in rating.split(".") if part
    }
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
    if "release_month" in filters:
        released = _date_value(record.get("release_date"))
        if released is None or released.month != filters["release_month"]:
            return False
    if "release_months" in filters:
        released = _date_value(record.get("release_date"))
        if released is None or released.month not in filters["release_months"]:
            return False
    if (
        filters.get("has_release_date")
        and _date_value(record.get("release_date")) is None
    ):
        return False

    rating = record.get("imdb_rating")
    if "min_imdb_rating" in filters:
        if rating is None or rating < filters["min_imdb_rating"]:
            return False
    if "max_imdb_rating" in filters:
        if rating is None or rating > filters["max_imdb_rating"]:
            return False
    votes = record.get("imdb_votes")
    if "min_imdb_votes" in filters:
        if votes is None or votes < filters["min_imdb_votes"]:
            return False
    if "person_name" in filters and not _person_matches(
        record,
        str(filters["person_name"]),
        filters.get("person_role"),
    ):
        return False
    if topic_terms:
        searchable = _normalize(
            " ".join(
                [
                    str(record.get("title") or ""),
                    str(record.get("original_title") or ""),
                    " ".join(record.get("directors") or []),
                    " ".join(record.get("writers") or []),
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


def _person_matches(
    record: dict[str, Any],
    person_name: str,
    role: Any,
) -> bool:
    role_values = {
        "directors": record.get("directors") or [],
        "writers": record.get("writers") or [],
        "top_cast": [
            str(item.get("name") or "")
            for item in record.get("top_cast", [])
            if isinstance(item, dict)
        ],
    }
    selected_roles = [str(role)] if role in role_values else list(role_values)
    person_terms = _normalize(person_name).split()
    candidates = (
        _normalize(str(value)).split()
        for selected_role in selected_roles
        for value in role_values[selected_role]
    )
    return any(all(term in candidate for term in person_terms) for candidate in candidates)


def _sort_value(record: dict[str, Any], field: str) -> Any:
    if field == "release_date":
        return _date_value(record.get(field))
    if field in {"imdb_rating", "imdb_votes", "runtime"}:
        value = record.get(field)
        return float(value) if isinstance(value, int | float) else None
    raise ValueError(f"Unsupported ranking field: {field}.")


def _date_value(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


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
    genres = ", ".join(
        f"{item['value']}: {item['count']}" for item in top_genres
    )
    return (
        f"There are {total} movies in the current dataset. Top genres: {genres}. "
        "Ask for a year, month, genre, rating, title, director, writer, or cast member."
    )


def _no_matches_answer(
    filters: dict[str, Any],
    records: list[dict[str, Any]],
) -> str:
    person = filters.get("person_name")
    if person:
        years = {record.get("year") for record in records if record.get("year")}
        dataset = f"this {years.pop()} dataset" if len(years) == 1 else "this dataset"
        return (
            f"No movies featuring {_display_name(str(person))} were found in "
            f"{dataset}."
        )
    return "No movies matched those structured filters."


def _public_filters(filters: dict[str, Any]) -> dict[str, Any]:
    public = dict(filters)
    if public.get("person_role") == "top_cast":
        public["person_role"] = "cast"
    return public


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


def _sources(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"n": number, "title": item["title"], "url": item["url"]}
        for number, item in enumerate(items, start=1)
    ]


def _ranking_label(field: str) -> str:
    return {
        "imdb_rating": "IMDb rating",
        "release_date": "release date",
        "runtime": "runtime",
        "imdb_votes": "IMDb vote count",
    }[field]


def _format_rank_value(item: dict[str, Any], field: str) -> str:
    if field == "imdb_rating":
        return f"{item.get('imdb_rating')} IMDb"
    if field == "release_date":
        return str(item.get("release_date"))
    if field == "runtime":
        return f"{item.get('runtime')} min"
    if field == "imdb_votes":
        return f"{int(item.get('imdb_votes') or 0):,} votes"
    return ""


def _display_name(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split())


def _normalize(value: str) -> str:
    value = re.sub(r"[-_/]+", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def decision_as_dict(decision: RouteDecision) -> dict[str, Any]:
    return asdict(decision)
