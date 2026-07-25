import logging
import os
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from flask import Blueprint, after_this_request, jsonify, request
from redis.exceptions import RedisError
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.config import Settings
from app.embedding.model import is_model_installed
from app.embedding.pipeline import EmbeddingOptions, ingest_run
from app.feedback.query_log import QueryLogStore
from app.generation.pipeline import (
    GenerationOptions,
    GenerationProviderError,
    generate_answer,
)
from app.queue import acquisition_queue, redis_connection
from app.rechunking.pipeline import RechunkOptions, rechunk_run
from app.retrieval.conversation import resolve_conversational_reference
from app.retrieval.expansion import (
    QueryExpansionOptions,
    QueryExpansionProviderError,
    expand_weak_query,
)
from app.retrieval.fusion import fuse_retrieval_attempts
from app.retrieval.pipeline import RetrievalOptions, search_run
from app.sessions.store import (
    InvalidSessionIdError,
    JsonFileSessionStore,
    SessionNotFoundError,
    SessionStorageError,
)
from app.structured.pipeline import route_query, run_structured_query
from app.structured.repository import create_structured_repository
from app.structured.title_lookup import (
    build_entity_response,
    resolve_title_query,
    rewrite_query_with_title,
)

api = Blueprint("api", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


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
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return (
            jsonify(
                {
                    "error": {
                        "code": "invalid_session",
                        "message": "Request body must be a JSON object.",
                    }
                }
            ),
            400,
        )

    try:
        title = _optional_string(payload, "title", default="New Session", max_length=120)
        model_id = _optional_string(payload, "model_id", default="", max_length=120)
        messages = payload.get("messages", [])
        if not isinstance(messages, list):
            raise ValueError("messages must be an array.")
        session = _session_store().create(
            title=title,
            model_id=model_id,
            messages=messages,
        )
    except ValueError as exc:
        return (
            jsonify({"error": {"code": "invalid_session", "message": str(exc)}}),
            400,
        )
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


@api.patch("/sessions/<string:session_id>")
def rename_session(session_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return (
            jsonify(
                {
                    "error": {
                        "code": "invalid_session",
                        "message": "Request body must be a JSON object.",
                    }
                }
            ),
            400,
        )
    try:
        title = _required_string(payload, "title", max_length=120)
        session = _session_store().rename(session_id, title)
    except InvalidSessionIdError as exc:
        return (
            jsonify({"error": {"code": "invalid_session_id", "message": str(exc)}}),
            400,
        )
    except ValueError as exc:
        return (
            jsonify({"error": {"code": "invalid_session", "message": str(exc)}}),
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
                        "message": "The session could not be updated.",
                    }
                }
            ),
            500,
        )

    response = jsonify({"data": session})
    response.headers["Cache-Control"] = "no-store"
    return response


@api.post("/sessions/<string:session_id>/messages")
def append_session_messages(session_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return (
            jsonify(
                {
                    "error": {
                        "code": "invalid_messages",
                        "message": "Request body must be a JSON object.",
                    }
                }
            ),
            400,
        )
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return (
            jsonify(
                {
                    "error": {
                        "code": "invalid_messages",
                        "message": "messages must be an array.",
                    }
                }
            ),
            400,
        )

    try:
        session = _session_store().append_messages(session_id, messages)
    except InvalidSessionIdError as exc:
        return (
            jsonify({"error": {"code": "invalid_session_id", "message": str(exc)}}),
            400,
        )
    except ValueError as exc:
        return (
            jsonify({"error": {"code": "invalid_messages", "message": str(exc)}}),
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
                        "message": "The session could not be updated.",
                    }
                }
            ),
            500,
        )

    response = jsonify({"data": session})
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


@api.get("/runs")
def list_runs():
    settings = Settings.from_env()
    runs_directory = Path(settings.data_dir) / "runs"
    runs = []
    if runs_directory.is_dir():
        for run_directory in runs_directory.iterdir():
            if not run_directory.is_dir():
                continue
            structured_path = run_directory / settings.structured_records_filename
            if not structured_path.is_file():
                continue
            runs.append(
                {
                    "id": run_directory.name,
                    "structured_ready": True,
                    "semantic_ready": (
                        (run_directory / "bm25.sqlite3").is_file()
                        and (run_directory / "vector_db" / "chroma").is_dir()
                    ),
                    "updated_at": datetime.fromtimestamp(
                        structured_path.stat().st_mtime,
                        tz=UTC,
                    ).isoformat(),
                }
            )
    runs.sort(key=lambda run: run["updated_at"], reverse=True)
    response = jsonify({"data": runs, "count": len(runs)})
    response.headers["Cache-Control"] = "no-store"
    return response


