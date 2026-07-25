import sqlite3
from pathlib import Path

from flask import Blueprint, jsonify, request
from redis.exceptions import RedisError
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.config import Settings
from app.embedding.model import is_model_installed
from app.embedding.pipeline import EmbeddingOptions, ingest_run
from app.generation.pipeline import (
    GenerationOptions,
    GenerationProviderError,
    generate_answer,
)
from app.queue import acquisition_queue, redis_connection
from app.rechunking.pipeline import RechunkOptions, rechunk_run
from app.retrieval.pipeline import RetrievalOptions, search_run
from app.sessions.store import (
    InvalidSessionIdError,
    JsonFileSessionStore,
    SessionNotFoundError,
    SessionStorageError,
)
from app.structured.pipeline import route_query, run_structured_query
from app.structured.repository import create_structured_repository

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


@api.post("/acquisitions")
def create_acquisition():
    try:
        settings = Settings.from_env()
        settings.require_tmdb_api_key()
        queue = acquisition_queue()
        job = queue.enqueue(
            "app.acquisition.pipeline.run_acquisition_job",
            job_timeout="24h",
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
                        "message": "The acquisition queue is unavailable.",
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
                    "status_url": f"/api/v1/acquisitions/{job.id}",
                }
            }
        ),
        202,
    )


@api.get("/acquisitions/<string:job_id>")
def get_acquisition(job_id: str):
    try:
        connection = redis_connection()
        job = Job.fetch(job_id, connection=connection)
        status = job.get_status(refresh=True)
    except NoSuchJobError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "job_not_found",
                        "message": "Movie acquisition job not found.",
                    }
                }
            ),
            404,
        )
    except RedisError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "queue_unavailable",
                        "message": "The acquisition queue is unavailable.",
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
            "code": "acquisition_failed",
            "message": "Movie acquisition failed. Check the worker logs for details.",
        }
    return jsonify({"data": data})


@api.post("/sessions")
def create_session():
    try:
        session = _session_store().create()
    except SessionStorageError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "session_storage_error",
                        "message": "The session could not be saved.",
                    }
                }
            ),
            500,
        )

    response = jsonify({"data": session})
    response.status_code = 201
    response.headers["Location"] = f"/api/v1/sessions/{session['id']}"
    response.headers["Cache-Control"] = "no-store"
    return response


@api.get("/sessions")
def list_sessions():
    try:
        sessions = _session_store().list_all()
    except SessionStorageError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "session_storage_error",
                        "message": "The sessions could not be read.",
                    }
                }
            ),
            500,
        )

    response = jsonify({"data": sessions, "count": len(sessions)})
    response.headers["Cache-Control"] = "no-store"
    return response


@api.get("/sessions/<string:session_id>")
def get_session(session_id: str):
    try:
        session = _session_store().get(session_id)
    except InvalidSessionIdError as exc:
        return (
            jsonify({"error": {"code": "invalid_session_id", "message": str(exc)}}),
            400,
        )
    except SessionNotFoundError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "session_not_found",
                        "message": "Session not found.",
                    }
                }
            ),
            404,
        )
    except SessionStorageError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "session_storage_error",
                        "message": "The session could not be read.",
                    }
                }
            ),
            500,
        )

    response = jsonify({"data": session})
    response.headers["Cache-Control"] = "no-store"
    return response


@api.post("/sessions/<string:session_id>/messages")
def add_session_message(session_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return (
            jsonify(
                {
                    "error": {
                        "code": "invalid_json",
                        "message": "Request body must be a JSON object.",
                    }
                }
            ),
            400,
        )
    role = payload.get("role")
    if role not in {"user", "assistant"}:
        return (
            jsonify(
                {
                    "error": {
                        "code": "invalid_role",
                        "message": "role must be 'user' or 'assistant'.",
                    }
                }
            ),
            400,
        )
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        return (
            jsonify(
                {
                    "error": {
                        "code": "invalid_content",
                        "message": "content must be a non-empty string.",
                    }
                }
            ),
            400,
        )

    try:
        session = _session_store().append_message(session_id, role, content)
    except InvalidSessionIdError as exc:
        return (
            jsonify({"error": {"code": "invalid_session_id", "message": str(exc)}}),
            400,
        )
    except SessionNotFoundError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "session_not_found",
                        "message": "Session not found.",
                    }
                }
            ),
            404,
        )
    except SessionStorageError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "session_storage_error",
                        "message": "The message could not be saved.",
                    }
                }
            ),
            500,
        )

    response = jsonify({"data": session})
    response.status_code = 201
    response.headers["Cache-Control"] = "no-store"
    return response


