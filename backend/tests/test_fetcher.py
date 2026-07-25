import responses

from app.config import Settings
from app.scraper.fetcher import ScraperApiClient


@responses.activate
def test_scraperapi_client_fetches_target_without_exposing_key(monkeypatch):
    monkeypatch.setenv("SCRAPERAPI_KEY", "secret-test-key")
    settings = Settings.from_env()
    responses.get(
        settings.scraperapi_endpoint,
        body="<html><body>This is a complete test response from ScraperAPI.</body></html>",
        status=200,
        content_type="text/html",
    )

    result = ScraperApiClient(settings).fetch("https://degrees.ucumberlands.edu/")

    assert result.status_code == 200
    assert "complete test response" in result.text
    assert "secret-test-key" not in result.text
