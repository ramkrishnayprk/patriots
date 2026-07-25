import json
from pathlib import Path

import pytest

from app.structured.repository import JsonlMovieRepository
from app.structured.title_lookup import (
    build_entity_response,
    resolve_title_query,
    rewrite_query_with_title,
)


def _repository(tmp_path):
    records_path = tmp_path / "movies_2026.jsonl"
    records = [
        {
            "imdb_id": "tt1000001",
            "title": "Laggam Time",
            "original_title": "Laggam Time",
            "akas": ["Wedding Time"],
            "year": 2026,
            "release_date": "2026-05-15",
            "runtime": 124,
            "genres": ["Comedy", "Drama"],
            "directors": ["Example Director"],
            "writers": ["Example Writer"],
            "top_cast": [{"name": "Example Actor", "order": 1}],
            "imdb_rating": 9.6,
            "imdb_votes": 1084,
            "overview": "A family prepares for a wedding under unusual pressure.",
            "source_urls": {"imdb": "https://www.imdb.com/title/tt1000001/"},
        },
        {
            "imdb_id": "tt1000002",
            "title": "Tomorrow Signal",
            "original_title": "Tomorrow Signal",
            "year": 2026,
            "imdb_votes": 500,
        },
    ]
    records_path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    return JsonlMovieRepository(records_path)


def _resolve(query, repository, aliases_path, **overrides):
    return resolve_title_query(
        query,
        repository=repository,
        aliases_path=aliases_path,
        min_score=overrides.get("min_score", 86),
        ambiguity_margin=overrides.get("ambiguity_margin", 3),
    )


def test_exact_title_lookup_returns_grounded_structured_record(tmp_path):
    match = _resolve(
        "Show me details of Laggam Time",
        _repository(tmp_path),
        tmp_path / "missing-aliases.json",
    )

    assert match is not None
    assert match.intent == "details"
    assert match.question_type == "details"
    assert match.record["imdb_id"] == "tt1000001"
    assert match.match_type == "exact"

    response = build_entity_response(
        "Show me details of Laggam Time",
        match,
        stage="pre_retrieval",
    )
    assert response["operation"] == "entity_lookup"
    assert response["items"][0]["title"] == "Laggam Time"
    assert "9.6/10 from 1,084 votes" in response["answer"]
    assert "was released on 2026-05-15 and runs 124 minutes" in response["answer"]
    assert response["router"]["vector_db_used"] is False
    assert response["router"]["openai_used"] is False


def test_entity_answer_leads_with_requested_fact_and_omits_unasked_metadata(
    tmp_path,
):
    match = _resolve(
        "Who directed Laggam Time?",
        _repository(tmp_path),
        tmp_path / "missing-aliases.json",
    )

    assert match is not None
    assert match.question_type == "director"
    response = build_entity_response(
        "Who directed Laggam Time?",
        match,
        stage="pre_retrieval",
    )
    assert response["answer"].startswith(
        "Laggam Time (2026) was directed by Example Director."
    )
    assert "runtime" not in response["answer"].lower()
    assert "cast" not in response["answer"].lower()


@pytest.mark.parametrize(
    ("query", "question_type"),
    [
        ("Laggam Time explain", "details"),
        ("who acted in Laggam Time", "cast"),
        ("cast of Laggam Time", "cast"),
        ("Laggam Time", "details"),
    ],
)
def test_common_entity_phrasings_resolve_without_vector_search(
    query,
    question_type,
    tmp_path,
):
    match = _resolve(
        query,
        _repository(tmp_path),
        tmp_path / "missing-aliases.json",
    )

    assert match is not None
    assert match.record["title"] == "Laggam Time"
    assert match.question_type == question_type
    response = build_entity_response(query, match, stage="pre_retrieval")
    assert response["router"]["vector_db_used"] is False


def test_arbitrary_semantic_query_is_not_treated_as_bare_title(tmp_path):
    match = _resolve(
        "science fiction movie about the future",
        _repository(tmp_path),
        tmp_path / "missing-aliases.json",
    )

    assert match is None


def test_more_details_returns_available_overview_and_names_depth_limit(tmp_path):
    match = _resolve(
        "Tell me more about Laggam Time",
        _repository(tmp_path),
        tmp_path / "missing-aliases.json",
    )

    assert match is not None
    assert match.question_type == "more"
    response = build_entity_response(
        "Explain more",
        match,
        stage="pre_retrieval",
    )
    assert "A family prepares for a wedding" in response["answer"]
    assert "full plot detail available" in response["answer"]
    assert "Top cast" not in response["answer"]


def test_configured_alias_and_fuzzy_spelling_resolve_to_canonical_title(tmp_path):
    aliases_path = tmp_path / "aliases.json"
    aliases_path.write_text(
        json.dumps({"aliases": {"lagam time": "Laggam Time"}}),
        encoding="utf-8",
    )
    repository = _repository(tmp_path)

    alias_match = _resolve(
        "Tell me about Lagam Time",
        repository,
        aliases_path,
    )
    fuzzy_match = _resolve(
        "Show me details of Laggm Time",
        repository,
        aliases_path,
    )

    assert alias_match is not None
    assert alias_match.record["title"] == "Laggam Time"
    assert alias_match.match_type == "configured_alias"
    assert fuzzy_match is not None
    assert fuzzy_match.record["title"] == "Laggam Time"


def test_semantic_entity_query_is_rewritten_for_retrieval(tmp_path):
    match = _resolve(
        "Explain the ending of Laggm Time",
        _repository(tmp_path),
        tmp_path / "missing-aliases.json",
    )

    assert match is not None
    assert match.intent == "semantic"
    assert rewrite_query_with_title(
        "Explain the ending of Laggm Time",
        match,
    ) == "Explain the ending of Laggam Time"


def test_non_entity_query_is_not_forced_into_title_lookup(tmp_path):
    match = _resolve(
        "Movies about families preparing for weddings",
        _repository(tmp_path),
        tmp_path / "missing-aliases.json",
    )

    assert match is None


GOLDEN_QUERIES = json.loads(
    (
        Path(__file__).parents[1]
        / "config"
        / "golden_queries.json"
    ).read_text(encoding="utf-8")
)["entity_lookups"]


@pytest.mark.parametrize("case", GOLDEN_QUERIES, ids=lambda case: case["query"])
def test_golden_entity_queries(case, tmp_path):
    aliases_path = tmp_path / "aliases.json"
    aliases_path.write_text(
        json.dumps({"aliases": {"lagam time": "Laggam Time"}}),
        encoding="utf-8",
    )

    match = _resolve(case["query"], _repository(tmp_path), aliases_path)

    assert match is not None
    response = build_entity_response(case["query"], match, stage="pre_retrieval")
    assert response["path"] == case["expected_path"]
    assert response["operation"] == case["expected_operation"]
    assert response["items"][0]["title"] == case["expected_title"]
