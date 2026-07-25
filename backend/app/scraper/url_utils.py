import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

TRACKING_PARAMETERS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
}

BLOCKED_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".css",
    ".js",
    ".xml",
    ".zip",
    ".mp4",
    ".mp3",
    ".woff",
    ".woff2",
    ".ttf",
)

BLOCKED_PATH_FRAGMENTS = (
    "/wp-admin/",
    "/wp-login/",
    "/feed/",
    "/tag/",
    "/author/",
    "/privacy",
    "/request-info",
    "/thank-you",
)


def normalize_url(url: str, *, base_url: str, allowed_domain: str) -> str | None:
    if not url:
        return None

    parsed = urlparse(urljoin(base_url, url.strip()))
    hostname = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or hostname != allowed_domain
        or parsed.username
        or parsed.password
        or port not in (None, 80, 443)
    ):
        return None

    clean_query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in TRACKING_PARAMETERS
        ]
    )
    path = re.sub(r"/+", "/", parsed.path or "/")
    if path != "/" and not path.endswith("/"):
        path += "/"

    return urlunparse(("https", allowed_domain, path, "", clean_query, ""))


def is_allowed_crawl_url(url: str, *, allowed_domain: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != allowed_domain:
        return False
    path = parsed.path.lower()
    if path.endswith(BLOCKED_EXTENSIONS):
        return False
    return not any(fragment in path for fragment in BLOCKED_PATH_FRAGMENTS)


def is_program_url(url: str) -> bool:
    return urlparse(url).path.startswith("/programs/")


def safe_filename(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    slug = urlparse(url).path.strip("/").replace("/", "_") or "homepage"
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", slug)
    return f"{slug[:80]}_{digest}.html"
