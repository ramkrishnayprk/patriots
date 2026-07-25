import json
from pathlib import Path
from typing import Any, Protocol

from app.structured.normalization import normalize_movie_record


class StructuredRecordRepository(Protocol):
    """Storage boundary implemented by JSONL now and replaceable by SQL/API later."""

    def list_records(self) -> list[dict[str, Any]]: ...


class JsonlMovieRepository:
    def __init__(self, path: Path):
        self.path = Path(path)

    def list_records(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            raise FileNotFoundError(f"Structured movie records were not found at {self.path}.")
        records = []
        with self.path.open(encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"{self.path.name} contains invalid JSON on line {line_number}."
                    ) from exc
                if not isinstance(record, dict):
                    raise ValueError(
                        f"Structured movie record {line_number} must be a JSON object."
                    )
                normalized = normalize_movie_record(record)
                if normalized["imdb_id"] and normalized["title"]:
                    records.append(normalized)
        return records


def create_structured_repository(
    *,
    backend: str,
    records_path: Path,
) -> StructuredRecordRepository:
    if backend == "jsonl":
        return JsonlMovieRepository(records_path)
    raise ValueError(f"Unsupported structured repository backend: {backend}.")
