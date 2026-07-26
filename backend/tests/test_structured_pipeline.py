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
        ("Paul Walker movies", "structured", "list"),
        ("Movies by Travis Knight", "structured", "list"),
        ("Top rated movies", "structured", "rank"),
        ("Top 10 movies", "structured", "rank"),
        ("Top 20 movies", "structured", "rank"),
        ("Highest rated movies", "structured", "rank"),
        ("Best 2026 movies", "structured", "rank"),
        ("Newest movies", "structured", "rank"),
        ("Longest movies", "structured", "rank"),
        ("Best movies of May", "structured", "rank"),
        ("Best movies of May or June", "structured", "rank"),
        ("Best science fiction movies", "structured", "rank"),
        ("Best action movies", "structured", "rank"),
        ("How many action movies?", "structured", "count"),
        ("How many 2026 releases?", "structured", "count"),
        ("2026 sci-fi movies", "structured", "list"),
        ("Movies released in June", "structured", "list"),
        ("What is the plot of The Future Film?", "semantic", None),
        ("What is Masters of the Universe about?", "semantic", None),
        ("Movies about revenge", "semantic", None),
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


def test_combined_director_genre_and_plural_rating_filter():
    decision = route_query(
        "Which sci-fi movies directed by Christopher Nolan have IMDb ratings above 8?"
    )

    assert decision.path == "structured"
    assert decision.operation == "list"
    assert decision.filters == {
        "genre": "Science Fiction",
        "min_imdb_rating": 8.0,
        "person_name": "christopher nolan",
        "person_role": "directors",
    }
    assert decision.topic_terms == ()


def test_combined_person_and_metadata_no_match_is_not_misleading(tmp_path):
    query = (
        "Which sci-fi movies directed by Christopher Nolan "
        "have IMDb ratings above 8?"
    )

    result = run_structured_query(
        query,
        repository=_repository(tmp_path),
        decision=route_query(query),
    )

    assert result["type"] == "not_in_sources"
    assert result["answer"] == (
        "No movies matched all requested filters for Christopher Nolan "
        "in this 2026 dataset."
    )


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


@pytest.mark.parametrize(
    ("query", "expected_id"),
    [
        ("Which movies star Morgan Vale?", "tt0000001"),
        ("Movies directed by Travis Knight", "tt0000003"),
        ("Movies written by Casey Script", "tt0000001"),
        ("Paul Walker movies", "tt0000004"),
    ],
)
def test_person_queries_search_the_requested_or_any_credit(
    tmp_path, query, expected_id
):
    repository = _repository(tmp_path)

    result = run_structured_query(
        query,
        repository=repository,
        decision=route_query(query),
    )

    assert result["count"] == 1
    assert result["items"][0]["imdb_id"] == expected_id
    assert result["router"]["vector_db_used"] is False


def test_unknown_person_returns_dataset_specific_no_match(tmp_path):
    repository = _repository(tmp_path)
    query = "Movies featuring Nobody Here"

    result = run_structured_query(
        query,
        repository=repository,
        decision=route_query(query),
    )

    assert result["type"] == "not_in_sources"
    assert result["count"] == 0
    assert result["answer"] == (
        "No movies featuring Nobody Here were found in this 2026 dataset."
    )


def test_top_rated_uses_vote_floor_and_honors_requested_limit(tmp_path):
    repository = _repository(tmp_path)
    query = "Top 2 rated movies"

    result = run_structured_query(
        query,
        repository=repository,
        decision=route_query(query),
        min_rating_votes=1_000,
    )

    assert result["operation"] == "rank"
    assert result["ranking"] == {
        "field": "imdb_rating",
        "direction": "desc",
        "requested_limit": 2,
        "returned": 2,
        "min_imdb_votes": 1000,
    }
    assert [item["imdb_id"] for item in result["items"]] == [
        "tt0000003",
        "tt0000004",
    ]
    assert "tt0000002" not in {item["imdb_id"] for item in result["items"]}
    assert result["answer"].startswith(
        "Here are the highest-rated matching movies with at least 1,000 IMDb votes:"
    )
    assert "\n\n1. " in result["answer"]
    assert "\n2. " in result["answer"]


