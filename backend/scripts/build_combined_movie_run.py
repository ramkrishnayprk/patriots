#!/usr/bin/env python3
"""Merge an existing movie run and a supplemental PDF run without re-chunking."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Callable

RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Required input is missing: {path}")

    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path} at line {line_number}.") from exc
            if not isinstance(record, dict):
                raise ValueError(f"Record {line_number} in {path} is not an object.")
            records.append(record)
    return records


def _deduplicate(
    records: list[dict[str, Any]],
    *,
    key: Callable[[dict[str, Any]], str],
) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for record in records:
        record_key = key(record).strip()
        if not record_key:
            raise ValueError("A merged record is missing its identity field.")
        unique[record_key] = record
    return list(unique.values())


def _structured_pdf_record(document: dict[str, Any]) -> dict[str, Any]:
    source_file = str(document.get("source_file") or "")
    return {
        **document,
        "imdb_id": str(document["id"]),
        "runtime": document.get("runtime_minutes"),
        "top_cast": [
            {"name": str(name), "characters": "[]"}
            for name in document.get("top_cast", [])
            if str(name).strip()
        ],
        "source_urls": {
            "pdf": str(document.get("url") or ""),
            "local_file": source_file,
        },
        "window_status": "fictional_mock",
    }


def _write_jsonl_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        for record in records:
            temporary.write(json.dumps(record, ensure_ascii=False) + "\n")
        temporary.flush()
        os.fsync(temporary.fileno())
    temporary_path.replace(path)


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        json.dump(value, temporary, ensure_ascii=False, indent=2)
        temporary.write("\n")
        temporary.flush()
        os.fsync(temporary.fileno())
    temporary_path.replace(path)


def build_combined_run(
    *,
    data_dir: Path,
    source_run_id: str,
    supplemental_run_id: str,
    output_run_id: str,
) -> dict[str, Any]:
    for run_id in (source_run_id, supplemental_run_id, output_run_id):
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise ValueError(f"Invalid run ID: {run_id}")
    if output_run_id in {source_run_id, supplemental_run_id}:
        raise ValueError("The output run must differ from both input runs.")

    runs_dir = data_dir / "runs"
    source_dir = runs_dir / source_run_id
    supplemental_dir = runs_dir / supplemental_run_id
    output_dir = runs_dir / output_run_id

    source_documents = _read_jsonl(source_dir / "documents.jsonl")
    supplemental_documents = _read_jsonl(supplemental_dir / "documents.jsonl")
    source_chunks = _read_jsonl(source_dir / "chunks.jsonl")
    supplemental_chunks = _read_jsonl(supplemental_dir / "chunks.jsonl")
    source_structured = _read_jsonl(source_dir / "movies_2026.jsonl")

    documents = _deduplicate(
        [*source_documents, *supplemental_documents],
        key=lambda item: str(item.get("id") or item.get("imdb_id") or ""),
    )
    chunks = _deduplicate(
        [*source_chunks, *supplemental_chunks],
        key=lambda item: str(item.get("id") or ""),
    )
    structured = _deduplicate(
        [
            *source_structured,
            *(_structured_pdf_record(document) for document in supplemental_documents),
        ],
        key=lambda item: str(item.get("imdb_id") or item.get("id") or ""),
    )

    _write_jsonl_atomic(output_dir / "documents.jsonl", documents)
    _write_jsonl_atomic(output_dir / "chunks.jsonl", chunks)
    _write_jsonl_atomic(output_dir / "movie_chunks.jsonl", chunks)
    _write_jsonl_atomic(output_dir / "movies_2026.jsonl", structured)

    manifest = {
        "run_id": output_run_id,
        "source_runs": [source_run_id, supplemental_run_id],
        "documents": len(documents),
        "chunks": len(chunks),
        "structured_records": len(structured),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json_atomic(output_dir / "merge_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--source-run", required=True)
    parser.add_argument("--supplemental-run", required=True)
    parser.add_argument("--output-run", default="combined-movies")
    args = parser.parse_args()

    result = build_combined_run(
        data_dir=args.data_dir,
        source_run_id=args.source_run,
        supplemental_run_id=args.supplemental_run,
        output_run_id=args.output_run,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