@api.delete("/sessions/<string:session_id>")
def delete_session(session_id: str):
    try:
        _session_store().delete(session_id)
    except InvalidSessionIdError as exc:
        return (
            jsonify({"error": {"code": "invalid_session_id", "message": str(exc)}}),
            400,
        )
    except SessionNotFoundError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "session_not_found",
                        "message": "Session not found.",
                    }
                }
            ),
            404,
        )
    except SessionStorageError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "session_storage_error",
                        "message": "The session could not be deleted.",
                    }
                }
            ),
            500,
        )

    response = jsonify({"data": {"id": session_id, "deleted": True}})
    response.headers["Cache-Control"] = "no-store"
    return response


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


@api.post("/runs/<string:run_id>/search")
def search_vectors(run_id: str):
    """Run hybrid dense/sparse retrieval and cross-encoder reranking."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return (
            jsonify(
                {
                    "error": {
                        "code": "invalid_json",
                        "message": "Request body must be a JSON object.",
                    }
                }
            ),
            400,
        )
    query = payload.get("query")
    if not isinstance(query, str):
        return (
            jsonify(
                {
                    "error": {
                        "code": "invalid_query",
                        "message": "query must be a string.",
                    }
                }
            ),
            400,
        )

    try:
        settings = Settings.from_env()
        missing_models = [
            name
            for name in (settings.embedding_model_name, settings.reranker_model_name)
            if not is_model_installed(settings.embedding_model_path, name)
        ]
        if missing_models:
            return (
                jsonify(
                    {
                        "error": {
                            "code": "retrieval_model_not_installed",
                            "message": (
                                "Required retrieval model(s) are not installed: "
                                f"{', '.join(missing_models)}. Run "
                                "`docker compose --profile model run --rm "
                                "embedding-model-download` first."
                            ),
                        }
                    }
                ),
                503,
            )
        result = search_run(
            data_dir=settings.data_dir,
            run_id=run_id,
            query=query,
            options=_retrieval_options(settings),
        )
    except FileNotFoundError as exc:
        return (
            jsonify({"error": {"code": "retrieval_index_not_found", "message": str(exc)}}),
            404,
        )
    except ValueError as exc:
        return (
            jsonify({"error": {"code": "retrieval_validation_failed", "message": str(exc)}}),
            422,
        )
    except (OSError, sqlite3.Error):
        return (
            jsonify(
                {
                    "error": {
                        "code": "retrieval_failed",
                        "message": "The retrieval indexes could not be read.",
                    }
                }
            ),
            500,
        )

    response = jsonify({"data": result})
    response.headers["Cache-Control"] = "no-store"
    return response


@api.post("/runs/<string:run_id>/answer")
def answer_query(run_id: str):
    """Route catalog questions or retrieve movie evidence for a cited answer."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return (
            jsonify(
                {
                    "error": {
                        "code": "invalid_json",
                        "message": "Request body must be a JSON object.",
                    }
                }
            ),
            400,
        )
    query = payload.get("query")
    if not isinstance(query, str):
        return (
            jsonify(
                {
                    "error": {
                        "code": "invalid_query",
                        "message": "query must be a string.",
                    }
                }
            ),
            400,
        )
    dry_run = payload.get("dry_run", False)
    if not isinstance(dry_run, bool):
        return (
            jsonify(
                {
                    "error": {
                        "code": "invalid_dry_run",
                        "message": "dry_run must be a boolean.",
                    }
                }
            ),
            400,
        )
    mode = payload.get("mode", "auto")
    if mode not in {"auto", "structured", "semantic"}:
        return (
            jsonify(
                {
                    "error": {
                        "code": "invalid_mode",
                        "message": "mode must be auto, structured, or semantic.",
                    }
                }
            ),
            400,
        )
    session_id = payload.get("session_id")
    if session_id is not None and not isinstance(session_id, str):
        return (
            jsonify(
                {
                    "error": {
                        "code": "invalid_session_id",
                        "message": "session_id must be a string.",
                    }
                }
            ),
            400,
        )

    session = None
    if session_id is not None:
        try:
            session = _session_store().get(session_id)
        except InvalidSessionIdError as exc:
            return (
                jsonify({"error": {"code": "invalid_session_id", "message": str(exc)}}),
                400,
            )
        except SessionNotFoundError:
            return (
                jsonify(
                    {
                        "error": {
                            "code": "session_not_found",
                            "message": "Session not found.",
                        }
                    }
                ),
                404,
            )
        except SessionStorageError:
            return (
                jsonify(
                    {
                        "error": {
                            "code": "session_storage_error",
                            "message": "The session could not be read.",
                        }
                    }
                ),
                500,
            )

    try:
        settings = Settings.from_env()
        decision = route_query(query, mode=mode)
        if decision.path == "structured":
            repository = create_structured_repository(
                backend=settings.structured_backend,
                records_path=(
                    settings.data_dir
                    / "runs"
                    / run_id
                    / settings.structured_records_filename
                ),
            )
            try:
                result = run_structured_query(
                    query,
                    repository=repository,
                    decision=decision,
                    max_list_items=settings.structured_max_list_items,
                )
            except FileNotFoundError as exc:
                return (
                    jsonify(
                        {
                            "error": {
                                "code": "structured_records_not_found",
                                "message": str(exc),
                            }
                        }
                    ),
                    404,
                )
            if session_id is not None:
                try:
                    _session_store().append_turn(
                        session_id,
                        user_content=query,
                        assistant_content=result.get("answer", ""),
                        assistant_extra={"type": result.get("type"), "path": "structured"},
                    )
                except (InvalidSessionIdError, SessionNotFoundError, SessionStorageError):
                    return (
                        jsonify(
                            {
                                "error": {
                                    "code": "session_storage_error",
                                    "message": "The answer was generated but the session could not be saved.",
                                }
                            }
                        ),
                        500,
                    )
                result["session_id"] = session_id
            response = jsonify({"data": result})
            response.headers["Cache-Control"] = "no-store"
            return response

        if not dry_run:
            try:
                settings.require_openai_api_key()
            except ValueError as exc:
                return (
                    jsonify(
                        {
                            "error": {
                                "code": "openai_configuration_error",
                                "message": str(exc),
                            }
                        }
                    ),
                    503,
                )

        missing_models = [
            name
            for name in (settings.embedding_model_name, settings.reranker_model_name)
            if not is_model_installed(settings.embedding_model_path, name)
        ]
        if missing_models:
            return (
                jsonify(
                    {
                        "error": {
                            "code": "retrieval_model_not_installed",
                            "message": (
                                "Required retrieval model(s) are not installed: "
                                f"{', '.join(missing_models)}. Run "
                                "`docker compose --profile model run --rm "
                                "embedding-model-download` first."
                            ),
                        }
                    }
                ),
                503,
            )

        retrieval = search_run(
            data_dir=settings.data_dir,
            run_id=run_id,
            query=query,
            options=_retrieval_options(settings),
        )
        result = generate_answer(
            retrieval,
            options=GenerationOptions(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                timeout_seconds=settings.openai_timeout_seconds,
                max_output_tokens=settings.openai_max_output_tokens,
                min_rerank_score=settings.generation_min_rerank_score,
            ),
            dry_run=dry_run,
            history=session["messages"] if session is not None else None,
        )
        result["path"] = "semantic"
        result["router"] = {
            "reason": decision.reason,
            "vector_db_used": True,
        }
        if session_id is not None and not dry_run:
            try:
                _session_store().append_turn(
                    session_id,
                    user_content=query,
                    assistant_content=result.get("answer", ""),
                    assistant_extra={"type": result.get("type"), "path": "semantic", "sources": result.get("sources", [])},
                )
            except (InvalidSessionIdError, SessionNotFoundError, SessionStorageError):
                return (
                    jsonify(
                        {
                            "error": {
                                "code": "session_storage_error",
                                "message": "The answer was generated but the session could not be saved.",
                            }
                        }
                    ),
                    500,
                )
            result["session_id"] = session_id
    except GenerationProviderError as exc:
        return (
            jsonify({"error": {"code": exc.code, "message": str(exc)}}),
            exc.status_code,
        )
    except FileNotFoundError as exc:
        return (
            jsonify({"error": {"code": "retrieval_index_not_found", "message": str(exc)}}),
            404,
        )
    except ValueError as exc:
        return (
            jsonify({"error": {"code": "answer_validation_failed", "message": str(exc)}}),
            422,
        )
    except (OSError, sqlite3.Error):
        return (
            jsonify(
                {
                    "error": {
                        "code": "answer_pipeline_failed",
                        "message": "The answer pipeline could not read its indexes.",
                    }
                }
            ),
            500,
        )

    response = jsonify({"data": result})
    response.headers["Cache-Control"] = "no-store"
    return response


def _isoformat(value):
    return value.isoformat() if value else None


def _session_store() -> JsonFileSessionStore:
    settings = Settings.from_env()
    return JsonFileSessionStore(Path(settings.data_dir) / "sessions")


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


def _retrieval_options(settings: Settings) -> RetrievalOptions:
    return RetrievalOptions(
        model_name=settings.embedding_model_name,
        reranker_model_name=settings.reranker_model_name,
        model_path=settings.embedding_model_path,
        embed_dim=settings.embedding_dimension,
        normalize=settings.embedding_normalize,
        device=settings.embedding_device,
        query_instruction=settings.embedding_query_instruction,
        passage_prefix=settings.embedding_passage_prefix,
        top_k_dense=settings.retrieval_top_k_dense,
        top_k_sparse=settings.retrieval_top_k_sparse,
        rrf_k=settings.retrieval_rrf_k,
        rerank_top_n=settings.retrieval_rerank_top_n,
        final_k=settings.retrieval_final_k,
        confidence_threshold=settings.retrieval_confidence_threshold,
        max_per_document=settings.retrieval_max_per_document,
        max_query_chars=settings.retrieval_max_query_chars,
        enable_filters=settings.retrieval_enable_filters,
    )
