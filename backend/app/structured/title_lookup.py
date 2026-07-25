import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from rapidfuzz import fuzz

from app.structured.repository import StructuredRecordRepository

LookupIntent = Literal["details", "semantic"]
EntityQuestion = Literal[
    "cast",
    "details",
    "director",
    "more",
    "overview",
    "rating",
    "release_date",
    "runtime",
    "writer",
]

DIRECT_PATTERNS = (
    re.compile(
        r"^\s*(?:show|give)\s+me\s+(?:the\s+)?"
        r"(?:details|information|info)(?:\s+(?:about|of|for))?\s+"
        r"(?P<title>.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:details|information|info)(?:\s+(?:about|of|for))?\s+"
        r"(?P<title>.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*tell\s+me\s+(?:more\s+)?about\s+(?P<title>.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*explain\s+more\s+about\s+(?P<title>.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*what(?:'s|\s+is)\s+(?P<title>.+?)\s+about\s*[?.!]*\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:plot|overview|synopsis)(?:\s+(?:of|for))\s+"
        r"(?P<title>.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:who\s+(?:directed|wrote)|what\s+is\s+the\s+"
        r"(?:runtime|rating)\s+(?:of|for))\s+(?P<title>.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*who\s+(?:is|was)\s+in\s+(?P<title>.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*who\s+(?:acted|acts|starred|stars)\s+in\s+"
        r"(?P<title>.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:cast|actors?)\s+(?:of|in)\s+(?P<title>.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*when\s+(?:was|is)\s+(?P<title>.+?)\s+released\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?P<title>.+?)\s+(?:explain|details?|information|info)\s*$",
        re.IGNORECASE,
    ),
)

SEMANTIC_PATTERNS = (
    re.compile(
        r"^\s*(?:explain|describe)\s+(?:the\s+)?"
        r"(?:ending|themes?|story)\s+(?:of|in)\s+(?P<title>.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?P<title>.+?)\s+(?:ending|themes?|story)\s*$",
        re.IGNORECASE,
    ),
)

GENERIC_TITLES = {
    "a",
    "a film",
    "a movie",
    "an",
    "film",
    "films",
    "movie",
    "movies",
    "the",
    "the film",
    "the movie",
}


@dataclass(frozen=True)
class TitleMatch:
    record: dict[str, Any]
    extracted_title: str
    matched_title: str
    score: float
    match_type: str
    intent: LookupIntent
    question_type: EntityQuestion


def extract_title_candidate(query: str) -> tuple[str, LookupIntent] | None:
    for pattern in DIRECT_PATTERNS:
        match = pattern.match(query)
        if match:
            return _clean_candidate(match.group("title")), "details"
    for pattern in SEMANTIC_PATTERNS:
        match = pattern.match(query)
        if match:
            return _clean_candidate(match.group("title")), "semantic"
    return None


def resolve_title_query(
    query: str,
    *,
    repository: StructuredRecordRepository,
    aliases_path: Path,
    min_score: float,
    ambiguity_margin: float,
) -> TitleMatch | None:
    extracted = extract_title_candidate(query)
    exact_only = extracted is None
    if extracted is None:
        # A bare title such as "Project Hail Mary" is a useful entity lookup,
        # but arbitrary semantic questions must not be fuzzy-forced to a movie.
        candidate, intent = _clean_candidate(query), "details"
    else:
        candidate, intent = extracted
    normalized_candidate = normalize_title(candidate)
    if not normalized_candidate or normalized_candidate in GENERIC_TITLES:
        return None

    try:
        records = repository.list_records()
    except FileNotFoundError:
        if exact_only:
            return None
        raise
    query_year = _query_year(query)
    if query_year is not None:
        records = [record for record in records if record.get("year") == query_year]
    if not records:
        return None

    configured_aliases = load_title_aliases(aliases_path)
    targets = _target_records(records)
    aliases_by_id: dict[str, list[tuple[str, str, str]]] = {}
    for record in records:
        imdb_id = str(record.get("imdb_id") or "")
        values = []
        for field in ("title", "original_title"):
            value = str(record.get(field) or "").strip()
            if value:
                values.append((normalize_title(value), value, field))
        for value in record.get("akas") or []:
            title = str(value).strip()
            if title:
                values.append((normalize_title(title), title, "aka"))
        aliases_by_id[imdb_id] = _unique_aliases(values)

    for alias, target in configured_aliases.items():
        record = targets.get(normalize_title(target)) or targets.get(target)
        if record is None:
            continue
        imdb_id = str(record.get("imdb_id") or "")
        aliases_by_id.setdefault(imdb_id, []).append(
            (normalize_title(alias), alias, "configured_alias")
        )

    scored = []
    for record in records:
        imdb_id = str(record.get("imdb_id") or "")
        choices = aliases_by_id.get(imdb_id, [])
        if not choices:
            continue
        best = max(
            choices,
            key=lambda value: fuzz.WRatio(normalized_candidate, value[0]),
        )
        score = float(fuzz.WRatio(normalized_candidate, best[0]))
        scored.append((score, _votes(record), record, best))
    if exact_only:
        scored = [value for value in scored if value[0] == 100.0]
    scored.sort(key=lambda value: (-value[0], -value[1], value[2].get("title", "")))
    if not scored or scored[0][0] < min_score:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < ambiguity_margin:
        return None

    score, _vote_count, record, matched = scored[0]
    match_type = (
        matched[2]
        if normalize_title(matched[1]) != normalized_candidate
        or matched[2] == "configured_alias"
        else "exact"
    )
    return TitleMatch(
        record=record,
        extracted_title=candidate,
        matched_title=matched[1],
        score=round(score, 2),
        match_type=match_type,
        intent=intent,
        question_type=_entity_question(query),
    )


