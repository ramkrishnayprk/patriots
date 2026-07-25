import json

from app import create_app


def test_create_scrape_reports_missing_key(monkeypatch):
    monkeypatch.setenv("SCRAPERAPI_KEY", "")
    client = create_app().test_client()

    response = client.post("/api/v1/scrapes")

    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "configuration_error"


def test_unknown_route_is_json():
    client = create_app().test_client()

    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_get_rechunk_endpoint_rebuilds_existing_documents(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    run_dir = tmp_path / "runs" / "api-run"
    run_dir.mkdir(parents=True)
    document = {
        "id": "document-1",
        "title": "Cybersecurity",
        "url": "https://example.edu/programs/cybersecurity/",
        "category": "Information Technology",
        "quick_facts": {"credit_hours": "30"},
        "sections": [],
        "text": " ".join(
            ["Students learn to protect reliable information systems." for _ in range(12)]
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
