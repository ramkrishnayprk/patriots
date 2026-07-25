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
    redis_url: str
    base_url: str
    allowed_domain: str
    max_pages: int
    min_delay_seconds: float
    max_delay_seconds: float
    request_timeout_seconds: float
    render_javascript: bool
    checkpoint_interval: int
    data_dir: Path
    chunk_size: int
    chunk_overlap: int
    min_chunk: int
    chunk_strategy: str
    embed_prefix: bool
    embedding_model_name: str
    embedding_model_path: Path
    embedding_dimension: int
    embedding_normalize: bool
    embedding_batch_size: int
    embedding_device: str
    embedding_distance_metric: str
    embedding_query_instruction: str
    embedding_passage_prefix: str
    user_agent: str

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            scraperapi_key=os.getenv("SCRAPERAPI_KEY", "").strip(),
            scraperapi_endpoint=os.getenv(
                "SCRAPERAPI_ENDPOINT", "https://api.scraperapi.com"
            ).strip(),
            redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0").strip(),
            base_url=os.getenv("BASE_URL", "https://degrees.ucumberlands.edu/").strip(),
            allowed_domain=os.getenv("ALLOWED_DOMAIN", "degrees.ucumberlands.edu").strip().lower(),
            max_pages=_integer("MAX_PAGES", 300),
            min_delay_seconds=_number("MIN_DELAY_SECONDS", 0.75),
            max_delay_seconds=_number("MAX_DELAY_SECONDS", 1.75),
            request_timeout_seconds=_number("REQUEST_TIMEOUT_SECONDS", 90, minimum=1),
            render_javascript=_boolean("RENDER_JAVASCRIPT", False),
            checkpoint_interval=_integer("CHECKPOINT_INTERVAL", 10),
            data_dir=Path(os.getenv("DATA_DIR", "/app/data")),
            chunk_size=_integer("CHUNK_SIZE", 1200, minimum=100),
            chunk_overlap=_integer("CHUNK_OVERLAP", 200, minimum=0),
            min_chunk=_integer("MIN_CHUNK", 150, minimum=1),
            chunk_strategy=os.getenv("CHUNK_STRATEGY", "section_aware").strip().lower(),
            embed_prefix=_boolean("EMBED_PREFIX", True),
            embedding_model_name=os.getenv(
                "EMBEDDING_MODEL_NAME", "BAAI/bge-small-en-v1.5"
            ).strip(),
            embedding_model_path=Path(os.getenv("EMBEDDING_MODEL_PATH", "/models")),
            embedding_dimension=_integer("EMBEDDING_DIMENSION", 384),
            embedding_normalize=_boolean("EMBEDDING_NORMALIZE", True),
            embedding_batch_size=_integer("EMBEDDING_BATCH_SIZE", 64),
            embedding_device=os.getenv("EMBEDDING_DEVICE", "auto").strip().lower(),
            embedding_distance_metric=os.getenv("EMBEDDING_DISTANCE_METRIC", "cosine")
            .strip()
            .lower(),
            embedding_query_instruction=os.getenv(
                "EMBEDDING_QUERY_INSTRUCTION",
                "Represent this sentence for searching relevant passages: ",
            ).strip(),
            embedding_passage_prefix=os.getenv("EMBEDDING_PASSAGE_PREFIX", ""),
            user_agent=os.getenv(
                "USER_AGENT",
                "UC-Program-RAG-Research-Bot/1.0 "
                "(educational indexing of public university program pages)",
            ).strip(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.max_delay_seconds < self.min_delay_seconds:
            raise ValueError(
                "MAX_DELAY_SECONDS must be greater than or equal to MIN_DELAY_SECONDS."
            )
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE.")
        if self.min_chunk > self.chunk_size:
            raise ValueError("MIN_CHUNK must be smaller than or equal to CHUNK_SIZE.")
        if self.chunk_strategy not in {"recursive", "section_aware"}:
            raise ValueError("CHUNK_STRATEGY must be recursive or section_aware.")
        if not self.embedding_model_name:
            raise ValueError("EMBEDDING_MODEL_NAME cannot be empty.")
        if self.embedding_device not in {"auto", "cpu"}:
            raise ValueError("EMBEDDING_DEVICE must be auto or cpu for FastEmbed.")
        if self.embedding_distance_metric != "cosine":
            raise ValueError("EMBEDDING_DISTANCE_METRIC must be cosine.")
        if not self.allowed_domain:
            raise ValueError("ALLOWED_DOMAIN cannot be empty.")

    def require_scraperapi_key(self) -> None:
        if not self.scraperapi_key:
            raise ValueError("SCRAPERAPI_KEY is missing. Add it to the root .env file.")
