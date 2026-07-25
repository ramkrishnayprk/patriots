import gzip
import json
from datetime import date

from app.acquisition.imdb import _rows, assemble_imdb_records
from app.acquisition.pipeline import acquire_movies


class FakeTmdb:
    def enrich(self, imdb_id):
        if imdb_id == "tt0000001":
            return {
                "status": "matched",
                "imdb_id": imdb_id,
                "tmdb_id": 101,
                "title": "The Future Film",
                "original_title": "The Future Film",
                "overview": (
                    "A researcher discovers a signal from tomorrow and must decide "
                    "whether changing the future will erase the present."
                ),
                "tagline": "Tomorrow is listening.",
                "release_date": "2026-03-15",
                "runtime": 121,
                "genres": ["Science Fiction", "Drama"],
                "tmdb_vote_average": 7.4,
            }
        return {"status": "no_match", "imdb_id": imdb_id}


def test_imdb_streaming_join_filters_before_resolving_people(tmp_path):
    paths = _datasets(tmp_path)

    records, stats = assemble_imdb_records(
        paths,
        year=2026,
        title_types=("movie",),
        include_adult=False,
        region_preference="US",
        top_cast_limit=10,
    )

    assert stats["imdb_candidates"] == 2
    assert [record["imdb_id"] for record in records] == ["tt0000001", "tt0000002"]
    first = records[0]
    assert first["title"] == "The Future Film"
    assert first["imdb_rating"] == 7.1
    assert first["directors"] == ["A. Director"]
    assert first["writers"] == ["W. Writer"]
    assert first["top_cast"][0]["name"] == "Lead Actor"
    assert first["genres"] == ["Drama", "Sci-Fi"]


def test_imdb_reader_accepts_fields_larger_than_python_default(tmp_path):
    path = tmp_path / "large.tsv.gz"
    large_value = "x" * 150_000
    with gzip.open(path, "wt", encoding="utf-8") as output:
        output.write("id\tvalue\n")
        output.write(f"one\t{large_value}\n")

    rows = list(_rows(path))

    assert rows == [{"id": "one", "value": large_value}]


def test_acquisition_emits_structured_and_semantic_contracts(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TMDB_API_KEY", "test-key")
    monkeypatch.setenv("MOVIE_WINDOW_START", "2026-01-01")

    result = acquire_movies(
        run_id="movie-run",
        today=date(2026, 7, 1),
        dataset_paths=_datasets(tmp_path / "fixtures"),
        tmdb_client=FakeTmdb(),
    )

    run_dir = tmp_path / "runs" / "movie-run"
    movies = _jsonl(run_dir / "movies_2026.jsonl")
    documents = _jsonl(run_dir / "documents.jsonl")
    chunks = _jsonl(run_dir / "movie_chunks.jsonl")
    compatibility_chunks = _jsonl(run_dir / "chunks.jsonl")
    report = json.loads((run_dir / "qa_report.json").read_text(encoding="utf-8"))

    assert result["movies"] == 2
    assert result["semantic_movies"] == 1
    assert len(movies) == 2
    assert len(documents) == 1
    assert chunks == compatibility_chunks
    assert chunks[0]["document_id"] == "tt0000001"
    assert movies[0]["release_date"] == "2026-03-15"
    assert movies[1]["window_status"] == "unverified"
    assert len(movies[0]["content_hash"]) == 64
    assert report["tmdb_no_match"] == 1
    assert report["no_overview"] == 1
    assert (run_dir / "movies_2026.csv").is_file()
    assert (run_dir / "missing_report.json").is_file()


def test_acquisition_hard_stops_at_configured_candidate_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TMDB_API_KEY", "test-key")
    monkeypatch.setenv("MOVIE_WINDOW_START", "2026-01-01")
    monkeypatch.setenv("MOVIE_MAX_CANDIDATES", "1")

    result = acquire_movies(
        run_id="limited-run",
        today=date(2026, 7, 1),
        dataset_paths=_datasets(tmp_path / "fixtures"),
        tmdb_client=FakeTmdb(),
    )

    assert result["movies"] == 1
    assert result["qa"]["imdb_candidates"] == 2
    assert result["qa"]["imdb_candidates_selected"] == 1
    assert result["qa"]["imdb_candidates_skipped_by_limit"] == 1


def _datasets(directory):
    directory.mkdir(parents=True, exist_ok=True)
    content = {
        "title.basics.tsv.gz": (
            "tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\t"
            "endYear\truntimeMinutes\tgenres\n"
            "tt0000001\tmovie\tFuture Film\tFuture Film\t0\t2026\t\\N\t120\tDrama,Sci-Fi\n"
            "tt0000002\tmovie\tMissing Film\tMissing Film\t0\t2026\t\\N\t95\tComedy\n"
            "tt0000003\tmovie\tAdult Film\tAdult Film\t1\t2026\t\\N\t90\tDrama\n"
            "tt0000004\ttvSeries\tSeries\tSeries\t0\t2026\t\\N\t45\tDrama\n"
        ),
        "title.ratings.tsv.gz": (
            "tconst\taverageRating\tnumVotes\n"
            "tt0000001\t7.1\t1500\n"
        ),
        "title.crew.tsv.gz": (
            "tconst\tdirectors\twriters\n"
            "tt0000001\tnm0000001\tnm0000002\n"
            "tt0000002\t\\N\t\\N\n"
        ),
        "title.principals.tsv.gz": (
            "tconst\tordering\tnconst\tcategory\tjob\tcharacters\n"
            'tt0000001\t1\tnm0000003\tactor\t\\N\t["Researcher"]\n'
        ),
        "name.basics.tsv.gz": (
            "nconst\tprimaryName\tbirthYear\tdeathYear\tprimaryProfession\tknownForTitles\n"
            "nm0000001\tA. Director\t\\N\t\\N\tdirector\ttt0000001\n"
            "nm0000002\tW. Writer\t\\N\t\\N\twriter\ttt0000001\n"
            "nm0000003\tLead Actor\t\\N\t\\N\tactor\ttt0000001\n"
        ),
        "title.akas.tsv.gz": (
            "titleId\tordering\ttitle\tregion\tlanguage\ttypes\tattributes\tisOriginalTitle\n"
            "tt0000001\t1\tThe Future Film\tUS\ten\t\\N\t\\N\t0\n"
        ),
    }
    paths = {}
    for name, value in content.items():
        path = directory / name
        with gzip.open(path, "wt", encoding="utf-8") as output:
            output.write(value)
        paths[name] = path
    return paths


def _jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
