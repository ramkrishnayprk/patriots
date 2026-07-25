from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _integer(name: str, default: int, minimum: int = 1) -> int:
    value = int(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


def _number(name: str, default: float, minimum: float = 0) -> float:
    value = float(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


@dataclass(frozen=True)
class Settings:
    scraperapi_key: str
    scraperapi_endpoint: str
    seeds_path: Path
    output_dir: Path
    max_titles: int
    request_timeout_seconds: float
    min_delay_seconds: float
    max_delay_seconds: float
    render_javascript: bool
    premium: bool
    country_code: str
    authorized: bool

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            scraperapi_key=os.getenv("SCRAPERAPI_KEY", "").strip(),
            scraperapi_endpoint=os.getenv(
                "SCRAPERAPI_ENDPOINT", "https://api.scraperapi.com"
            ).strip(),
            seeds_path=Path(
                os.getenv(
                    "IMDB_SCRAPER_SEEDS_PATH",
                    "/app/config/seed_urls.txt",
                )
            ),
            output_dir=Path(
                os.getenv("IMDB_SCRAPER_OUTPUT_DIR", "/app/data")
            ),
            max_titles=_integer("IMDB_SCRAPER_MAX_TITLES", 25),
            request_timeout_seconds=_number(
                "IMDB_SCRAPER_TIMEOUT_SECONDS", 90, minimum=1
            ),
            min_delay_seconds=_number(
                "IMDB_SCRAPER_MIN_DELAY_SECONDS", 2, minimum=0
            ),
            max_delay_seconds=_number(
                "IMDB_SCRAPER_MAX_DELAY_SECONDS", 5, minimum=0
            ),
            render_javascript=_boolean("IMDB_SCRAPER_RENDER", False),
            premium=_boolean("IMDB_SCRAPER_PREMIUM", False),
            country_code=os.getenv(
                "IMDB_SCRAPER_COUNTRY_CODE", "us"
            ).strip().lower(),
            authorized=_boolean("IMDB_SCRAPER_AUTHORIZED", False),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.scraperapi_endpoint.startswith("https://"):
            raise ValueError("SCRAPERAPI_ENDPOINT must use HTTPS.")
        if self.max_delay_seconds < self.min_delay_seconds:
            raise ValueError(
                "IMDB_SCRAPER_MAX_DELAY_SECONDS must be greater than or equal "
                "to IMDB_SCRAPER_MIN_DELAY_SECONDS."
            )
        if len(self.country_code) != 2:
            raise ValueError("IMDB_SCRAPER_COUNTRY_CODE must be a two-letter code.")

    def require_live_access(self) -> None:
        if not self.scraperapi_key:
            raise ValueError("SCRAPERAPI_KEY is missing from the environment.")
        if not self.authorized:
            raise ValueError(
                "Live execution is disabled. Set IMDB_SCRAPER_AUTHORIZED=true "
                "only after obtaining permission for the supplied URLs."
            )
