import importlib
import json
from types import SimpleNamespace
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


def test_session_messages_are_created_loaded_appended_and_renamed(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = create_app().test_client()
    first_messages = [
        {
            "role": "user",
            "content": "Best science fiction movies",
        },
        {
            "role": "assistant",
            "content": "Here are the top science fiction movies.",
            "sources": [
                {
                    "title": "Project Hail Mary",
                    "url": "https://www.imdb.com/title/tt12042730/",
                }
            ],
        },
    ]

    create_response = client.post(
        "/api/v1/sessions",
        json={
            "title": "Best science fiction movies",
            "model_id": "gpt-5",
            "messages": first_messages,
        },
    )

    assert create_response.status_code == 201
    created = create_response.get_json()["data"]
    assert created["model_id"] == "gpt-5"
    assert [message["role"] for message in created["messages"]] == [
        "user",
        "assistant",
    ]
    assert all(message["id"] for message in created["messages"])

    get_response = client.get(f"/api/v1/sessions/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.get_json()["data"] == created

    append_response = client.post(
        f"/api/v1/sessions/{created['id']}/messages",
        json={
            "messages": [
                {"role": "user", "content": "Only movies released in June"},
                {"role": "assistant", "content": "Here are the June releases."},
            ]
        },
    )
    assert append_response.status_code == 200
    assert len(append_response.get_json()["data"]["messages"]) == 4

    rename_response = client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={"title": "June science fiction"},
    )
    assert rename_response.status_code == 200
    assert rename_response.get_json()["data"]["title"] == "June science fiction"


def test_list_runs_returns_only_structured_ready_runs(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    ready = tmp_path / "runs" / "ready-run"
    ready.mkdir(parents=True)
    (ready / "movies_2026.jsonl").write_text("{}\n", encoding="utf-8")
    (ready / "bm25.sqlite3").write_text("", encoding="utf-8")
    (ready / "vector_db" / "chroma").mkdir(parents=True)
    (tmp_path / "runs" / "empty-run").mkdir()
    client = create_app().test_client()

    response = client.get("/api/v1/runs")

    assert response.status_code == 200
    assert response.get_json()["count"] == 1
    assert response.get_json()["data"][0]["id"] == "ready-run"
    assert response.get_json()["data"][0]["semantic_ready"] is True


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
    monkeypatch.setenv(
        "OPENAI_ALLOWED_MODELS",
        "gpt-4.1-mini,gpt-5.6-terra,gpt-5.6-luna",
    )
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
        "expand_weak_query",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("strong retrieval must not invoke query expansion")
        ),
    )
    generated_with = []

    def fake_generate_answer(*_args, **kwargs):
        generated_with.append(kwargs["options"].model)
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

    response = client.post(
        "/api/v1/runs/a-run/answer",
        json={"query": "movie plot", "model": "gpt-5.6-luna"},
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.get_json()["data"]["type"] == "answer"
    assert response.get_json()["data"]["router"]["generation_model"] == "gpt-5.6-luna"
    assert generated_with == ["gpt-5.6-luna"]


def test_answer_endpoint_rejects_model_outside_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_ALLOWED_MODELS", "gpt-4.1-mini,gpt-5.6-terra")
    client = create_app().test_client()

    response = client.post(
        "/api/v1/runs/a-run/answer",
        json={"query": "movie plot", "model": "unapproved-model"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "unsupported_model"


def test_answer_endpoint_resolves_exact_title_without_models_or_openai(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    run_dir = tmp_path / "runs" / "catalog-run"
    run_dir.mkdir(parents=True)
    (run_dir / "movies_2026.jsonl").write_text(
        json.dumps(
            {
                "imdb_id": "tt1000001",
                "title": "Laggam Time",
                "original_title": "Laggam Time",
                "year": 2026,
                "genres": ["Comedy", "Drama"],
                "imdb_rating": 9.6,
                "imdb_votes": 1084,
                "overview": "A family prepares for a wedding.",
                "source_urls": {
                    "imdb": "https://www.imdb.com/title/tt1000001/"
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    routes = importlib.import_module("app.api.routes")

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("entity lookup must not invoke semantic services")

    monkeypatch.setattr(routes, "is_model_installed", fail_if_called)
    monkeypatch.setattr(routes, "search_run", fail_if_called)
    monkeypatch.setattr(routes, "generate_answer", fail_if_called)
    client = create_app().test_client()

    response = client.post(
        "/api/v1/runs/catalog-run/answer",
        json={"query": "Show me details of Laggam Time"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["operation"] == "entity_lookup"
    assert data["items"][0]["imdb_id"] == "tt1000001"
    assert data["lookup"]["canonical_title"] == "Laggam Time"
    assert data["router"]["vector_db_used"] is False
    assert data["router"]["openai_used"] is False

    log_response = client.get("/api/v1/query-logs")
    assert log_response.status_code == 200
    log = log_response.get_json()["data"][0]
    assert log["query"] == "Show me details of Laggam Time"
    assert log["decision"] == "answered"
    assert log["operation"] == "entity_lookup"


def test_answer_endpoint_resolves_conversational_followup_from_history(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    run_dir = tmp_path / "runs" / "catalog-run"
    run_dir.mkdir(parents=True)
    (run_dir / "movies_2026.jsonl").write_text(
        json.dumps(
            {
                "imdb_id": "tt1000001",
                "title": "Laggam Time",
                "original_title": "Laggam Time",
                "year": 2026,
                "directors": ["Prajoth K Vennam"],
                "runtime": 128,
                "overview": "A wedding celebration descends into comic mayhem.",
                "source_urls": {
                    "imdb": "https://www.imdb.com/title/tt1000001/"
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    routes = importlib.import_module("app.api.routes")

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("resolved entity follow-up must not invoke semantic services")

    monkeypatch.setattr(routes, "is_model_installed", fail_if_called)
    monkeypatch.setattr(routes, "search_run", fail_if_called)
    monkeypatch.setattr(routes, "generate_answer", fail_if_called)
    client = create_app().test_client()

    response = client.post(
        "/api/v1/runs/catalog-run/answer",
        json={
            "query": "Explain more about the movie",
            "history": [
                {"role": "user", "content": "Tell me about Laggam Time"},
                {
                    "role": "assistant",
                    "content": "Laggam Time is a comedy.",
                    "sources": [
                        {
                            "title": "Laggam Time",
                            "url": "https://www.imdb.com/title/tt1000001/",
                        }
                    ],
                },
            ],
        },
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["operation"] == "entity_lookup"
    assert data["lookup"]["question_type"] == "more"
    assert data["conversation"] == {
        "reference_resolved": True,
        "strategy": "recent_single_source",
        "original_query": "Explain more about the movie",
        "rewritten_query": "Explain more about Laggam Time",
        "referenced_title": "Laggam Time",
    }
    assert "wedding celebration" in data["answer"]
    assert "full plot detail available" in data["answer"]

    log = client.get("/api/v1/query-logs?limit=1").get_json()["data"][0]
    assert log["conversation_rewrite"]["referenced_title"] == "Laggam Time"


def test_answer_endpoint_validates_conversation_history():
    client = create_app().test_client()

    response = client.post(
        "/api/v1/runs/catalog-run/answer",
        json={"query": "Tell me more", "history": "not-an-array"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_history"


def test_answer_endpoint_escalates_weak_semantic_title_query(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    run_dir = tmp_path / "runs" / "catalog-run"
    run_dir.mkdir(parents=True)
    (run_dir / "movies_2026.jsonl").write_text(
        json.dumps(
            {
                "imdb_id": "tt1000001",
                "title": "Laggam Time",
                "original_title": "Laggam Time",
                "year": 2026,
                "overview": "A family prepares for a wedding.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    routes = importlib.import_module("app.api.routes")
    monkeypatch.setattr(routes, "is_model_installed", lambda *_args: True)
    searched_queries = []

    def fake_search_run(**kwargs):
        searched_queries.append(kwargs["query"])
        rewritten = kwargs["query"] == "Explain the ending of Laggam Time"
        return {
            "status": "ok" if rewritten else "low_confidence",
            "query": {
                "original": kwargs["query"],
                "normalized": kwargs["query"].lower(),
            },
            "results": [
                {
                    "rank": 1,
                    "id": "chunk-1",
                    "score": 0.9 if rewritten else 0.01,
                    "rerank_score": 4.0 if rewritten else -10.0,
                }
            ],
            "diagnostics": {"latency_ms": 1.0},
        }

    monkeypatch.setattr(routes, "search_run", fake_search_run)
    monkeypatch.setattr(
        routes,
        "expand_weak_query",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError(
                "a successful deterministic title retry must not invoke the LLM"
            )
        ),
    )
    monkeypatch.setattr(
        routes,
        "generate_answer",
        lambda retrieval, **_kwargs: {
            "type": "answer",
            "answer": "A grounded explanation. [1]",
            "sources": [],
            "retrieval": {
                "status": retrieval["status"],
                "top_score": retrieval["results"][0]["score"],
                "top_rerank_score": retrieval["results"][0]["rerank_score"],
                "diagnostics": retrieval["diagnostics"],
            },
        },
    )
    client = create_app().test_client()

    response = client.post(
        "/api/v1/runs/catalog-run/answer",
        json={"query": "Explain the ending of Laggm Time"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert searched_queries == [
        "Explain the ending of Laggm Time",
        "Explain the ending of Laggam Time",
    ]
    assert data["lookup"]["stage"] == "escalation"
    assert (
        data["retrieval"]["diagnostics"]["escalation"][
            "deterministic_title_retry"
        ]["selected"]
        == "retry"
    )
    assert data["retrieval"]["status"] == "ok"
    log = client.get(
        "/api/v1/query-logs?triage_bucket=recall_miss_recovered"
    ).get_json()["data"][0]
    assert log["decision"] == "answered"
    assert (
        log["escalation"]["deterministic_title_retry"]["strategy"]
        == "fuzzy_title_rewrite"
    )


def test_answer_endpoint_uses_multi_query_and_hyde_only_after_weak_retrieval(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    routes = importlib.import_module("app.api.routes")
    monkeypatch.setattr(routes, "is_model_installed", lambda *_args: True)
    expanded = SimpleNamespace(
        variations=(
            "scientist receives signals from the future movie",
            "film plot with messages sent backward through time",
            "science fiction story about warnings from tomorrow",
        ),
        hypothetical_document=(
            "A science-fiction overview about a researcher receiving a "
            "warning sent backward through time."
        ),
    )
    expansion_calls = []

    def fake_expand(query, **_kwargs):
        expansion_calls.append(query)
        return expanded

    searched = []

    def fake_search_run(**kwargs):
        query = kwargs["query"]
        searched.append(
            {
                "query": query,
                "filters": kwargs["options"].enable_filters,
            }
        )
        is_original = query.startswith("Find a story")
        shared = {
            "rank": 1,
            "id": "future-0",
            "document_id": "future",
            "chunk_number": 0,
            "title": "Future Signal",
            "text": "A researcher receives a signal from tomorrow.",
            "url": "https://www.imdb.com/title/tt1/",
            "score": 0.01 if is_original else 0.95,
            "rerank_score": -10.0 if is_original else 5.0,
        }
        return {
            "status": "low_confidence" if is_original else "ok",
            "query": {"original": query, "normalized": query.lower()},
            "results": [shared],
            "diagnostics": {"latency_ms": 1.0},
        }

    monkeypatch.setattr(routes, "expand_weak_query", fake_expand)
    monkeypatch.setattr(routes, "search_run", fake_search_run)
    monkeypatch.setattr(
        routes,
        "generate_answer",
        lambda retrieval, **_kwargs: {
            "type": "answer",
            "answer": "Future Signal matches that description. [1]",
            "sources": [],
            "retrieval": {
                "status": retrieval["status"],
                "top_score": retrieval["results"][0]["score"],
                "top_rerank_score": retrieval["results"][0]["rerank_score"],
                "diagnostics": retrieval["diagnostics"],
            },
        },
    )
    client = create_app().test_client()

    query = "Find a story involving a scientist receiving messages from tomorrow"
    response = client.post(
        "/api/v1/runs/catalog-run/answer",
        json={"query": query},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert expansion_calls == [query]
    assert len(searched) == 5
    assert searched[-1]["query"] == expanded.hypothetical_document
    assert searched[-1]["filters"] is False
    assert data["retrieval"]["status"] == "ok"
    assert (
        data["retrieval"]["diagnostics"]["strategy"]
        == "multi_query_hyde_rrf"
    )
    escalation = data["retrieval"]["diagnostics"]["escalation"]
    assert escalation["selected"] == "multi_query_hyde_rrf"
    assert escalation["llm_expansion"]["variation_count"] == 3
    assert escalation["llm_expansion"]["hyde_used"] is True
    assert data["router"]["openai_retrieval_expansion_used"] is True

    log = client.get(
        "/api/v1/query-logs?triage_bucket=recall_miss_recovered"
    ).get_json()["data"][0]
    assert log["query"] == query
    assert log["escalation"]["selected"] == "multi_query_hyde_rrf"


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


def test_answer_endpoint_ranks_movies_without_models_or_openai(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("STRUCTURED_MIN_RATING_VOTES", "1000")
    run_dir = tmp_path / "runs" / "catalog-run"
    run_dir.mkdir(parents=True)
    (run_dir / "movies_2026.jsonl").write_text(
        "".join(
            json.dumps(record) + "\n"
            for record in [
                {
                    "imdb_id": "tt1",
                    "title": "Reliable Favorite",
                    "year": 2026,
                    "imdb_rating": 8.5,
                    "imdb_votes": 8_000,
                },
                {
                    "imdb_id": "tt2",
                    "title": "One Vote Wonder",
                    "year": 2026,
                    "imdb_rating": 10.0,
                    "imdb_votes": 1,
                },
            ]
        ),
        encoding="utf-8",
    )
    routes = importlib.import_module("app.api.routes")

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("semantic retrieval must not run for a ranking query")

    monkeypatch.setattr(routes, "is_model_installed", fail_if_called)
    monkeypatch.setattr(routes, "search_run", fail_if_called)
    monkeypatch.setattr(routes, "generate_answer", fail_if_called)
    client = create_app().test_client()

    response = client.post(
        "/api/v1/runs/catalog-run/answer",
        json={"query": "Top rated movies"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["path"] == "structured"
    assert data["operation"] == "rank"
    assert [item["title"] for item in data["items"]] == ["Reliable Favorite"]
    assert data["ranking"]["min_imdb_votes"] == 1000
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
