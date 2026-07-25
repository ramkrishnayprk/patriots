from __future__ import annotations

from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from imdb_scraper.config import Settings


class FetchError(RuntimeError):
    """A target page could not be fetched or validated."""


@dataclass(frozen=True)
class FetchResult:
    html: str
    status_code: int
    content_type: str


def create_session() -> requests.Session:
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=2,
        status_forcelist=(408, 425, 429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=4,
        pool_maxsize=4,
    )
    session = requests.Session()
    session.mount("https://", adapter)
    session.headers.update(
        {
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": "Authorized-IMDb-Metadata-Research/1.0",
        }
    )
    return session


class ScraperApiClient:
    def __init__(
        self,
        settings: Settings,
        session: requests.Session | None = None,
    ):
        self.settings = settings
        self.session = session or create_session()

    def fetch(self, target_url: str) -> FetchResult:
        params = {
            "url": target_url,
            "render": str(self.settings.render_javascript).lower(),
            "premium": str(self.settings.premium).lower(),
            "country_code": self.settings.country_code,
        }
        headers = {"x-sapi-api_key": self.settings.scraperapi_key}
        try:
            response = self.session.get(
                self.settings.scraperapi_endpoint,
                params=params,
                headers=headers,
                timeout=self.settings.request_timeout_seconds,
            )
        except requests.RequestException as exc:
            raise FetchError(f"ScraperAPI request failed: {exc}") from exc

        if response.status_code != 200:
            raise FetchError(
                f"ScraperAPI returned HTTP {response.status_code}."
            )
        html = response.text
        if len(html.strip()) < 500:
            raise FetchError("ScraperAPI returned an unexpectedly small page.")
        lowered = html.lower()
        if "captcha" in lowered or "access denied" in lowered:
            raise FetchError("The returned page appears to be a block page.")
        return FetchResult(
            html=html,
            status_code=response.status_code,
            content_type=response.headers.get("Content-Type", ""),
        )
