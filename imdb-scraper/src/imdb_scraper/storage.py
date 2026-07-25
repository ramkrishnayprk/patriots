from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"completed": [], "failed": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"completed": [], "failed": []}
    return value if isinstance(value, dict) else {"completed": [], "failed": []}