@pytest.mark.parametrize(("query", "limit"), [("Top 10 movies", 10), ("Top 20 movies", 20)])
def test_plain_top_n_means_imdb_rating_ranking(query, limit):
    decision = route_query(query)

    assert decision.path == "structured"
    assert decision.operation == "rank"
    assert decision.sort_by == "imdb_rating"
    assert decision.limit == limit
    assert decision.topic_terms == ()


@pytest.mark.parametrize(
    ("query", "expected_ids"),
    [
        ("Newest movies", ["tt0000002", "tt0000004", "tt0000001"]),
        ("Longest movies", ["tt0000004", "tt0000003", "tt0000001"]),
        ("Movies released in June", ["tt0000001", "tt0000004"]),
        ("2026 sci-fi movies", ["tt0000001"]),
        ("Best movies of May", ["tt0000003"]),
        (
            "Best movies of May or June",
            ["tt0000003", "tt0000004", "tt0000001"],
        ),
        ("Best science fiction movies", ["tt0000001"]),
        ("Best action movies", ["tt0000004"]),
    ],
)
def test_ranking_and_metadata_filters(tmp_path, query, expected_ids):
    repository = _repository(tmp_path)

    result = run_structured_query(
        query,
        repository=repository,
        decision=route_query(query),
        default_rank_limit=3,
    )

    assert [item["imdb_id"] for item in result["items"]] == expected_ids


@pytest.mark.parametrize(
    ("query", "expected_count"),
    [
        ("How many action movies?", 1),
        ("How many 2026 releases?", 4),
    ],
)
def test_count_and_aggregate_queries(tmp_path, query, expected_count):
    repository = _repository(tmp_path)

    result = run_structured_query(
        query,
        repository=repository,
        decision=route_query(query),
    )

    assert result["operation"] == "count"
    assert result["count"] == expected_count


def test_broad_query_returns_groups(tmp_path):
    repository = _repository(tmp_path)
    query = "What movies are in the dataset?"

    result = run_structured_query(
        query,
        repository=repository,
        decision=route_query(query),
    )

    assert result["count"] == 4
    assert result["items"] == []
    assert result["groups"]["year"] == [{"value": 2026, "count": 4}]
    assert {"value": "Drama", "count": 2} in result["groups"]["genre"]


def _repository(tmp_path):
    path = tmp_path / "movies_2026.jsonl"
    records = [
        {
            "imdb_id": "tt0000001",
            "title": "The Future Film",
            "year": 2026,
            "release_date": "2026-06-15",
            "runtime": 120,
            "genres": ["Science Fiction", "Drama"],
            "imdb_rating": 7.4,
            "imdb_votes": 5_000,
            "directors": ["Alex North"],
            "writers": ["Casey Script"],
            "top_cast": [{"name": "Morgan Vale"}],
            "source_urls": {"imdb": "https://www.imdb.com/title/tt0000001/"},
        },
        {
            "imdb_id": "tt0000002",
            "title": "Quiet Rooms",
            "year": 2026,
            "release_date": "2026-07-01",
            "runtime": 95,
            "genres": ["Drama"],
            "imdb_rating": 10.0,
            "imdb_votes": 1,
            "directors": ["Paul East"],
            "writers": ["Jamie Walker"],
            "top_cast": [{"name": "Taylor Reed"}],
        },
        {
            "imdb_id": "tt0000003",
            "title": "Night House",
            "year": 2026,
            "release_date": "2026-05-20",
            "runtime": 140,
            "genres": ["Horror"],
            "imdb_rating": 8.1,
            "imdb_votes": 2_000,
            "directors": ["Travis Knight"],
            "writers": [],
            "top_cast": [],
        },
        {
            "imdb_id": "tt0000004",
            "title": "Fast Horizon",
            "year": 2026,
            "release_date": "2026-06-30",
            "runtime": 180,
            "genres": ["Action"],
            "imdb_rating": 7.9,
            "imdb_votes": 3_000,
            "directors": ["Riley West"],
            "writers": [],
            "top_cast": [{"name": "Paul Walker"}],
        },
    ]
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    return JsonlMovieRepository(path)
