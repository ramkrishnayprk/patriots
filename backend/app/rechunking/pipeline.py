import fcntl
import hashlib
import json
import logging
import os
import re
import shutil
import statistics
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

STRATEGIES = {"recursive", "section_aware"}
RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


@dataclass(frozen=True)
class RechunkOptions:
    chunk_size: int = 1200
    overlap: int = 200
    min_chunk: int = 150
    strategy: str = "section_aware"
    embed_prefix: bool = True

    def validate(self) -> None:
        if self.chunk_size < 100:
            raise ValueError("chunk_size must be at least 100.")
        if self.overlap < 0:
            raise ValueError("overlap cannot be negative.")
        if self.overlap >= self.chunk_size:
            raise ValueError("overlap must be smaller than chunk_size.")
        if self.min_chunk < 1 or self.min_chunk > self.chunk_size:
            raise ValueError("min_chunk must be between 1 and chunk_size.")
        if self.strategy not in STRATEGIES:
            raise ValueError("strategy must be recursive or section_aware.")


@dataclass
class SplitMetrics:
    oversized_sections: int = 0
    tiny_sections_merged: int = 0
    used_fallback: bool = False


def rechunk_run(*, data_dir: Path, run_id: str, options: RechunkOptions) -> dict[str, Any]:
    """Rebuild one run's chunks exclusively from its documents.jsonl file."""
    options.validate()
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id may contain only letters, numbers, hyphens, and underscores.")

    run_dir = Path(data_dir) / "runs" / run_id
    documents_path = run_dir / "documents.jsonl"
    if not documents_path.is_file():
        raise FileNotFoundError(f"documents.jsonl was not found for run {run_id}.")

    run_dir.mkdir(parents=True, exist_ok=True)
    with _run_lock(run_dir):
        return _rechunk_locked(
            run_dir=run_dir,
            documents_path=documents_path,
            options=options,
        )


