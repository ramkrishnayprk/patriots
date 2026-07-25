import logging
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import Settings

logger = logging.getLogger(__name__)


class FetchError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class FetchResult:
    text: str
    content_type: str
    status_code: int


class ScraperApiClient:
    def __init__(self, settings: Settings):
        settings.require_scraperapi_key()
        self.settings = settings
        self.session = self._create_session(settings.user_agent)

    @staticmethod
    def _create_session(user_agent: str) -> requests.Session:
        retry_strategy = Retry(
            total=5,
            connect=5,
            read=5,
            status=5,
            backoff_factor=2,
            status_forcelist=(408, 425, 429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10,
        )
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        return session

    def fetch(self, target_url: str, *, render: bool = False) -> FetchResult:
        params = {
            "api_key": self.settings.scraperapi_key,
            "url": target_url,
            "render": str(render).lower(),
        }
        try:
            response = self.session.get(
                self.settings.scraperapi_endpoint,
                params=params,
                timeout=self.settings.request_timeout_seconds,
            )
        except requests.RequestException as exc:
            # Do not log the request object: its URL contains the API key.
            logger.warning(
                "ScraperAPI network failure | target=%s | error_type=%s",
                target_url,
                type(exc).__name__,
            )
            raise FetchError(f"Network failure while fetching {target_url}.") from exc

        if response.status_code != 200:
            logger.error(
                "ScraperAPI request failed | status=%s | target=%s",
                response.status_code,
                target_url,
            )
            raise FetchError(
                f"ScraperAPI returned HTTP {response.status_code} for {target_url}.",
                response.status_code,
            )

        content_type = response.headers.get("Content-Type", "").lower()
        if len(response.text.strip()) < 50:
            raise FetchError(f"ScraperAPI returned an empty response for {target_url}.")
        return FetchResult(
            text=response.text,
            content_type=content_type,
            status_code=response.status_code,
        )
