from pathlib import Path

from flask import Blueprint, jsonify, request
from redis.exceptions import RedisError
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.config import Settings
from app.embedding.model import is_model_installed
from app.embedding.pipeline import EmbeddingOptions, ingest_run
from app.queue import redis_connection, scrape_queue
from app.rechunking.pipeline import RechunkOptions, rechunk_run

api = Blueprint("api", __name__, url_prefix="/api/v1")


@api.get("/health")
def health():
    try:
        redis_connection().ping()
        redis_status = "ok"
        status_code = 200
    except RedisError:
        redis_status = "unavailable"
        status_code = 503
    return (
        jsonify(
            {
                "status": "ok" if status_code == 200 else "degraded",
                "redis": redis_status,
            }
        ),
        status_code,
    )


@api.post("/scrapes")
def create_scrape():
    settings = Settings.from_env()
    try:
        settings.require_scraperapi_key()
        queue = scrape_queue()
        job = queue.enqueue(
            "app.scraper.pipeline.run_scrape_job",
            job_timeout="6h",
            result_ttl=86_400,
            failure_ttl=604_800,
        )
    except ValueError as exc:
        return (
            jsonify({"error": {"code": "configuration_error", "message": str(exc)}}),
            503,
        )
    except RedisError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "queue_unavailable",
                        "message": "The scrape queue is unavailable.",
                    }
                }
            ),
            503,
        )

    return (
        jsonify(
            {
                "data": {
                    "id": job.id,
                    "status": "queued",
                    "status_url": f"/api/v1/scrapes/{job.id}",
                }
            }
        ),
        202,
    )


@api.get("/scrapes/<string:job_id>")
def get_scrape(job_id: str):
    try:
        connection = redis_connection()
        job = Job.fetch(job_id, connection=connection)
        status = job.get_status(refresh=True)
    except NoSuchJobError:
        return (
            jsonify({"error": {"code": "job_not_found", "message": "Scrape job not found."}}),
            404,
        )
    except RedisError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "queue_unavailable",
                        "message": "The scrape queue is unavailable.",
                    }
                }
            ),
            503,
        )

    status_value = status.value if hasattr(status, "value") else str(status)
    data = {
        "id": job.id,
        "status": status_value,
        "progress": job.meta.get("progress", {}),
        "created_at": _isoformat(job.created_at),
        "started_at": _isoformat(job.started_at),
        "ended_at": _isoformat(job.ended_at),
    }
    if job.is_finished:
        data["result"] = job.result
    elif job.is_failed:
        data["error"] = {
            "code": "scrape_failed",
            "message": "The scrape failed. Check the worker logs for details.",
        }
    return jsonify({"data": data})


@api.get("/runs/<string:run_id>/chunks/rebuild")
def rebuild_chunks(run_id: str):
    """Run a local, network-free re-chunk against one run's documents.jsonl."""
    try:
        settings = Settings.from_env()
        options = RechunkOptions(
            chunk_size=_query_integer("chunk_size", settings.chunk_size),
            overlap=_query_integer("overlap", settings.chunk_overlap, minimum=0),
            min_chunk=_query_integer("min_chunk", settings.min_chunk),
            strategy=request.args.get("strategy", settings.chunk_strategy).strip().lower(),
            embed_prefix=_query_boolean("embed_prefix", settings.embed_prefix),
        )
        report = rechunk_run(
            data_dir=Path(settings.data_dir),
            run_id=run_id,
            options=options,
        )
    except FileNotFoundError as exc:
        return (
            jsonify({"error": {"code": "documents_not_found", "message": str(exc)}}),
            404,
        )
    except ValueError as exc:
        return (
            jsonify({"error": {"code": "invalid_rechunk_request", "message": str(exc)}}),
            400,
        )
    except OSError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "rechunk_failed",
                        "message": "The chunk output could not be written.",
                    }
                }
            ),
            500,
        )

    response = jsonify({"data": report})
    response.headers["Cache-Control"] = "no-store"
    return response


@api.get("/runs/<string:run_id>/vectors/rebuild")
def rebuild_vectors(run_id: str):
    """Populate the local dense and sparse indexes from chunks.jsonl."""
    try:
        settings = Settings.from_env()
        if not is_model_installed(settings.embedding_model_path, settings.embedding_model_name):
            return (
                jsonify(
                    {
                        "error": {
                            "code": "embedding_model_not_installed",
                            "message": (
                                f"Embedding model is not installed at "
                                f"{settings.embedding_model_path}. Run the "
                                "embedding-model-download Docker service first."
                            ),
                        }
                    }
                ),
                503,
            )
        report = ingest_run(
            data_dir=settings.data_dir,
            run_id=run_id,
            options=EmbeddingOptions(
                model_name=settings.embedding_model_name,
                model_path=settings.embedding_model_path,
                embed_dim=settings.embedding_dimension,
                normalize=settings.embedding_normalize,
                batch_size=settings.embedding_batch_size,
                device=settings.embedding_device,
                distance_metric=settings.embedding_distance_metric,
                query_instruction=settings.embedding_query_instruction,
                passage_prefix=settings.embedding_passage_prefix,
            ),
        )
    except FileNotFoundError as exc:
        return (
            jsonify({"error": {"code": "chunks_not_found", "message": str(exc)}}),
            404,
        )
    except ValueError as exc:
        return (
            jsonify({"error": {"code": "embedding_validation_failed", "message": str(exc)}}),
            422,
        )
    except OSError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "embedding_ingestion_failed",
                        "message": "The vector or sparse index could not be written.",
                    }
                }
            ),
            500,
        )

    response = jsonify({"data": report})
    response.headers["Cache-Control"] = "no-store"
    return response


def _isoformat(value):
    return value.isoformat() if value else None


def _query_integer(name: str, default: int, *, minimum: int = 1) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


def _query_boolean(name: str, default: bool) -> bool:
    raw = request.args.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false.")