@api.get("/query-logs")
def list_query_logs():
    try:
        limit = _query_integer("limit", 100)
        if limit > 1_000:
            raise ValueError("limit cannot exceed 1000.")
        decision = request.args.get("decision") or None
        triage_bucket = request.args.get("triage_bucket") or None
        entries = _query_log_store().list_recent(
            limit=limit,
            decision=decision,
            triage_bucket=triage_bucket,
        )
    except ValueError as exc:
        return (
            jsonify({"error": {"code": "invalid_query_log_request", "message": str(exc)}}),
            400,
        )
    except OSError:
        return (
            jsonify(
                {
                    "error": {
                        "code": "query_log_unavailable",
                        "message": "The query log could not be read.",
                    }
                }
            ),
            500,
        )

    response = jsonify({"data": entries, "count": len(entries)})
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
    requested_model = payload.get("model")
    if requested_model is not None and (
        not isinstance(requested_model, str) or not requested_model.strip()
    ):
        return (
            jsonify(
                {
                    "error": {
                        "code": "invalid_model",
                        "message": "model must be a non-empty string.",
                    }
                }
            ),
            400,
        )
    if isinstance(requested_model, str):
        requested_model = requested_model.strip()
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
    try:
        history = _conversation_history(payload)
    except ValueError as exc:
        return (
            jsonify(
                {
                    "error": {
                        "code": "invalid_history",
                        "message": str(exc),
                    }
                }
            ),
            400,
        )

    _register_query_log(run_id, query)

    try:
        settings = Settings.from_env()
        generation_model = requested_model or settings.openai_model
        if generation_model not in settings.openai_allowed_models:
            return (
                jsonify(
                    {
                        "error": {
                            "code": "unsupported_model",
                            "message": (
                                "model must be one of: "
                                f"{', '.join(settings.openai_allowed_models)}."
                            ),
                        }
                    }
                ),
                400,
            )
        repository = _movie_repository(settings, run_id)
        conversation_rewrite = resolve_conversational_reference(query, history)
        effective_query = (
            conversation_rewrite.rewritten_query
            if conversation_rewrite
            else query
        )
        if mode != "semantic":
            title_match = resolve_title_query(
                effective_query,
                repository=repository,
                aliases_path=settings.title_aliases_path,
                min_score=settings.title_lookup_min_score,
                ambiguity_margin=settings.title_lookup_ambiguity_margin,
            )
            if title_match and title_match.intent == "details":
                result = build_entity_response(
                    query,
                    title_match,
                    stage="pre_retrieval",
                )
                _attach_conversation_rewrite(result, conversation_rewrite)
                response = jsonify({"data": result})
                response.headers["Cache-Control"] = "no-store"
                return response

        decision = route_query(effective_query, mode=mode)
        if decision.path == "structured":
            try:
                result = run_structured_query(
                    effective_query,
                    repository=repository,
                    decision=decision,
                    max_list_items=settings.structured_max_list_items,
                    min_rating_votes=settings.structured_min_rating_votes,
                    default_rank_limit=settings.structured_default_rank_limit,
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
            _attach_conversation_rewrite(result, conversation_rewrite)
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
            query=effective_query,
            options=_retrieval_options(settings),
        )
        retrieval["_kind"] = "original"
        retrieval_attempts = [retrieval]
        title_match = None
        expansion_used = False
        escalation = {
            "attempted": False,
            "deterministic_title_retry": None,
            "llm_expansion": None,
        }
        if _retrieval_is_weak(
            retrieval,
            min_rerank_score=settings.generation_min_rerank_score,
        ):
            title_match = resolve_title_query(
                effective_query,
                repository=repository,
                aliases_path=settings.title_aliases_path,
                min_score=settings.title_lookup_min_score,
                ambiguity_margin=settings.title_lookup_ambiguity_margin,
            )
            if title_match:
                rewritten_query = rewrite_query_with_title(
                    effective_query,
                    title_match,
                )
                retry = search_run(
                    data_dir=settings.data_dir,
                    run_id=run_id,
                    query=rewritten_query,
                    options=_retrieval_options(settings),
                )
                retry["_kind"] = "canonical_title"
                retrieval_attempts.append(retry)
                escalation["attempted"] = True
                escalation["deterministic_title_retry"] = {
                    "strategy": "fuzzy_title_rewrite",
                    "original_query": effective_query,
                    "rewritten_query": rewritten_query,
                    "matched_title": title_match.matched_title,
                    "canonical_title": title_match.record.get("title"),
                    "imdb_id": title_match.record.get("imdb_id"),
                    "match_score": title_match.score,
                    "retry_status": retry.get("status"),
                }
                if _retrieval_strength(retry) > _retrieval_strength(retrieval):
                    retrieval = retry
                    escalation["deterministic_title_retry"]["selected"] = "retry"
                else:
                    escalation["deterministic_title_retry"]["selected"] = "original"

            if (
                _retrieval_is_weak(
                    retrieval,
                    min_rerank_score=settings.generation_min_rerank_score,
                )
                and settings.query_expansion_enabled
                and not dry_run
            ):
                escalation["attempted"] = True
                try:
                    expanded = expand_weak_query(
                        effective_query,
                        options=QueryExpansionOptions(
                            api_key=settings.openai_api_key,
                            model=settings.query_expansion_model,
                            timeout_seconds=settings.openai_timeout_seconds,
                            max_output_tokens=(
                                settings.query_expansion_max_output_tokens
                            ),
                            variation_count=settings.query_expansion_variations,
                            max_query_chars=settings.retrieval_max_query_chars,
                        ),
                    )
                except QueryExpansionProviderError as exc:
                    escalation["llm_expansion"] = {
                        "attempted": True,
                        "status": "provider_error",
                        "message": str(exc),
                    }
                else:
                    expansion_used = True
                    for variation_number, variation in enumerate(
                        expanded.variations,
                        start=1,
                    ):
                        variation_result = search_run(
                            data_dir=settings.data_dir,
                            run_id=run_id,
                            query=variation,
                            options=_retrieval_options(settings),
                        )
                        variation_result["_kind"] = (
                            f"query_variation_{variation_number}"
                        )
                        retrieval_attempts.append(variation_result)

                    if settings.query_expansion_hyde_enabled:
                        hyde_result = search_run(
                            data_dir=settings.data_dir,
                            run_id=run_id,
                            query=expanded.hypothetical_document,
                            options=replace(
                                _retrieval_options(settings),
                                enable_filters=False,
                            ),
                        )
                        hyde_result["_kind"] = "hyde"
                        retrieval_attempts.append(hyde_result)

                    fused = fuse_retrieval_attempts(
                        original_query=effective_query,
                        attempts=retrieval_attempts,
                        final_k=settings.retrieval_final_k,
                        rrf_k=settings.query_expansion_rrf_k,
                    )
                    escalation["llm_expansion"] = {
                        "attempted": True,
                        "status": "completed",
                        "model": settings.query_expansion_model,
                        "variation_count": len(expanded.variations),
                        "hyde_used": settings.query_expansion_hyde_enabled,
                        "search_attempts": len(retrieval_attempts),
                    }
                    if _retrieval_strength(fused) >= _retrieval_strength(retrieval):
                        retrieval = fused
                        escalation["selected"] = "multi_query_hyde_rrf"
                    else:
                        escalation["selected"] = "best_pre_expansion_attempt"
            elif dry_run and settings.query_expansion_enabled:
                escalation["llm_expansion"] = {
                    "attempted": False,
                    "status": "skipped_dry_run",
                }

            if escalation["attempted"] or escalation["llm_expansion"]:
                retrieval.setdefault("diagnostics", {})["escalation"] = escalation

        result = generate_answer(
            retrieval,
            options=GenerationOptions(
                api_key=settings.openai_api_key,
                model=generation_model,
                timeout_seconds=settings.openai_timeout_seconds,
                max_output_tokens=settings.openai_max_output_tokens,
                min_rerank_score=settings.generation_min_rerank_score,
            ),
            dry_run=dry_run,
        )
        result["path"] = "semantic"
        result["router"] = {
            "reason": decision.reason,
            "vector_db_used": True,
            "openai_retrieval_expansion_used": expansion_used,
            "generation_model": generation_model,
        }
        if title_match:
            result["lookup"] = {
                "stage": "escalation",
                "extracted_title": title_match.extracted_title,
                "matched_title": title_match.matched_title,
                "canonical_title": title_match.record.get("title"),
                "imdb_id": title_match.record.get("imdb_id"),
                "score": title_match.score,
                "match_type": title_match.match_type,
            }
        _attach_conversation_rewrite(result, conversation_rewrite)
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