def _rechunk_locked(
    *,
    run_dir: Path,
    documents_path: Path,
    options: RechunkOptions,
) -> dict[str, Any]:
    chunks_path = run_dir / "chunks.jsonl"
    errors_path = run_dir / "chunk_errors.log"
    report_path = run_dir / "chunk_report.json"
    manifest_path = run_dir / "chunk_manifest.json"
    generation = _next_generation(chunks_path, manifest_path)
    splitter = _create_splitter(options)

    documents_processed = 0
    documents_skipped = 0
    total_chunks = 0
    duplicates_dropped = 0
    validation_errors = 0
    oversized_sections = 0
    tiny_sections_merged = 0
    fallback_documents: list[str] = []
    chunks_per_document: list[int] = []
    character_lengths: list[int] = []
    seen_hashes: set[str] = set()

    chunks_temporary = _temporary_file(run_dir, "chunks")
    errors_temporary = _temporary_file(run_dir, "chunk-errors")
    try:
        with (
            documents_path.open(encoding="utf-8") as documents,
            chunks_temporary.open("w", encoding="utf-8") as chunks_output,
            errors_temporary.open("w", encoding="utf-8") as errors_output,
        ):
            for line_number, line in enumerate(documents, start=1):
                if not line.strip():
                    continue
                try:
                    document = json.loads(line)
                except json.JSONDecodeError as exc:
                    validation_errors += 1
                    documents_skipped += 1
                    _write_error(
                        errors_output,
                        line_number=line_number,
                        reason="invalid_json",
                        error=str(exc),
                    )
                    continue

                if not isinstance(document, dict):
                    validation_errors += 1
                    documents_skipped += 1
                    _write_error(
                        errors_output,
                        line_number=line_number,
                        reason="document_must_be_an_object",
                    )
                    continue

                document_id = str(document.get("id") or "").strip()
                text = str(document.get("text") or "").strip()
                sections = document.get("sections")
                if not document_id:
                    validation_errors += 1
                    documents_skipped += 1
                    _write_error(
                        errors_output,
                        line_number=line_number,
                        reason="missing_document_id",
                    )
                    continue
                if not text and not _usable_sections(sections):
                    validation_errors += 1
                    documents_skipped += 1
                    _write_error(
                        errors_output,
                        line_number=line_number,
                        document_id=document_id,
                        reason="missing_text_and_sections",
                    )
                    continue

                raw_chunks, metrics = _split_document(document, options, splitter)
                oversized_sections += metrics.oversized_sections
                tiny_sections_merged += metrics.tiny_sections_merged
                if metrics.used_fallback:
                    fallback_documents.append(document_id)

                document_chunk_count = 0
                for raw_chunk in raw_chunks:
                    final_text = _enrich_text(
                        raw_chunk["text"],
                        document=document,
                        first_chunk=document_chunk_count == 0,
                        embed_prefix=options.embed_prefix,
                    )
                    content_hash = hashlib.sha256(final_text.encode("utf-8")).hexdigest()
                    error = _validate_chunk(
                        text=final_text,
                        document_id=document_id,
                        chunk_number=document_chunk_count,
                        min_chunk=options.min_chunk,
                    )
                    if error:
                        validation_errors += 1
                        _write_error(
                            errors_output,
                            line_number=line_number,
                            document_id=document_id,
                            reason=error,
                            char_len=len(final_text),
                        )
                        continue
                    if content_hash in seen_hashes:
                        duplicates_dropped += 1
                        continue

                    seen_hashes.add(content_hash)
                    chunk = {
                        "id": (f"{document_id}::{options.strategy}::{document_chunk_count}"),
                        "document_id": document_id,
                        "chunk_number": document_chunk_count,
                        "title": str(document.get("title") or ""),
                        "section": raw_chunk["section"],
                        "year": document.get("year"),
                        "genres": document.get("genres") or [],
                        "imdb_rating": document.get("imdb_rating"),
                        "url": str(document.get("url") or ""),
                        "quick_facts": document.get("quick_facts") or {},
                        "text": final_text,
                        "strategy": options.strategy,
                        "content_hash": content_hash,
                        "generation": generation,
                        "char_len": len(final_text),
                    }
                    chunks_output.write(
                        json.dumps(chunk, ensure_ascii=False, separators=(",", ":")) + "\n"
                    )
                    document_chunk_count += 1
                    total_chunks += 1
                    character_lengths.append(len(final_text))

                if document_chunk_count:
                    documents_processed += 1
                    chunks_per_document.append(document_chunk_count)
                else:
                    documents_skipped += 1
                    validation_errors += 1
                    _write_error(
                        errors_output,
                        line_number=line_number,
                        document_id=document_id,
                        reason="document_produced_no_chunks",
                    )

            chunks_output.flush()
            os.fsync(chunks_output.fileno())
            errors_output.flush()
            os.fsync(errors_output.fileno())

        if total_chunks == 0:
            raise ValueError("Re-chunking produced no valid chunks; existing output was preserved.")

        generated_at = datetime.now(UTC).isoformat()
        report = {
            "run_id": run_dir.name,
            "generation": generation,
            "strategy": options.strategy,
            "configuration": asdict(options),
            "documents_processed": documents_processed,
            "documents_skipped": documents_skipped,
            "total_chunks": total_chunks,
            "chunks_per_document": _distribution(chunks_per_document),
            "character_lengths": _distribution(character_lengths),
            "oversized_sections_split": oversized_sections,
            "tiny_sections_merged": tiny_sections_merged,
            "fallback_document_count": len(fallback_documents),
            "fallback_documents": fallback_documents,
            "duplicates_dropped": duplicates_dropped,
            "validation_errors": validation_errors,
            "output": str(chunks_path.relative_to(run_dir.parent.parent)),
            "generated_at": generated_at,
        }
        manifest = {
            "generation": generation,
            "strategy": options.strategy,
            "configuration": asdict(options),
            "documents": documents_processed,
            "chunks": total_chunks,
            "generated_at": generated_at,
        }

        chunks_temporary.replace(chunks_path)
        movie_chunks_temporary = _temporary_file(run_dir, "movie-chunks")
        try:
            shutil.copyfile(chunks_path, movie_chunks_temporary)
            movie_chunks_temporary.replace(run_dir / "movie_chunks.jsonl")
        finally:
            movie_chunks_temporary.unlink(missing_ok=True)
        errors_temporary.replace(errors_path)
        _write_json_atomic(report_path, report)
        _write_json_atomic(manifest_path, manifest)
        logger.info("Re-chunk complete | %s", json.dumps(report, separators=(",", ":")))
        return report
    finally:
        chunks_temporary.unlink(missing_ok=True)
        errors_temporary.unlink(missing_ok=True)


def _split_document(
    document: dict[str, Any],
    options: RechunkOptions,
    splitter: RecursiveCharacterTextSplitter,
) -> tuple[list[dict[str, str]], SplitMetrics]:
    if options.strategy == "recursive":
        return _recursive_document_chunks(document, options, splitter), SplitMetrics()

    sections = _usable_sections(document.get("sections"))
    if len(sections) <= 1:
        return (
            _recursive_document_chunks(document, options, splitter),
            SplitMetrics(used_fallback=True),
        )

    output: list[dict[str, str]] = []
    pending_tiny: list[str] = []
    metrics = SplitMetrics()
    for section in sections:
        heading = section["heading"]
        content = section["content"]
        if len(content) < options.min_chunk:
            pending_tiny.append(f"{heading}\n\n{content}".strip())
            metrics.tiny_sections_merged += 1
            continue

        if len(content) > options.chunk_size:
            metrics.oversized_sections += 1
            pieces = _merge_tiny_fragments(
                splitter.split_text(content),
                min_chunk=options.min_chunk,
            )
        else:
            pieces = [content]

        section_chunks = [
            {"section": heading, "text": f"{heading}\n\n{piece}".strip()} for piece in pieces
        ]
        if pending_tiny and section_chunks:
            section_chunks[0]["text"] = "\n\n".join(
                [*pending_tiny, section_chunks[0]["text"]]
            ).strip()
            pending_tiny = []
        output.extend(section_chunks)

    if pending_tiny:
        trailing = "\n\n".join(pending_tiny).strip()
        if output:
            output[-1]["text"] = f"{output[-1]['text']}\n\n{trailing}".strip()
        else:
            output.append(
                {
                    "section": sections[0]["heading"],
                    "text": trailing,
                }
            )
    return output, metrics


