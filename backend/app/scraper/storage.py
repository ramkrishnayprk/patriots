import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app.scraper.url_utils import safe_filename


class RunStorage:
    def __init__(self, data_dir: Path, run_id: str):
        safe_run_id = re.sub(r"[^a-zA-Z0-9_-]", "_", run_id)
        if not safe_run_id:
            raise ValueError("Run ID cannot be empty.")
        self.data_dir = Path(data_dir)
        self.run_dir = self.data_dir / "runs" / safe_run_id
        self.raw_html_dir = self.run_dir / "raw_html"
        self.programs_file = self.run_dir / "programs.json"
        self.documents_file = self.run_dir / "documents.jsonl"
        self.chunks_file = self.run_dir / "chunks.jsonl"
        self.failed_urls_file = self.run_dir / "failed_urls.json"
        self.discovered_urls_file = self.run_dir / "discovered_urls.json"
        self.raw_html_dir.mkdir(parents=True, exist_ok=True)

    def save_raw_html(self, url: str, html: str) -> Path:
        destination = self.raw_html_dir / safe_filename(url)
        _write_text_atomic(destination, html)
        return destination

    def save_checkpoint(
        self,
        *,
        programs: list[dict[str, Any]],
        chunks: list[dict[str, Any]],
        failed_urls: list[dict[str, Any]],
        discovered_urls: set[str],
    ) -> None:
        _write_json_atomic(self.programs_file, programs)
        _write_jsonl_atomic(self.documents_file, programs)
        _write_jsonl_atomic(self.chunks_file, chunks)
        _write_json_atomic(self.failed_urls_file, failed_urls)
        _write_json_atomic(self.discovered_urls_file, sorted(discovered_urls))

    def relative_run_path(self) -> str:
        return str(self.run_dir.relative_to(self.data_dir))


def _write_json_atomic(path: Path, data: Any) -> None:
    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    _write_text_atomic(path, content)


def _write_jsonl_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    content = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records
    )
    _write_text_atomic(path, content)


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    except OSError:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
        raise
