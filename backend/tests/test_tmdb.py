import json

import responses

from app.acquisition.tmdb import TmdbClient
from app.config import Settings


@responses.activate
def test_tmdb_client_joins_by_imdb_id_and_reuses_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("TMDB_API_KEY", "secret")
    settings = Settings.from_env()
    responses.get(
        "https://api.themoviedb.org/3/find/tt1234567",
        json={"movie_results": [{"id": 42}]},
        status=200,
    )
    responses.get(
        "https://api.themoviedb.org/3/movie/42",
        json={
            "id": 42,
            "imdb_id": "tt1234567",
            "title": "A Movie",
            "original_title": "A Movie",
            "overview": "A complete plot overview.",
            "release_date": "2026-05-01",
            "runtime": 100,
            "genres": [{"id": 18, "name": "Drama"}],
            "vote_average": 7.0,
            "tagline": "A tagline",
        },
        status=200,
    )
    client = TmdbClient(settings, cache_dir=tmp_path)

    first = client.enrich("tt1234567")
    second = client.enrich("tt1234567")

    assert first == second
    assert first["status"] == "matched"
    assert first["release_date"] == "2026-05-01"
    assert len(responses.calls) == 2
    assert json.loads((tmp_path / "tt1234567.json").read_text())["tmdb_id"] == 42
