import hashlib
import re
from typing import Any


def clean_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def split_long_text(text: str, *, max_size: int, overlap: int) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    paragraphs = [value.strip() for value in text.split("\n\n") if value.strip()]
    chunks: list[str] = []
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
            current = current[max(max_size - overlap, 1) :].strip()
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if len(chunk) >= 80]


def create_movie_chunks(
    document: dict[str, Any],
    *,
    chunk_size: int,
    chunk_overlap: int,
    generation: int = 1,
) -> list[dict[str, Any]]:
    """Chunk only real narrative text, retaining movie metadata for retrieval."""
    chunks = []
    chunk_number = 0
    for section in document.get("sections", []):
        heading = str(section.get("heading") or "Overview")
        content = str(section.get("content") or "").strip()
        for text in split_long_text(
            f"{heading}\n\n{content}",
            max_size=chunk_size,
            overlap=chunk_overlap,
        ):
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            chunks.append(
                {
                    "id": f"{document['imdb_id']}::source_aware::{chunk_number}",
                    "document_id": document["imdb_id"],
                    "chunk_number": chunk_number,
                    "title": document["title"],
                    "section": heading,
                    "year": document.get("year"),
                    "genres": document.get("genres", []),
                    "imdb_rating": document.get("imdb_rating"),
                    "url": document["url"],
                    "quick_facts": document.get("quick_facts", {}),
                    "text": text,
                    "strategy": "source_aware",
                    "content_hash": content_hash,
                    "generation": generation,
                    "char_len": len(text),
                }
            )
            chunk_number += 1
    return chunks