def build_entity_response(
    query: str,
    match: TitleMatch,
    *,
    stage: str,
) -> dict[str, Any]:
    record = match.record
    title = str(record.get("title") or match.matched_title)
    year = record.get("year")
    heading = f"{title} ({year})" if year else title
    answer = _entity_answer(
        record,
        heading=heading,
        question_type=match.question_type,
    )

    item = _public_record(record)
    return {
        "type": "structured_answer",
        "path": "structured",
        "operation": "entity_lookup",
        "query": query,
        "answer": answer,
        "count": 1,
        "items": [item],
        "groups": {},
        "sources": [{"n": 1, "title": title, "url": item["url"]}],
        "lookup": {
            "stage": stage,
            "extracted_title": match.extracted_title,
            "matched_title": match.matched_title,
            "canonical_title": title,
            "imdb_id": record.get("imdb_id"),
            "score": match.score,
            "match_type": match.match_type,
            "question_type": match.question_type,
        },
        "router": {
            "reason": "title_entity_lookup",
            "vector_db_used": False,
            "openai_used": False,
        },
    }


def rewrite_query_with_title(query: str, match: TitleMatch) -> str:
    canonical = str(match.record.get("title") or match.matched_title)
    rewritten = re.sub(
        re.escape(match.extracted_title),
        canonical,
        query,
        count=1,
        flags=re.IGNORECASE,
    )
    return rewritten if rewritten != query else f"{query} {canonical}"


