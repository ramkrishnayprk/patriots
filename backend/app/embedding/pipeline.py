import hashlib
import json
import logging
import math
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import chromadb
import numpy as np
from chromadb.config import Settings as ChromaSettings

from app.embedding.model import load_local_model

logger = logging.getLogger(__name__)
RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
SCALAR_TYPES = (str, int, float, bool)


@dataclass(frozen=True)
class EmbeddingOptions:
    model_name: str
    model_path: Path
    embed_dim: int = 384
    normalize: bool = True
    batch_size: int = 64
    device: str = "auto"
    distance_metric: str = "cosine"
    query_instruction: str = "Represent this sentence for searching relevant passages: "
    passage_prefix: str = ""

    def validate(self) -> None:
        if not self.model_name:
            raise ValueError("model_name cannot be empty.")
        if self.embed_dim < 1:
            raise ValueError("embed_dim must be positive.")
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive.")
        if self.distance_metric != "cosine":
            raise ValueError("Only cosine distance is supported.")

    def contract(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "embed_dim": self.embed_dim,
            "normalize": self.normalize,
            "distance_metric": self.distance_metric,
            "query_instruction": self.query_instruction,
            "passage_prefix": self.passage_prefix,
        }

    def contract_hash(self) -> str:
        encoded = json.dumps(self.contract(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


def ingest_run(
    *,
    data_dir: Path,
    run_id: str,
    options: EmbeddingOptions,
    model: Any | None = None,
) -> dict[str, Any]:
    """Embed chunks.jsonl and atomically synchronize dense and sparse stores."""
    options.validate()
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id may contain only letters, numbers, hyphens, and underscores.")

    run_dir = Path(data_dir) / "runs" / run_id
    chunks_path = run_dir / "chunks.jsonl"
    if not chunks_path.is_file():
        raise FileNotFoundError(f"chunks.jsonl was not found for run {run_id}.")

    model = model or load_local_model(
        options.model_path,
        model_name=options.model_name,
        device=options.device,
    )
    actual_dimension = int(model.get_sentence_embedding_dimension())
    if actual_dimension != options.embed_dim:
        raise ValueError(
            f"Embedding dimension mismatch: model={actual_dimension}, "
            f"configured={options.embed_dim}."
        )

    contract_hash = options.contract_hash()
    vector_dir = run_dir / "vector_db"
    vector_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(vector_dir / "chroma"),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    collection_name = f"chunks_{contract_hash[:16]}"
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": options.distance_metric},
    )
    cache = _open_cache(Path(data_dir) / "embedding_cache.sqlite3")
    sparse_temporary = _temporary_path(run_dir, "bm25")
    sparse = _open_sparse_index(sparse_temporary)
    errors_path = run_dir / "embedding_errors.log"
    errors_temporary = _temporary_path(run_dir, "embedding-errors")

    current_ids: set[str] = set()
    generations: set[int] = set()
    embedded = 0
    reused = 0
    skipped = 0
    truncated = 0
    records_pending: list[dict[str, Any]] = []
    upserts_pending: list[tuple[dict[str, Any], list[float]]] = []

    try:
        with (
            chunks_path.open(encoding="utf-8") as source,
            errors_temporary.open("w", encoding="utf-8") as errors,
        ):
            for line_number, line in enumerate(source, start=1):
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError as exc:
                    skipped += 1
                    _write_error(errors, line_number, "invalid_json", error=str(exc))
                    continue
                prepared = _prepare_record(chunk, options)
                if isinstance(prepared, str):
                    skipped += 1
                    _write_error(errors, line_number, prepared)
                    continue
                if prepared["id"] in current_ids:
                    skipped += 1
                    _write_error(errors, line_number, "duplicate_chunk_id")
                    continue

                current_ids.add(prepared["id"])
                generations.add(prepared["generation"])
                sparse.execute(
                    "INSERT INTO chunks_fts(chunk_id, text) VALUES (?, ?)",
                    (prepared["id"], prepared["text"]),
                )
                sparse.execute(
                    "INSERT INTO chunk_metadata(chunk_id, metadata_json) VALUES (?, ?)",
                    (
                        prepared["id"],
                        json.dumps(prepared["metadata"], separators=(",", ":")),
                    ),
                )

                cached = _cache_get(cache, contract_hash, prepared["content_hash"])
                if cached is not None:
                    _validate_vector(cached, options.embed_dim, options.normalize)
                    upserts_pending.append((prepared, cached))
                    reused += 1
                else:
                    records_pending.append(prepared)

                if len(records_pending) >= options.batch_size:
                    vectors, batch_truncated = _encode_batch(model, records_pending, options)
                    truncated += batch_truncated
                    for record, vector in zip(records_pending, vectors, strict=True):
                        _cache_put(
                            cache,
                            contract_hash,
                            record["content_hash"],
                            vector,
                        )
                        upserts_pending.append((record, vector))
                        embedded += 1
                    records_pending = []

                if len(upserts_pending) >= options.batch_size:
                    _upsert(collection, upserts_pending)
                    upserts_pending = []

            if records_pending:
                vectors, batch_truncated = _encode_batch(model, records_pending, options)
                truncated += batch_truncated
                for record, vector in zip(records_pending, vectors, strict=True):
                    _cache_put(cache, contract_hash, record["content_hash"], vector)
                    upserts_pending.append((record, vector))
                    embedded += 1
            if upserts_pending:
                _upsert(collection, upserts_pending)

            errors.flush()
            os.fsync(errors.fileno())

        if not current_ids:
            raise ValueError("No valid chunks were available for embedding.")

        cache.commit()
        sparse.commit()
        existing_ids = set(collection.get(include=[])["ids"])
        stale_ids = sorted(existing_ids - current_ids)
        for start in range(0, len(stale_ids), options.batch_size):
            collection.delete(ids=stale_ids[start : start + options.batch_size])

        expected = len(current_ids)
        actual = collection.count()
        if actual != expected:
            raise ValueError(f"Vector parity failure: expected={expected}, actual={actual}.")

        smoke = _smoke_query(collection, model, options)
        sparse.close()
        sparse_temporary.replace(run_dir / "bm25.sqlite3")
        errors_temporary.replace(errors_path)

        previous_collection = _previous_collection(run_dir / "embedding_manifest.json")
        if previous_collection and previous_collection != collection_name:
            try:
                client.delete_collection(previous_collection)
            except ValueError:
                logger.warning("Previous Chroma collection was already absent.")

        generated_at = datetime.now(UTC).isoformat()
        report = {
            "run_id": run_id,
            "collection": collection_name,
            "contract_hash": contract_hash,
            "contract": options.contract(),
            "generation": max(generations),
            "input_chunks": expected,
            "embedded": embedded,
            "reused_from_cache": reused,
            "skipped": skipped,
            "truncated": truncated,
            "swept": len(stale_ids),
            "vector_count": actual,
            "vector_dimension": actual_dimension,
            "smoke_query": smoke,
            "generated_at": generated_at,
        }
        _write_json_atomic(run_dir / "embedding_report.json", report)
        _write_json_atomic(
            run_dir / "embedding_manifest.json",
            {
                "active_collection": collection_name,
                "contract_hash": contract_hash,
                "contract": options.contract(),
                "generation": max(generations),
                "generated_at": generated_at,
            },
        )
        logger.info("Embedding ingestion complete | %s", json.dumps(report))
        return report
    finally:
        cache.close()
        try:
            sparse.close()
        except sqlite3.Error:
            pass
        sparse_temporary.unlink(missing_ok=True)
        errors_temporary.unlink(missing_ok=True)


def _prepare_record(chunk: Any, options: EmbeddingOptions) -> dict[str, Any] | str:
    if not isinstance(chunk, dict):
        return "chunk_must_be_an_object"
    chunk_id = str(chunk.get("id") or "").strip()
    text = str(chunk.get("text") or "").strip()
    content_hash = str(chunk.get("content_hash") or "").strip()
    if not chunk_id:
        return "missing_chunk_id"
    if not text:
        return "empty_text"
    if not content_hash:
        return "missing_content_hash"
    if hashlib.sha256(text.encode()).hexdigest() != content_hash:
        return "content_hash_mismatch"
    try:
        generation = int(chunk["generation"])
        chunk_number = int(chunk["chunk_number"])
    except (KeyError, TypeError, ValueError):
        return "invalid_operational_metadata"

    metadata: dict[str, str | int | float | bool] = {
        "document_id": str(chunk.get("document_id") or ""),
        "imdb_id": str(chunk.get("document_id") or ""),
        "title": str(chunk.get("title") or ""),
        "section": str(chunk.get("section") or ""),
        "genres": ", ".join(str(value) for value in (chunk.get("genres") or [])),
        "url": str(chunk.get("url") or ""),
        "strategy": str(chunk.get("strategy") or ""),
        "generation": generation,
        "chunk_number": chunk_number,
        "content_hash": content_hash,
    }
    if chunk.get("year") is not None:
        metadata["year"] = int(chunk["year"])
    if chunk.get("imdb_rating") is not None:
        metadata["imdb_rating"] = float(chunk["imdb_rating"])
    quick_facts = chunk.get("quick_facts")
    if isinstance(quick_facts, dict):
        for key, value in quick_facts.items():
            if value is None:
                continue
            safe_key = re.sub(r"[^a-zA-Z0-9_]+", "_", str(key)).strip("_").lower()
            metadata[f"qf_{safe_key}"] = (
                value if isinstance(value, SCALAR_TYPES) else json.dumps(value)
            )
    return {
        "id": chunk_id,
        "text": f"{options.passage_prefix}{text}",
        "document": text,
        "content_hash": content_hash,
        "generation": generation,
        "metadata": metadata,
    }


def _encode_batch(
    model: Any,
    records: list[dict[str, Any]],
    options: EmbeddingOptions,
) -> tuple[list[list[float]], int]:
    texts = [record["text"] for record in records]
    truncated = _count_truncated(model, texts)
    encoded = model.encode(
        texts,
        batch_size=options.batch_size,
        normalize_embeddings=options.normalize,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    vectors = np.asarray(encoded, dtype=np.float32)
    output = []
    for vector in vectors:
        values = vector.tolist()
        _validate_vector(values, options.embed_dim, options.normalize)
        output.append(values)
    return output, truncated


def _count_truncated(model: Any, texts: list[str]) -> int:
    tokenizer = getattr(model, "tokenizer", None)
    maximum = int(getattr(model, "max_seq_length", 0) or 0)
    if tokenizer is None or maximum <= 0:
        return 0
    return sum(
        len(tokenizer.encode(text, add_special_tokens=True, truncation=False)) > maximum
        for text in texts
    )


def _validate_vector(vector: list[float], dimension: int, normalized: bool) -> None:
    if len(vector) != dimension:
        raise ValueError(f"Vector dimension mismatch: expected={dimension}, actual={len(vector)}.")
    if any(not math.isfinite(value) for value in vector):
        raise ValueError("Vector contains NaN or infinity.")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise ValueError("Vector is all zero.")
    if normalized and not math.isclose(norm, 1.0, rel_tol=1e-3, abs_tol=1e-3):
        raise ValueError(f"Vector is not normalized; norm={norm:.6f}.")


def _upsert(collection: Any, records: list[tuple[dict[str, Any], list[float]]]) -> None:
    collection.upsert(
        ids=[record["id"] for record, _vector in records],
        embeddings=[vector for _record, vector in records],
        documents=[record["document"] for record, _vector in records],
        metadatas=[record["metadata"] for record, _vector in records],
    )


def _smoke_query(collection: Any, model: Any, options: EmbeddingOptions) -> dict[str, Any]:
    instruction = options.query_instruction.strip()
    query = " ".join(part for part in [instruction, "movie plot and story"] if part)
    vector = model.encode(
        [query],
        normalize_embeddings=options.normalize,
        convert_to_numpy=True,
        show_progress_bar=False,
    )[0].tolist()
    _validate_vector(vector, options.embed_dim, options.normalize)
    result = collection.query(
        query_embeddings=[vector],
        n_results=min(5, collection.count()),
        include=["metadatas", "distances"],
    )
    metadatas = result.get("metadatas", [[]])[0]
    hits = [
        {
            "title": metadata.get("title", ""),
            "url": metadata.get("url", ""),
            "distance": result.get("distances", [[]])[0][index],
        }
        for index, metadata in enumerate(metadatas)
    ]
    return {"query": "movie plot and story", "sensible": bool(hits), "hits": hits}


def _open_cache(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS embeddings ("
        "contract_hash TEXT NOT NULL, content_hash TEXT NOT NULL, "
        "vector_json TEXT NOT NULL, PRIMARY KEY(contract_hash, content_hash))"
    )
    return connection


def _cache_get(
    cache: sqlite3.Connection, contract_hash: str, content_hash: str
) -> list[float] | None:
    row = cache.execute(
        "SELECT vector_json FROM embeddings WHERE contract_hash=? AND content_hash=?",
        (contract_hash, content_hash),
    ).fetchone()
    return json.loads(row[0]) if row else None


def _cache_put(
    cache: sqlite3.Connection,
    contract_hash: str,
    content_hash: str,
    vector: list[float],
) -> None:
    cache.execute(
        "INSERT OR REPLACE INTO embeddings VALUES (?, ?, ?)",
        (contract_hash, content_hash, json.dumps(vector, separators=(",", ":"))),
    )


def _open_sparse_index(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE VIRTUAL TABLE chunks_fts "
        "USING fts5(chunk_id UNINDEXED, text, tokenize='porter unicode61')"
    )
    connection.execute(
        "CREATE TABLE chunk_metadata (chunk_id TEXT PRIMARY KEY, metadata_json TEXT NOT NULL)"
    )
    return connection


def _temporary_path(directory: Path, prefix: str) -> Path:
    with NamedTemporaryFile(
        dir=directory, prefix=f".{prefix}.", suffix=".tmp", delete=False
    ) as temporary:
        return Path(temporary.name)


def _write_error(output, line_number: int, reason: str, **details: Any) -> None:
    output.write(
        json.dumps(
            {"line_number": line_number, "reason": reason, **details},
            separators=(",", ":"),
        )
        + "\n"
    )


def _previous_collection(manifest_path: Path) -> str | None:
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8")).get("active_collection")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def _write_json_atomic(path: Path, data: Any) -> None:
    temporary = _temporary_path(path.parent, path.stem)
    try:
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
