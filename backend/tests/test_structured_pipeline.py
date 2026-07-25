import json

import pytest

from app.structured.normalization import normalize_movie_record
from app.structured.pipeline import route_query, run_structured_query
from app.structured.repository import JsonlMovieRepository


def test_movie_record_normalization():
    record = normalize_movie_record(
        {
            "id": "tt1",
            "title": "Film",
            "year": "2026",
            "runtime": "110",
            "genres": "Drama,Science Fiction",
            "imdb_rating": "7.4",
        }
    )

    assert record["imdb_id"] == "tt1"
    assert record["year"] == 2026
    assert record["runtime"] == 110
    assert record["genres"] == ["Drama", "Science Fiction"]
    assert record["imdb_rating"] == 7.4


@pytest.mark.parametrize(
    ("query", "path", "operation"),
    [
        ("List 2026 science fiction movies rated above 7", "structured", "list"),
        ("How many horror movies were released in 2026?", "structured", "count"),
        ("What movies are in the dataset?", "structured", "summary"),
        ("Which films star Morgan Vale?", "structured", "list"),
        ("What is the plot of The Future Film?", "semantic", None),
        ("Explain the ending of The Future Film", "semantic", None),
        ("Tell me about The Future Film", "semantic", None),
    ],
)
def test_router_separates_catalog_queries_from_plot_questions(query, path, operation):
    decision = route_query(query)

    assert decision.path == path
    assert decision.operation == operation


def test_mode_can_force_either_path():
    assert route_query("Tell me about Film", mode="structured").path == "structured"
    assert route_query("List all movies", mode="semantic").path == "semantic"


def test_jsonl_repository_filters_and_counts_without_vector_access(tmp_path):
    repository = _repository(tmp_path)
    query = "How many 2026 science fiction movies rated above 7?"

    result = run_structured_query(
        query,
        repository=repository,
        decision=route_query(query),
    )

    assert result["count"] == 1
    assert result["items"] == []
    assert result["filters"] == {
        "year": 2026,
        "genre": "Science Fiction",
        "min_imdb_rating": 7.0,
    }
    assert result["router"]["vector_db_used"] is False
    assert result["router"]["openai_used"] is False


def test_structured_title_director_and_cast_search(tmp_path):
    repository = _repository(tmp_path)
    query = "Which movies star Morgan Vale?"

    result = run_structured_query(
        query,
        repository=repository,
        decision=route_query(query),
    )

    assert result["count"] == 1
    assert result["items"][0]["imdb_id"] == "tt0000001"


def test_broad_query_returns_groups(tmp_path):
    repository = _repository(tmp_path)
    query = "What movies are in the dataset?"

    result = run_structured_query(
        query,
        repository=repository,
        decision=route_query(query),
    )

    assert result["count"] == 3
    assert result["items"] == []
    assert result["groups"]["year"] == [{"value": 2026, "count": 3}]
    assert {"value": "Drama", "count": 2} in result["groups"]["genre"]


def _repository(tmp_path):
    path = tmp_path / "movies_2026.jsonl"
    records = [
        {
            "imdb_id": "tt0000001",
            "title": "The Future Film",
            "year": 2026,
            "genres": ["Science Fiction", "Drama"],
            "imdb_rating": 7.4,
            "directors": ["Alex North"],
            "top_cast": [{"name": "Morgan Vale"}],
            "source_urls": {"imdb": "https://www.imdb.com/title/tt0000001/"},
        },
        {
            "imdb_id": "tt0000002",
            "title": "Quiet Rooms",
            "year": 2026,
            "genres": ["Drama"],
            "imdb_rating": 6.8,
            "directors": ["Jamie East"],
            "top_cast": [{"name": "Taylor Reed"}],
        },
        {
            "imdb_id": "tt0000003",
            "title": "Night House",
            "year": 2026,
            "genres": ["Horror"],
            "imdb_rating": None,
            "directors": ["Alex North"],
            "top_cast": [],
        },
    ]
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    return JsonlMovieRepository(path)
