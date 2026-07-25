import logging
import random
import time
import uuid
from collections import deque
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

from rq import get_current_job

from app.config import Settings
from app.scraper.chunking import create_chunks
from app.scraper.extractor import extract_internal_links, extract_program_page
from app.scraper.fetcher import FetchError, ScraperApiClient
from app.scraper.storage import RunStorage
from app.scraper.url_utils import (
    is_allowed_crawl_url,
    is_program_url,
    normalize_url,
)

logger = logging.getLogger(__name__)


def run_scrape_job() -> dict:
    job = get_current_job()
    run_id = job.id if job else str(uuid.uuid4())
    return crawl_site(run_id=run_id, job=job)


def crawl_site(*, run_id: str, job=None) -> dict:
    settings = Settings.from_env()
    settings.require_scraperapi_key()
    client = ScraperApiClient(settings)
    storage = RunStorage(settings.data_dir, run_id)

    base_url = normalize_url(
        settings.base_url,
        base_url=settings.base_url,
        allowed_domain=settings.allowed_domain,
    )
    if not base_url:
        raise ValueError("BASE_URL must be an HTTP(S) URL on ALLOWED_DOMAIN.")

    robots, min_delay, max_delay = _load_robots_policy(client, settings, base_url)
    time.sleep(min_delay)
    queue = deque([base_url])
    queued_urls = {base_url}
    visited_urls: set[str] = set()
    discovered_urls: set[str] = {base_url}
    programs: list[dict] = []
    chunks: list[dict] = []
    failed_urls: list[dict] = []
    processed_pages = 0

    _update_progress(
        job,
        phase="crawling",
        processed_pages=0,
        max_pages=settings.max_pages,
        programs=0,
        chunks=0,
        failed=0,
    )

    while queue and processed_pages < settings.max_pages:
        current_url = queue.popleft()
        if current_url in visited_urls:
            continue
        visited_urls.add(current_url)

        if not robots.can_fetch(settings.user_agent, current_url):
            logger.info("robots.txt denied URL | target=%s", current_url)
            continue

        logger.info("Fetching page | target=%s", current_url)
        try:
            result = client.fetch(
                current_url,
                render=settings.render_javascript,
            )
            processed_pages += 1
            storage.save_raw_html(current_url, result.text)
            links = extract_internal_links(
                result.text,
                current_url,
                base_url=base_url,
                allowed_domain=settings.allowed_domain,
            )
            discovered_urls.update(links)
            _enqueue_links(
                links,
                queue=queue,
                queued_urls=queued_urls,
                visited_urls=visited_urls,
                robots=robots,
                user_agent=settings.user_agent,
                allowed_domain=settings.allowed_domain,
            )

            if is_program_url(current_url):
                _extract_and_append_program(
                    result.text,
                    current_url,
                    settings=settings,
                    programs=programs,
                    chunks=chunks,
                    failed_urls=failed_urls,
                )
        except FetchError as exc:
            processed_pages += 1
            failed_urls.append(
                {
                    "url": current_url,
                    "reason": "fetch_failed",
                    "status_code": exc.status_code,
                }
            )
        except (OSError, ValueError, TypeError) as exc:
            logger.exception("Page processing failed | target=%s", current_url)
            failed_urls.append(
                {
                    "url": current_url,
                    "reason": "processing_failed",
                    "error": str(exc),
                }
            )

        if processed_pages and processed_pages % settings.checkpoint_interval == 0:
            storage.save_checkpoint(
                programs=_deduplicate(programs, "id"),
                chunks=_deduplicate(chunks, "id"),
                failed_urls=failed_urls,
                discovered_urls=discovered_urls,
            )

        _update_progress(
            job,
            phase="crawling",
            processed_pages=processed_pages,
            max_pages=settings.max_pages,
            queued_pages=len(queue),
            discovered_pages=len(discovered_urls),
            programs=len(programs),
            chunks=len(chunks),
            failed=len(failed_urls),
        )
        if queue and processed_pages < settings.max_pages:
            time.sleep(random.uniform(min_delay, max_delay))

    programs = _deduplicate(programs, "id")
    chunks = _deduplicate(chunks, "id")
    storage.save_checkpoint(
        programs=programs,
        chunks=chunks,
        failed_urls=failed_urls,
        discovered_urls=discovered_urls,
    )

    summary = {
        "run_id": run_id,
        "pages_processed": processed_pages,
        "pages_visited": len(visited_urls),
        "pages_discovered": len(discovered_urls),
        "programs": len(programs),
        "chunks": len(chunks),
        "failed": len(failed_urls),
        "artifacts": storage.relative_run_path(),
    }
    _update_progress(job, phase="completed", **summary)
    logger.info(
        "Crawl complete | pages=%s | programs=%s | chunks=%s | failed=%s",
        processed_pages,
        len(programs),
        len(chunks),
        len(failed_urls),
    )
    return summary


def _load_robots_policy(
    client: ScraperApiClient,
    settings: Settings,
    base_url: str,
) -> tuple[RobotFileParser, float, float]:
    robots_url = urljoin(base_url, "/robots.txt")
    result = client.fetch(robots_url, render=False)
    if "user-agent" not in result.text.lower():
        raise ValueError("The source site returned an invalid robots.txt response.")
    robots = RobotFileParser()
    robots.set_url(robots_url)
    robots.parse(result.text.splitlines())

    robots_delay = robots.crawl_delay(settings.user_agent)
    if robots_delay is None:
        robots_delay = robots.crawl_delay("*")
    minimum = max(settings.min_delay_seconds, float(robots_delay or 0))
    maximum = max(settings.max_delay_seconds, minimum)
    logger.info("Crawl policy loaded | delay=%.2f-%.2fs", minimum, maximum)
    return robots, minimum, maximum


def _enqueue_links(
    links: set[str],
    *,
    queue: deque,
    queued_urls: set[str],
    visited_urls: set[str],
    robots: RobotFileParser,
    user_agent: str,
    allowed_domain: str,
) -> None:
    allowed_links = [
        link
        for link in links
        if is_allowed_crawl_url(link, allowed_domain=allowed_domain)
        and robots.can_fetch(user_agent, link)
        and link not in visited_urls
        and link not in queued_urls
    ]
    program_links = sorted(link for link in allowed_links if is_program_url(link))
    other_links = sorted(link for link in allowed_links if not is_program_url(link))
    for link in reversed(program_links):
        queue.appendleft(link)
        queued_urls.add(link)
    for link in other_links:
        queue.append(link)
        queued_urls.add(link)


def _extract_and_append_program(
    html: str,
    current_url: str,
    *,
    settings: Settings,
    programs: list[dict],
    chunks: list[dict],
    failed_urls: list[dict],
) -> None:
    try:
        document = extract_program_page(
            html,
            current_url,
            base_url=settings.base_url,
            allowed_domain=settings.allowed_domain,
        )
        if document["text_length"] < 250:
            failed_urls.append({"url": current_url, "reason": "low_content"})
            return
        programs.append(document)
        chunks.extend(
            create_chunks(
                document,
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
            )
        )
    except (ValueError, TypeError, KeyError) as exc:
        logger.exception("Program extraction failed | target=%s", current_url)
        failed_urls.append(
            {
                "url": current_url,
                "reason": "parsing_failed",
                "error": str(exc),
            }
        )


def _deduplicate(records: list[dict], key: str) -> list[dict]:
    return list({record[key]: record for record in records}.values())


def _update_progress(job, **progress) -> None:
    if job is None:
        return
    job.meta["progress"] = progress
    job.save_meta()
