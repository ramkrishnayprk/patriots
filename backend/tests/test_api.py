import importlib
import json
from uuid import UUID

from app import create_app


def test_create_acquisition_reports_missing_key(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "")
    client = create_app().test_client()

    response = client.post("/api/v1/acquisitions")

    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "configuration_error"


def test_unknown_route_is_json():
    client = create_app().test_client()

    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_session_create_list_and_delete(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = create_app().test_client()

    create_response = client.post("/api/v1/sessions")

    assert create_response.status_code == 201
    created = create_response.get_json()["data"]
    assert str(UUID(created["id"])) == created["id"]
    assert created["title"] == "New Session"
    assert created["messages"] == []
    assert create_response.headers["Location"] == f"/api/v1/sessions/{created['id']}"
    session_path = tmp_path / "sessions" / f"{created['id']}.json"
    assert session_path.exists()
    assert json.loads(session_path.read_text(encoding="utf-8")) == created

    list_response = client.get("/api/v1/sessions")

    assert list_response.status_code == 200
    assert list_response.get_json() == {"data": [created], "count": 1}

    delete_response = client.delete(f"/api/v1/sessions/{created['id']}")

    assert delete_response.status_code == 200
    assert delete_response.get_json()["data"] == {
        "id": created["id"],
        "deleted": True,
    }
    assert not session_path.exists()
    assert client.get("/api/v1/sessions").get_json() == {"data": [], "count": 0}


def test_delete_session_validates_id(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = create_app().test_client()

    response = client.delete("/api/v1/sessions/not-a-uuid")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_session_id"


def test_delete_missing_session_returns_not_found(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = create_app().test_client()

    response = client.delete("/api/v1/sessions/2e92dce3-8e37-4308-956f-628319d4f007")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "session_not_found"


def test_get_session_endpoint_returns_saved_document(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = create_app().test_client()
    created = client.post("/api/v1/sessions").get_json()["data"]

    response = client.get(f"/api/v1/sessions/{created['id']}")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.get_json()["data"] == created


def test_get_session_endpoint_validates_id_and_missing_session(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = create_app().test_client()

    invalid = client.get("/api/v1/sessions/not-a-uuid")
    missing = client.get("/api/v1/sessions/2e92dce3-8e37-4308-956f-628319d4f007")

    assert invalid.status_code == 400
    assert invalid.get_json()["error"]["code"] == "invalid_session_id"
    assert missing.status_code == 404
    assert missing.get_json()["error"]["code"] == "session_not_found"


def test_add_session_message_endpoint_appends_and_persists(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = create_app().test_client()
    created = client.post("/api/v1/sessions").get_json()["data"]
    session_path = tmp_path / "sessions" / f"{created['id']}.json"

    response = client.post(
        f"/api/v1/sessions/{created['id']}/messages",
        json={"role": "user", "content": "Who directed Oppenheimer?"},
    )

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["title"] == "Who directed Oppenheimer?"
    assert [m["role"] for m in data["messages"]] == ["user"]
    assert data["messages"][0]["content"] == "Who directed Oppenheimer?"
    assert json.loads(session_path.read_text(encoding="utf-8")) == data


def test_add_session_message_endpoint_validates_role_and_content(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = create_app().test_client()
    created = client.post("/api/v1/sessions").get_json()["data"]

    bad_role = client.post(
        f"/api/v1/sessions/{created['id']}/messages",
        json={"role": "system", "content": "hi"},
    )
    bad_content = client.post(
        f"/api/v1/sessions/{created['id']}/messages",
        json={"role": "user", "content": "   "},
    )
    missing_session = client.post(
        "/api/v1/sessions/2e92dce3-8e37-4308-956f-628319d4f007/messages",
        json={"role": "user", "content": "hi"},
    )

    assert bad_role.status_code == 400
    assert bad_role.get_json()["error"]["code"] == "invalid_role"
    assert bad_content.status_code == 400
    assert bad_content.get_json()["error"]["code"] == "invalid_content"
    assert missing_session.status_code == 404
    assert missing_session.get_json()["error"]["code"] == "session_not_found"


def test_get_rechunk_endpoint_rebuilds_existing_documents(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    run_dir = tmp_path / "runs" / "api-run"
    run_dir.mkdir(parents=True)
    document = {
        "id": "tt0000001",
        "imdb_id": "tt0000001",
        "title": "The Future Film",
        "url": "https://www.imdb.com/title/tt0000001/",
        "year": 2026,
        "genres": ["Science Fiction"],
        "quick_facts": {"runtime": 120, "imdb_rating": 7.4},
        "sections": [],
        "text": " ".join(
            ["A researcher receives a mysterious signal from tomorrow." for _ in range(12)]
        ),
    }
    (run_dir / "documents.jsonl").write_text(json.dumps(document) + "\n", encoding="utf-8")
    client = create_app().test_client()

    response = client.get(
        "/api/v1/runs/api-run/chunks/rebuild"
        "?strategy=recursive&chunk_size=200&overlap=20&min_chunk=80&embed_prefix=false"
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.get_json()["data"]["generation"] == 1
    assert response.get_json()["data"]["strategy"] == "recursive"
    assert (run_dir / "chunks.jsonl").exists()


def test_get_rechunk_endpoint_validates_query(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = create_app().test_client()

    response = client.get("/api/v1/runs/api-run/chunks/rebuild?embed_prefix=sometimes")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_rechunk_request"


def test_get_vector_endpoint_requires_downloaded_model(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("EMBEDDING_MODEL_PATH", str(tmp_path / "missing-model"))
    client = create_app().test_client()

    response = client.get("/api/v1/runs/api-run/vectors/rebuild")

    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "embedding_model_not_installed"


def test_search_endpoint_requires_json_query():
    client = create_app().test_client()

    response = client.post("/api/v1/runs/a-run/search", json={})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_query"


def test_search_endpoint_returns_pipeline_response(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    routes = importlib.import_module("app.api.routes")
    monkeypatch.setattr(routes, "is_model_installed", lambda *_args: True)
    monkeypatch.setattr(
        routes,
        "search_run",
        lambda **_kwargs: {
            "status": "ok",
            "query": {"original": "movie plot", "normalized": "movie plot"},
            "results": [{"rank": 1, "id": "chunk-1"}],
            "diagnostics": {"latency_ms": 1.0},
        },
    )
    client = create_app().test_client()

    response = client.post("/api/v1/runs/a-run/search", json={"query": "movie plot"})

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.get_json()["data"]["results"][0]["id"] == "chunk-1"


def test_answer_endpoint_requires_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    client = create_app().test_client()

    response = client.post("/api/v1/runs/a-run/answer", json={"query": "Tell me about a movie"})

    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "openai_configuration_error"


def test_answer_endpoint_runs_retrieval_then_generation(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    routes = importlib.import_module("app.api.routes")
    monkeypatch.setattr(routes, "is_model_installed", lambda *_args: True)
    retrieval = {
        "status": "ok",
        "query": {"original": "movie plot", "normalized": "movie plot"},
        "results": [{"rank": 1, "id": "chunk-1", "rerank_score": 4.0}],
        "diagnostics": {"latency_ms": 1.0},
    }
    monkeypatch.setattr(routes, "search_run", lambda **_kwargs: retrieval)
    monkeypatch.setattr(
        routes,
        "generate_answer",
        lambda *_args, **_kwargs: {
            "type": "answer",
            "answer": "A grounded answer. [1]",
            "sources": [
                {
                    "n": 1,
                    "title": "The Future Film",
                    "url": "https://www.imdb.com/title/tt0000001/",
                }
            ],
        },
    )
    client = create_app().test_client()

    response = client.post("/api/v1/runs/a-run/answer", json={"query": "movie plot"})

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.get_json()["data"]["type"] == "answer"


def test_answer_endpoint_routes_counts_to_structured_data_without_models_or_key(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    run_dir = tmp_path / "runs" / "catalog-run"
    run_dir.mkdir(parents=True)
    (run_dir / "movies_2026.jsonl").write_text(
        "".join(
            json.dumps(record) + "\n"
            for record in [
                {
                    "imdb_id": "tt1",
                    "title": "Future Signal",
                    "year": 2026,
                    "genres": ["Science Fiction"],
                },
                {
                    "imdb_id": "tt2",
                    "title": "Red Planet",
                    "year": 2026,
                    "genres": ["Science Fiction"],
                },
                {
                    "imdb_id": "tt3",
                    "title": "Quiet Room",
                    "year": 2026,
                    "genres": ["Drama"],
                },
            ]
        ),
        encoding="utf-8",
    )
    routes = importlib.import_module("app.api.routes")

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("semantic retrieval must not run for a structured query")

    monkeypatch.setattr(routes, "is_model_installed", fail_if_called)
    monkeypatch.setattr(routes, "search_run", fail_if_called)
    monkeypatch.setattr(routes, "generate_answer", fail_if_called)
    client = create_app().test_client()

    response = client.post(
        "/api/v1/runs/catalog-run/answer",
        json={"query": "How many science fiction movies?"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["path"] == "structured"
    assert data["operation"] == "count"
    assert data["count"] == 2
    assert data["router"]["vector_db_used"] is False
    assert data["router"]["openai_used"] is False


def test_answer_endpoint_rejects_invalid_mode():
    client = create_app().test_client()

    response = client.post(
        "/api/v1/runs/a-run/answer",
        json={"query": "List all movies", "mode": "sql"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_mode"


def test_answer_endpoint_rejects_missing_session(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    client = create_app().test_client()

    response = client.post(
        "/api/v1/runs/a-run/answer",
        json={
            "query": "movie plot",
            "session_id": "2e92dce3-8e37-4308-956f-628319d4f007",
        },
    )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "session_not_found"


def test_answer_endpoint_with_session_id_persists_turn_and_feeds_history(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    routes = importlib.import_module("app.api.routes")
    monkeypatch.setattr(routes, "is_model_installed", lambda *_args: True)
    retrieval = {
        "status": "ok",
        "query": {"original": "movie plot", "normalized": "movie plot"},
        "results": [{"rank": 1, "id": "chunk-1", "rerank_score": 4.0}],
        "diagnostics": {"latency_ms": 1.0},
    }
    monkeypatch.setattr(routes, "search_run", lambda **_kwargs: retrieval)

    received_history = []

    def fake_generate_answer(_retrieval, *, options, dry_run=False, history=None):
        received_history.append(history)
        return {
            "type": "answer",
            "answer": "A grounded answer. [1]",
            "sources": [
                {
                    "n": 1,
                    "title": "The Future Film",
                    "url": "https://www.imdb.com/title/tt0000001/",
                }
            ],
        }

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    client = create_app().test_client()
    session = client.post("/api/v1/sessions").get_json()["data"]

    first = client.post(
        "/api/v1/runs/a-run/answer",
        json={"query": "movie plot", "session_id": session["id"]},
    )

    assert first.status_code == 200
    first_data = first.get_json()["data"]
    assert first_data["session_id"] == session["id"]
    assert received_history[0] == []

    session_path = tmp_path / "sessions" / f"{session['id']}.json"
    saved = json.loads(session_path.read_text(encoding="utf-8"))
    assert [m["role"] for m in saved["messages"]] == ["user", "assistant"]
    assert saved["messages"][0]["content"] == "movie plot"
    assert saved["messages"][1]["content"] == "A grounded answer. [1]"
    assert saved["messages"][1]["sources"][0]["title"] == "The Future Film"
    assert saved["title"] == "movie plot"

    second = client.post(
        "/api/v1/runs/a-run/answer",
        json={"query": "who directed it", "session_id": session["id"]},
    )

    assert second.status_code == 200
    assert len(received_history[1]) == 2
    assert received_history[1][0]["content"] == "movie plot"
