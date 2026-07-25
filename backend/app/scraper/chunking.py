from typing import Any

from app.scraper.extractor import clean_text


def split_long_text(text: str, *, max_size: int, overlap: int) -> list[str]:
    text = clean_text(text)
    if not text:
        return []

    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    chunks = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_size:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = f"{current[-overlap:]}\n\n{paragraph}".strip()
            while len(current) > max_size:
                chunks.append(current[:max_size].strip())
                current = current[max_size - overlap :].strip()
        else:
            start = 0
            while start < len(paragraph):
                end = start + max_size
                chunks.append(paragraph[start:end].strip())
                start = max(end - overlap, start + 1)
            current = ""

    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if len(chunk) >= 80]


def create_chunks(
    document: dict[str, Any], *, chunk_size: int, chunk_overlap: int
) -> list[dict[str, Any]]:
    output = []
    chunk_number = 0
    title = document["title"]
    category = document.get("category")
    quick_facts = document.get("quick_facts", {})

    for section in document["sections"]:
        heading = section["heading"]
        section_text = (
            f"Program: {title}\n"
            f"Category: {category or 'Not specified'}\n"
            f"Section: {heading}\n\n"
            f"{section['content']}"
        )
        for chunk in split_long_text(
            section_text,
            max_size=chunk_size,
            overlap=chunk_overlap,
        ):
            output.append(
                {
                    "id": f"{document['id']}-{chunk_number:04d}",
                    "document_id": document["id"],
                    "chunk_number": chunk_number,
                    "title": title,
                    "section": heading,
                    "category": category,
                    "url": document["url"],
                    "quick_facts": quick_facts,
                    "text": chunk,
                }
            )
            chunk_number += 1
    return output
