import csv
import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

CSV_FIELDS = (
    "imdb_id",
    "title",
    "original_title",
    "release_date",
    "year",
    "runtime",
    "genres",
    "imdb_rating",
    "imdb_votes",
    "tmdb_vote_average",
    "directors",
    "writers",
    "top_cast",
    "overview",
    "source_urls",
    "fetched_at",
    "content_hash",
)


class MovieRunStorage:
    def __init__(self, data_dir: Path, run_id: str):
        safe_run_id = re.sub(r"[^a-zA-Z0-9_-]", "_", run_id)
        if not safe_run_id:
            raise ValueError("Run ID cannot be empty.")
        self.data_dir = Path(data_dir)
        self.run_dir = self.data_dir / "runs" / safe_run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        *,
        movies: list[dict[str, Any]],
        documents: list[dict[str, Any]],
        chunks: list[dict[str, Any]],
        missing_report: list[dict[str, Any]],
        qa_report: dict[str, Any],
        manifest: dict[str, Any],
    ) -> None:
        _write_jsonl_atomic(self.run_dir / "movies_2026.jsonl", movies)
        _write_csv_atomic(self.run_dir / "movies_2026.csv", movies)
        _write_jsonl_atomic(self.run_dir / "documents.jsonl", documents)
        _write_jsonl_atomic(self.run_dir / "movie_chunks.jsonl", chunks)
        _write_jsonl_atomic(self.run_dir / "chunks.jsonl", chunks)
        _write_json_atomic(self.run_dir / "missing_report.json", missing_report)
        _write_json_atomic(self.run_dir / "qa_report.json", qa_report)
        _write_json_atomic(self.run_dir / "acquisition_manifest.json", manifest)

    def relative_run_path(self) -> str:
        return str(self.run_dir.relative_to(self.data_dir))


def _write_json_atomic(path: Path, data: Any) -> None:
    _write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _write_jsonl_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    content = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    _write_text_atomic(path, content)


def _write_csv_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    temporary_path = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            writer = csv.DictWriter(temporary, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for record in records:
                row = {
                    key: (
                        json.dumps(record.get(key), ensure_ascii=False)
                        if isinstance(record.get(key), list | dict)
                        else record.get(key)
                    )
                    for key in CSV_FIELDS
                }
                writer.writerow(row)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


def _write_text_atomic(path: Path, content: str) -> None:
    temporary_path = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
