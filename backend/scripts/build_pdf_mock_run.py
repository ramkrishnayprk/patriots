#!/usr/bin/env python3
"""Create a pipeline-ready movie document run from extracted PDF text."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


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


def build_documents(
    *,
    catalog_path: Path,
    text_dir: Path,
    data_dir: Path,
    run_id: str,
) -> Path:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(catalog, list) or not catalog:
        raise ValueError("Catalog must be a non-empty JSON array.")

    documents: list[dict[str, Any]] = []
    for movie in catalog:
        slug = str(movie["slug"])
        text_path = text_dir / f"{slug}.txt"
        if not text_path.is_file():
            raise FileNotFoundError(f"Extracted PDF text is missing: {text_path}")

        extracted_text = text_path.read_text(encoding="utf-8").strip()
        if len(extracted_text) < 200:
            raise ValueError(f"Extracted PDF text is unexpectedly short: {text_path}")

        quick_facts = {
            "release_date": movie["release_date"],
            "runtime_minutes": movie["runtime_minutes"],
            "genres": ", ".join(movie["genres"]),
            "director": ", ".join(movie["directors"]),
            "writers": ", ".join(movie["writers"]),
            "top_cast": ", ".join(movie["top_cast"]),
            "imdb_rating": movie["imdb_rating"],
            "imdb_votes": movie["imdb_votes"],
        }
        documents.append(
            {
                "id": movie["id"],
                "document_type": "fictional_movie_pdf",
                "title": movie["title"],
                "original_title": movie["original_title"],
                "year": movie["year"],
                "release_date": movie["release_date"],
                "runtime_minutes": movie["runtime_minutes"],
                "genres": movie["genres"],
                "directors": movie["directors"],
                "writers": movie["writers"],
                "top_cast": movie["top_cast"],
                "imdb_rating": movie["imdb_rating"],
                "imdb_votes": movie["imdb_votes"],
                "overview": movie["overview"],
                "quick_facts": quick_facts,
                "source_type": "pdf",
                "source_file": f"pdfs/{slug}.pdf",
                "url": f"local://fictional-movie-pdfs/{slug}.pdf",
                "sections": [
                    {
                        "heading": "Movie dossier",
                        "content": extracted_text,
                    }
                ],
                "text": extracted_text,
                "text_length": len(extracted_text),
            }
        )

    output_path = data_dir / "runs" / run_id / "documents.jsonl"
    _write_jsonl_atomic(output_path, documents)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--text-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--run-id", default="fictional-pdf-movies")
    args = parser.parse_args()

    output = build_documents(
        catalog_path=args.catalog,
        text_dir=args.text_dir,
        data_dir=args.data_dir,
        run_id=args.run_id,
    )
    print(output)


if __name__ == "__main__":
    main()
