import os
from dataclasses import dataclass
from datetime import date
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


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in os.getenv(name, default).split(",") if value.strip())


@dataclass(frozen=True)
class Settings:
    tmdb_api_key: str
    tmdb_base_url: str
    tmdb_rate_limit: int
    tmdb_rate_window_seconds: float
    tmdb_transient_cache_hours: float
    imdb_dataset_base_url: str
    movie_window_start: date
    movie_title_types: tuple[str, ...]
    movie_include_adult: bool
    movie_region_preference: str
    movie_top_cast_limit: int
    movie_max_candidates: int
    enable_wikipedia: bool
    request_timeout_seconds: float
    download_chunk_bytes: int
    user_agent: str
    redis_url: str
    data_dir: Path
    openai_api_key: str
    openai_model: str
    openai_allowed_models: tuple[str, ...]
    openai_timeout_seconds: float
    openai_max_output_tokens: int
    generation_min_rerank_score: float
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
    reranker_model_name: str
    retrieval_top_k_dense: int
    retrieval_top_k_sparse: int
    retrieval_rrf_k: int
    retrieval_rerank_top_n: int
    retrieval_final_k: int
    retrieval_confidence_threshold: float
    retrieval_max_per_document: int
    retrieval_max_query_chars: int
    retrieval_enable_filters: bool
    structured_backend: str
    structured_records_filename: str
    structured_max_list_items: int
    structured_min_rating_votes: int
    structured_default_rank_limit: int
    title_lookup_min_score: float
    title_lookup_ambiguity_margin: float
    title_aliases_path: Path
    query_expansion_enabled: bool
    query_expansion_model: str
    query_expansion_variations: int
    query_expansion_hyde_enabled: bool
    query_expansion_max_output_tokens: int
    query_expansion_rrf_k: int

    @classmethod
    def from_env(cls) -> "Settings":
        openai_model = os.getenv("OPENAI_MODEL", "gpt-5.6-terra").strip()
        try:
            window_start = date.fromisoformat(
                os.getenv("MOVIE_WINDOW_START", "2026-01-01").strip()
            )
        except ValueError as exc:
            raise ValueError("MOVIE_WINDOW_START must use YYYY-MM-DD.") from exc

        settings = cls(
            tmdb_api_key=os.getenv("TMDB_API_KEY", "").strip(),
            tmdb_base_url=os.getenv(
                "TMDB_BASE_URL", "https://api.themoviedb.org/3"
            ).strip().rstrip("/"),
            tmdb_rate_limit=_integer("TMDB_RATE_LIMIT", 37),
            tmdb_rate_window_seconds=_number(
                "TMDB_RATE_WINDOW_SECONDS", 10, minimum=0.1
            ),
            tmdb_transient_cache_hours=_number(
                "TMDB_TRANSIENT_CACHE_HOURS", 24, minimum=0
            ),
            imdb_dataset_base_url=os.getenv(
                "IMDB_DATASET_BASE_URL", "https://datasets.imdbws.com"
            ).strip().rstrip("/"),
            movie_window_start=window_start,
            movie_title_types=_csv("MOVIE_TITLE_TYPES", "movie"),
            movie_include_adult=_boolean("MOVIE_INCLUDE_ADULT", False),
            movie_region_preference=os.getenv(
                "MOVIE_REGION_PREFERENCE", "US"
            ).strip().upper(),
            movie_top_cast_limit=_integer("MOVIE_TOP_CAST_LIMIT", 10),
            movie_max_candidates=_integer("MOVIE_MAX_CANDIDATES", 2_500),
            enable_wikipedia=_boolean("ENABLE_WIKIPEDIA", False),
            request_timeout_seconds=_number("REQUEST_TIMEOUT_SECONDS", 90, minimum=1),
            download_chunk_bytes=_integer("DOWNLOAD_CHUNK_BYTES", 1_048_576),
            user_agent=os.getenv(
                "USER_AGENT",
                "Movie-RAG-Research-Pipeline/1.0 (private educational project)",
            ).strip(),
            redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0").strip(),
            data_dir=Path(os.getenv("DATA_DIR", "/app/data")),
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_model=openai_model,
            openai_allowed_models=_csv(
                "OPENAI_ALLOWED_MODELS",
                f"{openai_model},gpt-5.6-terra,gpt-5.6-luna",
            ),
            openai_timeout_seconds=_number("OPENAI_TIMEOUT_SECONDS", 30, minimum=1),
            openai_max_output_tokens=_integer("OPENAI_MAX_OUTPUT_TOKENS", 600),
            generation_min_rerank_score=_number(
                "GENERATION_MIN_RERANK_SCORE", -4.5, minimum=-100
            ),
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
            embedding_distance_metric=os.getenv(
                "EMBEDDING_DISTANCE_METRIC", "cosine"
            ).strip().lower(),
            embedding_query_instruction=os.getenv(
                "EMBEDDING_QUERY_INSTRUCTION",
                "Represent this sentence for searching relevant passages: ",
            ).strip(),
            embedding_passage_prefix=os.getenv("EMBEDDING_PASSAGE_PREFIX", ""),
            reranker_model_name=os.getenv(
                "RERANKER_MODEL_NAME", "Xenova/ms-marco-MiniLM-L-6-v2"
            ).strip(),
            retrieval_top_k_dense=_integer("RETRIEVAL_TOP_K_DENSE", 20),
            retrieval_top_k_sparse=_integer("RETRIEVAL_TOP_K_SPARSE", 20),
            retrieval_rrf_k=_integer("RETRIEVAL_RRF_K", 60),
            retrieval_rerank_top_n=_integer("RETRIEVAL_RERANK_TOP_N", 30),
            retrieval_final_k=_integer("RETRIEVAL_FINAL_K", 5),
            retrieval_confidence_threshold=_number(
                "RETRIEVAL_CONFIDENCE_THRESHOLD", 0.01
            ),
            retrieval_max_per_document=_integer("RETRIEVAL_MAX_PER_DOCUMENT", 2),
            retrieval_max_query_chars=_integer("RETRIEVAL_MAX_QUERY_CHARS", 1000),
            retrieval_enable_filters=_boolean("RETRIEVAL_ENABLE_FILTERS", True),
            structured_backend=os.getenv("STRUCTURED_BACKEND", "jsonl").strip().lower(),
            structured_records_filename=os.getenv(
                "STRUCTURED_RECORDS_FILENAME", "movies_2026.jsonl"
            ).strip(),
            structured_max_list_items=_integer("STRUCTURED_MAX_LIST_ITEMS", 50),
            structured_min_rating_votes=_integer(
                "STRUCTURED_MIN_RATING_VOTES", 1_000, minimum=0
            ),
            structured_default_rank_limit=_integer(
                "STRUCTURED_DEFAULT_RANK_LIMIT", 10
            ),
            title_lookup_min_score=_number("TITLE_LOOKUP_MIN_SCORE", 86),
            title_lookup_ambiguity_margin=_number(
                "TITLE_LOOKUP_AMBIGUITY_MARGIN", 3
            ),
            title_aliases_path=Path(
                os.getenv("TITLE_ALIASES_PATH", "/app/config/title_aliases.json")
            ),
            query_expansion_enabled=_boolean("QUERY_EXPANSION_ENABLED", True),
            query_expansion_model=os.getenv(
                "QUERY_EXPANSION_MODEL",
                os.getenv("OPENAI_MODEL", "gpt-5.6-terra"),
            ).strip(),
            query_expansion_variations=_integer("QUERY_EXPANSION_VARIATIONS", 3),
            query_expansion_hyde_enabled=_boolean(
                "QUERY_EXPANSION_HYDE_ENABLED", True
            ),
            query_expansion_max_output_tokens=_integer(
                "QUERY_EXPANSION_MAX_OUTPUT_TOKENS", 500
            ),
            query_expansion_rrf_k=_integer("QUERY_EXPANSION_RRF_K", 60),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.tmdb_base_url.startswith("https://"):
            raise ValueError("TMDB_BASE_URL must be an HTTPS URL.")
        if not self.imdb_dataset_base_url.startswith("https://"):
            raise ValueError("IMDB_DATASET_BASE_URL must be an HTTPS URL.")
        if not self.movie_title_types:
            raise ValueError("MOVIE_TITLE_TYPES cannot be empty.")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE.")
        if self.min_chunk > self.chunk_size:
            raise ValueError("MIN_CHUNK must be smaller than or equal to CHUNK_SIZE.")
        if self.chunk_strategy not in {"recursive", "section_aware"}:
            raise ValueError("CHUNK_STRATEGY must be recursive or section_aware.")
        if not self.embedding_model_name or not self.reranker_model_name:
            raise ValueError("Embedding and reranker model names cannot be empty.")
        if not self.openai_model:
            raise ValueError("OPENAI_MODEL cannot be empty.")
        if not self.openai_allowed_models:
            raise ValueError("OPENAI_ALLOWED_MODELS cannot be empty.")
        if self.openai_model not in self.openai_allowed_models:
            raise ValueError("OPENAI_MODEL must be included in OPENAI_ALLOWED_MODELS.")
        if self.embedding_device not in {"auto", "cpu"}:
            raise ValueError("EMBEDDING_DEVICE must be auto or cpu for FastEmbed.")
        if self.embedding_distance_metric != "cosine":
            raise ValueError("EMBEDDING_DISTANCE_METRIC must be cosine.")
        if self.retrieval_confidence_threshold > 1:
            raise ValueError("RETRIEVAL_CONFIDENCE_THRESHOLD cannot exceed 1.")
        if self.generation_min_rerank_score > 100:
            raise ValueError("GENERATION_MIN_RERANK_SCORE cannot exceed 100.")
        if self.title_lookup_min_score > 100:
            raise ValueError("TITLE_LOOKUP_MIN_SCORE cannot exceed 100.")
        if self.title_lookup_ambiguity_margin > 100:
            raise ValueError("TITLE_LOOKUP_AMBIGUITY_MARGIN cannot exceed 100.")
        if not self.query_expansion_model:
            raise ValueError("QUERY_EXPANSION_MODEL cannot be empty.")
        if not 3 <= self.query_expansion_variations <= 4:
            raise ValueError("QUERY_EXPANSION_VARIATIONS must be 3 or 4.")
        if self.structured_backend not in {"jsonl"}:
            raise ValueError("STRUCTURED_BACKEND must be jsonl.")
        if (
            not self.structured_records_filename
            or Path(self.structured_records_filename).name
            != self.structured_records_filename
        ):
            raise ValueError("STRUCTURED_RECORDS_FILENAME must be a plain filename.")

    def require_tmdb_api_key(self) -> None:
        if not self.tmdb_api_key:
            raise ValueError("TMDB_API_KEY is missing. Add it to the root .env file.")

    def require_openai_api_key(self) -> None:
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is missing. Add it to the root .env file.")