def load_title_aliases(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    values = payload.get("aliases", payload)
    if not isinstance(values, dict):
        return {}
    return {
        str(alias).strip(): str(target).strip()
        for alias, target in values.items()
        if str(alias).strip() and isinstance(target, str) and target.strip()
    }


def normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def _clean_candidate(value: str) -> str:
    candidate = re.sub(r"\(\s*(?:19|20)\d{2}\s*\)", "", value)
    candidate = re.sub(r"\b(?:movie|film)\b\s*$", "", candidate, flags=re.IGNORECASE)
    return candidate.strip(" \t\n\r\"'?.!")


def _target_records(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output = {}
    for record in records:
        imdb_id = str(record.get("imdb_id") or "")
        if imdb_id:
            output[imdb_id] = record
        for field in ("title", "original_title"):
            title = str(record.get(field) or "").strip()
            if title:
                output[normalize_title(title)] = record
    return output


def _unique_aliases(
    values: list[tuple[str, str, str]],
) -> list[tuple[str, str, str]]:
    output = []
    seen = set()
    for normalized, display, source in values:
        if normalized and normalized not in seen:
            output.append((normalized, display, source))
            seen.add(normalized)
    return output


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    source_urls = record.get("source_urls") or {}
    return {
        "imdb_id": record.get("imdb_id"),
        "title": record.get("title"),
        "original_title": record.get("original_title"),
        "akas": record.get("akas", []),
        "release_date": record.get("release_date"),
        "year": record.get("year"),
        "runtime": record.get("runtime"),
        "genres": record.get("genres", []),
        "imdb_rating": record.get("imdb_rating"),
        "imdb_votes": record.get("imdb_votes"),
        "directors": record.get("directors", []),
        "writers": record.get("writers", []),
        "top_cast": record.get("top_cast", []),
        "overview": record.get("overview"),
        "url": source_urls.get("imdb") or record.get("url", ""),
        "source_urls": source_urls,
    }


def _query_year(query: str) -> int | None:
    match = re.search(r"\b(19\d{2}|20\d{2})\b", query)
    return int(match.group(1)) if match else None


def _votes(record: dict[str, Any]) -> int:
    value = record.get("imdb_votes")
    return int(value) if isinstance(value, int | float) else 0


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _entity_question(query: str) -> EntityQuestion:
    normalized = " ".join(query.lower().split())
    if re.search(r"\bwho\s+directed\b|\b(?:its|the)\s+director\b", normalized):
        return "director"
    if re.search(r"\bwho\s+wrote\b|\b(?:its|the)\s+writers?\b", normalized):
        return "writer"
    if re.search(
        r"\bwho\s+(?:is|was|acted|acts|starred|stars)\s+in\b"
        r"|\b(?:cast|actors?)\b",
        normalized,
    ):
        return "cast"
    if re.search(r"\bruntime\b|\bhow\s+long\b", normalized):
        return "runtime"
    if re.search(r"\brating\b|\brated\b", normalized):
        return "rating"
    if re.search(r"\bwhen\b.*\breleased\b|\brelease\s+date\b", normalized):
        return "release_date"
    if re.search(r"\b(?:explain|tell\s+me)\s+more\b|\bmore\s+details\b", normalized):
        return "more"
    if re.search(r"\b(?:plot|overview|synopsis)\b|\bwhat(?:'s|\s+is)\b.*\babout\b", normalized):
        return "overview"
    return "details"


def _entity_answer(
    record: dict[str, Any],
    *,
    heading: str,
    question_type: EntityQuestion,
) -> str:
    directors = _strings(record.get("directors"))
    writers = _strings(record.get("writers"))
    cast = [
        str(item.get("name") or "").strip()
        for item in (record.get("top_cast") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    cast = list(dict.fromkeys(cast))
    overview = str(record.get("overview") or "").strip()
    runtime = record.get("runtime")
    rating = record.get("imdb_rating")
    votes = record.get("imdb_votes")
    release_date = record.get("release_date")
    genres = _strings(record.get("genres"))

    if question_type == "director":
        fact = (
            f"{heading} was directed by {', '.join(directors)}."
            if directors
            else f"The current dataset does not list a director for {heading}."
        )
        return f"{fact} [1]"
    if question_type == "writer":
        fact = (
            f"{heading} was written by {', '.join(writers)}."
            if writers
            else f"The current dataset does not list a writer for {heading}."
        )
        return f"{fact} [1]"
    if question_type == "cast":
        fact = (
            f"The listed cast for {heading} includes {', '.join(cast[:8])}."
            if cast
            else f"The current dataset does not list cast members for {heading}."
        )
        return f"{fact} [1]"
    if question_type == "runtime":
        fact = (
            f"{heading} has a runtime of {runtime} minutes."
            if runtime
            else f"The current dataset does not list a runtime for {heading}."
        )
        return f"{fact} [1]"
    if question_type == "rating":
        if rating is None:
            fact = f"The current dataset does not list an IMDb rating for {heading}."
        elif votes is not None:
            fact = (
                f"{heading} has an IMDb rating of {rating}/10 "
                f"from {int(votes):,} votes."
            )
        else:
            fact = f"{heading} has an IMDb rating of {rating}/10."
        return f"{fact} [1]"
    if question_type == "release_date":
        fact = (
            f"{heading} was released on {release_date}."
            if release_date
            else f"The current dataset does not list a release date for {heading}."
        )
        return f"{fact} [1]"
    if question_type == "overview":
        fact = (
            f"{heading} is about this: {overview}"
            if overview
            else f"The current dataset does not include a plot overview for {heading}."
        )
        return f"{fact} [1]"

    sentences = []
    if overview:
        sentences.append(f"{heading} is about this: {overview}")
    else:
        sentences.append(f"{heading} is included in the current movie dataset.")
    if directors:
        sentences.append(f"It was directed by {', '.join(directors)}.")
    metadata = []
    if release_date and runtime:
        metadata.append(f"was released on {release_date} and runs {runtime} minutes")
    elif release_date:
        metadata.append(f"was released on {release_date}")
    elif runtime:
        metadata.append(f"runs {runtime} minutes")
    if genres:
        metadata.append(f"is categorized as {', '.join(genres)}")
    if metadata:
        sentences.append(f"It {_natural_join(metadata)}.")
    if rating is not None and votes is not None:
        sentences.append(
            f"Its IMDb rating is {rating}/10 from {int(votes):,} votes."
        )
    elif rating is not None:
        sentences.append(f"Its IMDb rating is {rating}/10.")
    answer = f"{' '.join(sentences)} [1]"
    if question_type == "more":
        answer += (
            " That is the full plot detail available in the current dataset; "
            "I don’t have a longer synopsis in these sources."
        )
    return answer


def _natural_join(values: list[str]) -> str:
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"
