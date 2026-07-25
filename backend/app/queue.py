from redis import Redis
from rq import Queue

from app.config import Settings


def redis_connection() -> Redis:
    return Redis.from_url(Settings.from_env().redis_url)


def acquisition_queue() -> Queue:
    return Queue(
        "acquisition",
        connection=redis_connection(),
        default_timeout="24h",
    )
