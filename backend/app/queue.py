from redis import Redis
from rq import Queue

from app.config import Settings


def redis_connection() -> Redis:
    return Redis.from_url(Settings.from_env().redis_url)


def scrape_queue() -> Queue:
    return Queue(
        "scraping",
        connection=redis_connection(),
        default_timeout="6h",
    )
