from flask import Blueprint, jsonify
from redis.exceptions import RedisError
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.config import Settings
from app.queue import redis_connection, scrape_queue

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


def _isoformat(value):
    return value.isoformat() if value else None
