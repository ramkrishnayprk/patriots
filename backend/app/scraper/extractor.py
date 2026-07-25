import hashlib
import re
import time
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.scraper.url_utils import is_allowed_crawl_url, normalize_url


def clean_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def element_text(element: Tag | None) -> str | None:
    if not element:
        return None
    text = clean_text(element.get_text(" ", strip=True))
    return text or None


def remove_unwanted_elements(soup: BeautifulSoup) -> None:
    selectors = (
        "script",
        "style",
        "noscript",
        "svg",
        "canvas",
        "iframe",
        "form",
        "nav",
        "footer",
        "header",
        ".cookie",
        ".cookies",
        ".cookie-banner",
        ".modal",
        ".popup",
        ".request-info",
        ".lead-form",
        ".form-wrapper",
        "[aria-hidden='true']",
    )
    for selector in selectors:
        for element in soup.select(selector):
            element.decompose()


def extract_internal_links(
    html: str,
    current_url: str,
    *,
    base_url: str,
    allowed_domain: str,
) -> set[str]:
    soup = BeautifulSoup(html, "lxml")
    discovered = set()
    for link in soup.select("a[href]"):
        normalized = normalize_url(
            urljoin(current_url, link.get("href", "")),
            base_url=base_url,
            allowed_domain=allowed_domain,
        )
        if normalized and is_allowed_crawl_url(normalized, allowed_domain=allowed_domain):
            discovered.add(normalized)
    return discovered


def extract_meta_description(soup: BeautifulSoup) -> str | None:
    for selector in ('meta[name="description"]', 'meta[property="og:description"]'):
        meta = soup.select_one(selector)
        if meta and meta.get("content"):
            return clean_text(str(meta["content"]))
    return None


def extract_canonical_url(
    soup: BeautifulSoup,
    fallback_url: str,
    *,
    base_url: str,
    allowed_domain: str,
) -> str:
    canonical = soup.select_one('link[rel="canonical"]')
    if canonical and canonical.get("href"):
        normalized = normalize_url(
            str(canonical["href"]),
            base_url=base_url,
            allowed_domain=allowed_domain,
        )
        if normalized:
            return normalized
    return fallback_url


def extract_breadcrumbs(soup: BeautifulSoup) -> list[str]:
    selectors = (
        ".breadcrumb a",
        ".breadcrumbs a",
        '[aria-label="breadcrumb"] a',
        "nav.breadcrumb a",
    )
    for selector in selectors:
        items = [element_text(item) for item in soup.select(selector)]
        values = [item for item in items if item]
        if values:
            return values
    return []


def extract_quick_facts(soup: BeautifulSoup) -> dict[str, str]:
    facts: dict[str, str] = {}
    text = clean_text(soup.get_text("\n", strip=True))
    for pattern in (
        r"(\d+)\s+Credit Hours",
        r"Credit Hours\s+(\d+)",
        r"(\d+)[-\s]credit[-\s]hour",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            facts["credit_hours"] = match.group(1)
            break

    has_online = bool(re.search(r"\b100%\s+online\b|\bonline\b", text, re.IGNORECASE))
    has_campus = bool(re.search(r"\bon[-\s]?campus\b", text, re.IGNORECASE))
    if has_online and has_campus:
        facts["delivery_format"] = "Online and On-Campus"
    elif has_online:
        facts["delivery_format"] = "Online"
    elif has_campus:
        facts["delivery_format"] = "On-Campus"
    return facts


def find_main_content(soup: BeautifulSoup) -> Tag:
    for selector in ("main", "#main", "#content", ".main-content", ".page-content", "article"):
        element = soup.select_one(selector)
        if isinstance(element, Tag):
            return element
    return soup


def extract_sections(main: Tag) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current_heading = "Overview"
    current_content: list[str] = []

    def save_current_section() -> None:
        nonlocal current_content
        body = clean_text("\n".join(current_content))
        if body:
            sections.append({"heading": current_heading, "content": body})
        current_content = []

    for element in main.find_all(("h1", "h2", "h3", "p", "li", "table")):
        if element.name in {"h1", "h2", "h3"}:
            heading = element_text(element)
            if heading:
                save_current_section()
                current_heading = heading
        elif element.name == "table":
            rows = []
            for row in element.select("tr"):
                cells = [element_text(cell) for cell in row.select("th, td")]
                values = [cell for cell in cells if cell]
                if values:
                    rows.append(" | ".join(values))
            if rows:
                current_content.append("\n".join(rows))
        else:
            text = element_text(element)
            if text:
                current_content.append(text)

    save_current_section()
    return remove_duplicate_sections(sections)


def remove_duplicate_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for section in sections:
        signature = (
            section["heading"].strip().lower(),
            section["content"].strip().lower(),
        )
        if signature not in seen:
            seen.add(signature)
            unique.append(section)
    return unique


def infer_program_category(breadcrumbs: list[str], sections: list[dict[str, Any]]) -> str | None:
    categories = (
        "Business",
        "Counseling",
        "Criminal Justice",
        "Education",
        "General Studies",
        "Health, Human Services & Nursing",
        "Information Technology",
        "Leadership & Communications",
        "Mission & Ministry",
        "Social & Behavioral Sciences",
    )
    combined = " ".join(breadcrumbs + [section["heading"] for section in sections]).lower()
    return next((category for category in categories if category.lower() in combined), None)


def extract_program_page(
    html: str,
    source_url: str,
    *,
    base_url: str,
    allowed_domain: str,
) -> dict[str, Any]:
    original_soup = BeautifulSoup(html, "lxml")
    title = (
        element_text(original_soup.select_one("h1"))
        or element_text(original_soup.select_one("title"))
        or source_url
    )
    meta_description = extract_meta_description(original_soup)
    canonical_url = extract_canonical_url(
        original_soup,
        source_url,
        base_url=base_url,
        allowed_domain=allowed_domain,
    )
    breadcrumbs = extract_breadcrumbs(original_soup)
    quick_facts = extract_quick_facts(original_soup)

    clean_soup = BeautifulSoup(html, "lxml")
    remove_unwanted_elements(clean_soup)
    sections = extract_sections(find_main_content(clean_soup))
    category = infer_program_category(breadcrumbs, sections)

    full_text_parts = [title]
    if meta_description:
        full_text_parts.append(meta_description)
    for section in sections:
        full_text_parts.extend((section["heading"], section["content"]))
    full_text = clean_text("\n\n".join(full_text_parts))

    return {
        "id": hashlib.sha256(canonical_url.encode("utf-8")).hexdigest(),
        "document_type": "degree_program",
        "title": title,
        "url": canonical_url,
        "source_url": source_url,
        "domain": allowed_domain,
        "category": category,
        "breadcrumbs": breadcrumbs,
        "meta_description": meta_description,
        "quick_facts": quick_facts,
        "sections": sections,
        "text": full_text,
        "text_length": len(full_text),
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