def _recursive_document_chunks(
    document: dict[str, Any],
    options: RechunkOptions,
    splitter: RecursiveCharacterTextSplitter,
) -> list[dict[str, str]]:
    text = str(document.get("text") or "").strip()
    if not text:
        text = "\n\n".join(
            f"{section['heading']}\n\n{section['content']}"
            for section in _usable_sections(document.get("sections"))
        )
    pieces = _merge_tiny_fragments(splitter.split_text(text), min_chunk=options.min_chunk)
    section = str(document.get("title") or "")
    return [{"section": section, "text": piece} for piece in pieces]


def _usable_sections(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    sections = []
    for section in value:
        if not isinstance(section, dict):
            continue
        content = str(section.get("content") or "").strip()
        if not content:
            continue
        sections.append(
            {
                "heading": str(section.get("heading") or "Overview").strip() or "Overview",
                "content": content,
            }
        )
    return sections


def _create_splitter(options: RechunkOptions) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=options.chunk_size,
        chunk_overlap=options.overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", "? ", "! ", " ", ""],
        is_separator_regex=False,
        keep_separator=True,
    )


def _merge_tiny_fragments(chunks: list[str], *, min_chunk: int) -> list[str]:
    cleaned = [chunk.strip() for chunk in chunks if chunk.strip()]
    if len(cleaned) <= 1:
        return cleaned

    merged: list[str] = []
    pending = ""
    for chunk in cleaned:
        if pending:
            chunk = f"{pending}\n\n{chunk}".strip()
            pending = ""
        if len(chunk) < min_chunk:
            if merged:
                merged[-1] = f"{merged[-1]}\n\n{chunk}".strip()
            else:
                pending = chunk
            continue
        merged.append(chunk)
    if pending:
        if merged:
            merged[-1] = f"{merged[-1]}\n\n{pending}".strip()
        else:
            merged.append(pending)
    return merged


def _enrich_text(
    text: str,
    *,
    document: dict[str, Any],
    first_chunk: bool,
    embed_prefix: bool,
) -> str:
    text = text.strip()
    if not embed_prefix:
        return text

    prefix = [f"Movie: {str(document.get('title') or '').strip()}"]
    quick_facts = document.get("quick_facts")
    if first_chunk and isinstance(quick_facts, dict) and quick_facts:
        rendered = " | ".join(
            f"{str(key).replace('_', ' ').title()}: {value}"
            for key, value in sorted(quick_facts.items())
            if value is not None and value != ""
        )
        if rendered:
            prefix.append(f"Quick facts: {rendered}")
    return "\n".join([*prefix, "", text]).strip()


def _validate_chunk(
    *,
    text: str,
    document_id: str,
    chunk_number: int,
    min_chunk: int,
) -> str | None:
    if not document_id:
        return "missing_document_id"
    if chunk_number < 0:
        return "invalid_chunk_number"
    if not text:
        return "empty_text"
    if len(text) < min_chunk:
        return "chunk_below_minimum"
    return None


def _next_generation(chunks_path: Path, manifest_path: Path) -> int:
    maximum = 0
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            maximum = max(maximum, int(manifest.get("generation", 0)))
        except (OSError, ValueError, json.JSONDecodeError, TypeError):
            logger.warning("Ignoring unreadable chunk manifest at %s", manifest_path)

    if chunks_path.is_file():
        with chunks_path.open(encoding="utf-8") as chunks:
            for line in chunks:
                try:
                    maximum = max(maximum, int(json.loads(line).get("generation", 0)))
                except (ValueError, json.JSONDecodeError, AttributeError, TypeError):
                    continue
    return maximum + 1


def _distribution(values: list[int]) -> dict[str, int | float | None]:
    if not values:
        return {"min": None, "median": None, "max": None}
    median = statistics.median(values)
    return {
        "min": min(values),
        "median": int(median) if float(median).is_integer() else median,
        "max": max(values),
    }


def _write_error(output, **error: Any) -> None:
    output.write(json.dumps(error, ensure_ascii=False, separators=(",", ":")) + "\n")


def _temporary_file(directory: Path, prefix: str) -> Path:
    with NamedTemporaryFile(
        dir=directory,
        prefix=f".{prefix}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        return Path(temporary.name)


def _write_json_atomic(path: Path, data: Any) -> None:
    temporary = _temporary_file(path.parent, path.stem)
    try:
        with temporary.open("w", encoding="utf-8") as output:
            json.dump(data, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _run_lock(run_dir: Path) -> Iterator[None]:
    lock_path = run_dir / ".rechunk.lock"
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