def _movie_repository(settings: Settings, run_id: str):
    records_path = (
        Path(settings.data_dir)
        / "runs"
        / run_id
        / settings.structured_records_filename
    )
    return create_structured_repository(
        backend=settings.structured_backend,
        records_path=records_path,
    )


def _conversation_history(payload: dict) -> list[dict]:
    raw_history = payload.get("history", [])
    if raw_history is None:
        return []
    if not isinstance(raw_history, list):
        raise ValueError("history must be an array.")
    if len(raw_history) > 12:
        raise ValueError("history cannot contain more than 12 messages.")

    history = []
    for raw_message in raw_history:
        if not isinstance(raw_message, dict):
            raise ValueError("Each history message must be a JSON object.")
        role = raw_message.get("role")
        content = raw_message.get("content")
        if role not in {"user", "assistant"}:
            raise ValueError("History message role must be user or assistant.")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("History message content must be a non-empty string.")
        if len(content) > 4_000:
            raise ValueError("History message content cannot exceed 4000 characters.")
        message = {"role": role, "content": content.strip()}
        sources = raw_message.get("sources")
        if isinstance(sources, list):
            message["sources"] = [
                {
                    "title": str(source.get("title") or "").strip(),
                    "url": str(source.get("url") or "").strip(),
                }
                for source in sources[:10]
                if isinstance(source, dict)
                and str(source.get("title") or "").strip()
            ]
        history.append(message)
    return history


