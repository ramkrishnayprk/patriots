import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class QueryLogStore:
    """Append-only local query log for retrieval-miss review."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "id": str(uuid4()),
            "created_at": datetime.now(UTC).isoformat(),
            "review_status": "unreviewed",
            **record,
        }
        payload = (
            json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        descriptor = os.open(
            self.path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return entry

    def list_recent(
        self,
        *,
        limit: int = 100,
        decision: str | None = None,
        triage_bucket: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        entries = []
        with self.path.open(encoding="utf-8") as source:
            for line in source:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                if decision and entry.get("decision") != decision:
                    continue
                if triage_bucket and entry.get("triage_bucket") != triage_bucket:
                    continue
                entries.append(entry)
        return entries[-limit:][::-1]
