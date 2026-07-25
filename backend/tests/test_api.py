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