def _attach_conversation_rewrite(result: dict, rewrite) -> None:
    if rewrite is None:
        return
    result["conversation"] = {
        "reference_resolved": True,
        "strategy": rewrite.strategy,
        "original_query": rewrite.original_query,
        "rewritten_query": rewrite.rewritten_query,
        "referenced_title": rewrite.referenced_title,
    }


def _query_log_store() -> QueryLogStore:
    data_dir = Path(os.getenv("DATA_DIR", "/app/data"))
    return QueryLogStore(data_dir / "query_logs" / "queries.jsonl")


def _register_query_log(run_id: str, query: str) -> None:
    @after_this_request
    def persist_query_log(response):
        try:
            payload = response.get_json(silent=True) if response.is_json else {}
            payload = payload if isinstance(payload, dict) else {}
            data = payload.get("data")
            data = data if isinstance(data, dict) else {}
            error = payload.get("error")
            error = error if isinstance(error, dict) else {}
            answer_type = data.get("type")
            lookup = data.get("lookup")
            lookup = lookup if isinstance(lookup, dict) else {}
            retrieval = data.get("retrieval")
            retrieval = retrieval if isinstance(retrieval, dict) else {}
            diagnostics = retrieval.get("diagnostics")
            diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
            escalation = diagnostics.get("escalation")
            escalation = escalation if isinstance(escalation, dict) else {}

            if response.status_code >= 400:
                decision = "error"
                triage_bucket = "system_error"
            elif answer_type in {"not_in_sources", "out_of_scope"}:
                decision = "refused"
                triage_bucket = "needs_review"
            else:
                decision = "answered"
                triage_bucket = (
                    "recall_miss_recovered"
                    if (
                        lookup.get("stage") == "escalation"
                        or escalation.get("selected")
                        == "multi_query_hyde_rrf"
                    )
                    else "answered"
                )

            _query_log_store().append(
                {
                    "run_id": run_id,
                    "query": query,
                    "response_status": response.status_code,
                    "decision": decision,
                    "triage_bucket": triage_bucket,
                    "answer_type": answer_type,
                    "path": data.get("path"),
                    "operation": data.get("operation"),
                    "router_reason": (data.get("router") or {}).get("reason")
                    if isinstance(data.get("router"), dict)
                    else None,
                    "retrieval_status": retrieval.get("status"),
                    "top_score": retrieval.get("top_score"),
                    "top_rerank_score": retrieval.get("top_rerank_score"),
                    "result_count": data.get("count"),
                    "lookup": lookup or None,
                    "escalation": escalation or None,
                    "conversation_rewrite": data.get("conversation"),
                    "error_code": error.get("code"),
                }
            )
        except (OSError, TypeError, ValueError):
            logger.exception("Unable to persist query feedback log")
        return response


def _retrieval_is_weak(
    retrieval: dict,
    *,
    min_rerank_score: float,
) -> bool:
    results = retrieval.get("results")
    if retrieval.get("status") in {"no_results", "low_confidence"}:
        return True
    if not isinstance(results, list) or not results:
        return True
    return _number_or_negative_infinity(results[0].get("rerank_score")) < (
        min_rerank_score
    )


def _retrieval_strength(retrieval: dict) -> tuple[int, float, float]:
    results = retrieval.get("results")
    top_result = results[0] if isinstance(results, list) and results else {}
    confident = int(retrieval.get("status") == "ok")
    return (
        confident,
        _number_or_negative_infinity(top_result.get("rerank_score")),
        _number_or_negative_infinity(top_result.get("score")),
    )


def _number_or_negative_infinity(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def _required_string(
    payload: dict,
    name: str,
    *,
    max_length: int,
) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{name} cannot exceed {max_length} characters.")
    return normalized


def _optional_string(
    payload: dict,
    name: str,
    *,
    default: str,
    max_length: int,
) -> str:
    value = payload.get(name, default)
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string.")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{name} cannot exceed {max_length} characters.")
    return normalized or default


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
