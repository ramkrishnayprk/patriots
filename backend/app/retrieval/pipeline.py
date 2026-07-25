import hashlib
import json
import math
import re
import sqlite3
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
import numpy as np
from chromadb.config import Settings as ChromaSettings

from app.embedding.model import load_local_model, load_local_reranker
from app.embedding.pipeline import RUN_ID_PATTERN

KNOWN_GENRES = (
    "Action",
    "Adventure",
    "Animation",
    "Comedy",
    "Crime",
    "Documentary",
    "Drama",
    "Family",
    "Fantasy",
    "History",
    "Horror",
    "Music",
    "Mystery",
    "Romance",
    "Science Fiction",
    "Thriller",
    "War",
    "Western",
)
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class RetrievalOptions:
    model_name: str
    reranker_model_name: str
    model_path: Path
    embed_dim: int = 384
    normalize: bool = True
    device: str = "auto"
    query_instruction: str = "Represent this sentence for searching relevant passages: "
    passage_prefix: str = ""
    top_k_dense: int = 20
    top_k_sparse: int = 20
    rrf_k: int = 60
    rerank_top_n: int = 30
    final_k: int = 5
    confidence_threshold: float = 0.01
    max_per_document: int = 2
    max_query_chars: int = 1000
    enable_filters: bool = True

    def validate(self) -> None:
        integer_fields = {
            "embed_dim": self.embed_dim,
            "top_k_dense": self.top_k_dense,
            "top_k_sparse": self.top_k_sparse,
            "rrf_k": self.rrf_k,
            "rerank_top_n": self.rerank_top_n,
            "final_k": self.final_k,
            "max_per_document": self.max_per_document,
            "max_query_chars": self.max_query_chars,
        }
        for name, value in integer_fields.items():
            if value < 1:
                raise ValueError(f"{name} must be positive.")
        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1.")


def search_run(
    *,
    data_dir: Path,
    run_id: str,
    query: str,
    options: RetrievalOptions,
    embedding_model: Any | None = None,
    reranker: Any | None = None,
) -> dict[str, Any]:
    """Search one run's dense and sparse indexes and rerank the fused candidates."""
    started = time.perf_counter()
    options.validate()
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id may contain only letters, numbers, hyphens, and underscores.")
    if not isinstance(query, str):
        raise ValueError("query must be a string.")

    original_query = query
    normalized_query = _normalize_query(query)
    was_truncated = len(normalized_query) > options.max_query_chars
    normalized_query = normalized_query[: options.max_query_chars].rstrip()
    diagnostics: dict[str, Any] = {
        "candidates": {
            "dense": 0,
            "sparse": 0,
            "fused": 0,
            "reranked": 0,
            "after_deduplication": 0,
            "returned": 0,
        },
        "filters": {
            "requested": {},
            "applied": False,
            "relaxed": False,
        },
        "degradations": [],
        "query_truncated": was_truncated,
    }
    if not normalized_query:
        diagnostics["latency_ms"] = _elapsed_ms(started)
        return _response(
            status="no_results",
            original_query=original_query,
            normalized_query=normalized_query,
            results=[],
            diagnostics=diagnostics,
        )

    run_dir = Path(data_dir) / "runs" / run_id
    manifest = _load_manifest(run_dir)
    _validate_contract(manifest, options)
    sparse_path = run_dir / "bm25.sqlite3"
    if not sparse_path.is_file():
        raise FileNotFoundError(f"bm25.sqlite3 was not found for run {run_id}.")

    embedding_model = embedding_model or load_local_model(
        options.model_path,
        model_name=options.model_name,
        device=options.device,
    )
    reranker = reranker or load_local_reranker(
        options.model_path,
        model_name=options.reranker_model_name,
    )
    collection = _load_collection(run_dir, manifest["active_collection"])
    filters = _parse_filters(normalized_query) if options.enable_filters else {}
    diagnostics["filters"]["requested"] = filters

    dense_hits = _dense_search(
        collection=collection,
        query=normalized_query,
        filters=filters,
        options=options,
        model=embedding_model,
    )
    sparse_hits = _sparse_search(
        path=sparse_path,
        query=normalized_query,
        filters=filters,
        limit=options.top_k_sparse,
    )

    if filters and not dense_hits and not sparse_hits:
        diagnostics["filters"]["relaxed"] = True
        diagnostics["degradations"].append("metadata_filters_relaxed")
        dense_hits = _dense_search(
            collection=collection,
            query=normalized_query,
            filters={},
            options=options,
            model=embedding_model,
        )
        sparse_hits = _sparse_search(
            path=sparse_path,
            query=normalized_query,
            filters={},
            limit=options.top_k_sparse,
        )
    elif filters:
        diagnostics["filters"]["applied"] = True

    diagnostics["candidates"]["dense"] = len(dense_hits)
    diagnostics["candidates"]["sparse"] = len(sparse_hits)
    fused = _reciprocal_rank_fusion(dense_hits, sparse_hits, options.rrf_k)
    diagnostics["candidates"]["fused"] = len(fused)
    rerank_candidates = fused[: options.rerank_top_n]

    if not rerank_candidates:
        diagnostics["latency_ms"] = _elapsed_ms(started)
        return _response(
            status="no_results",
            original_query=original_query,
            normalized_query=normalized_query,
            results=[],
            diagnostics=diagnostics,
        )

    raw_scores = reranker.rerank(
        original_query[: options.max_query_chars],
        [candidate["text"] for candidate in rerank_candidates],
    )
    if len(raw_scores) != len(rerank_candidates):
        raise ValueError("Reranker returned a different number of scores than candidates.")
    for candidate, raw_score in zip(rerank_candidates, raw_scores, strict=True):
        score = float(raw_score)
        if not math.isfinite(score):
            raise ValueError("Reranker returned a non-finite score.")
        candidate["rerank_score"] = score
        candidate["score"] = _sigmoid(score)

    diagnostics["candidates"]["reranked"] = len(rerank_candidates)
    ranked = sorted(
        rerank_candidates,
        key=lambda item: (
            -item["score"],
            item["document_id"],
            int(item.get("chunk_number", 0)),
            item["id"],
        ),
    )
    ranked = _remove_duplicates(ranked)
    diagnostics["candidates"]["after_deduplication"] = len(ranked)
    ranked = _apply_diversity(ranked, options.max_per_document)
    final = ranked[: options.final_k]
    diagnostics["candidates"]["returned"] = len(final)

    results = [_public_result(item, rank) for rank, item in enumerate(final, start=1)]
    status = (
        "ok"
        if results and results[0]["score"] >= options.confidence_threshold
        else "low_confidence"
    )
    diagnostics["confidence_threshold"] = options.confidence_threshold
    diagnostics["latency_ms"] = _elapsed_ms(started)
    return _response(
        status=status,
        original_query=original_query,
        normalized_query=normalized_query,
        results=results,
        diagnostics=diagnostics,
    )


def _dense_search(
    *,
    collection: Any,
    query: str,
    filters: dict[str, Any],
    options: RetrievalOptions,
    model: Any,
) -> list[dict[str, Any]]:
    count = int(collection.count())
    if count == 0:
        return []
    instruction = options.query_instruction.strip()
    embedded_query = " ".join(part for part in (instruction, query) if part)
    vector = np.asarray(
        model.encode(
            [embedded_query],
            normalize_embeddings=options.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0],
        dtype=np.float32,
    )
    if vector.shape != (options.embed_dim,):
        raise ValueError(
            f"Query vector dimension mismatch: expected={options.embed_dim}, "
            f"actual={vector.size}."
        )
    fetch_limit = (
        min(count, max(options.top_k_dense * 10, 100))
        if filters
        else min(options.top_k_dense, count)
    )
    result = collection.query(
        query_embeddings=[vector.tolist()],
        n_results=fetch_limit,
        include=["documents", "metadatas", "distances"],
    )
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    output = []
    for index, chunk_id in enumerate(ids):
        metadata = metadatas[index] or {}
        if filters and not _metadata_matches(metadata, filters):
            continue
        output.append(
            _candidate(
                chunk_id=chunk_id,
                text=documents[index] or "",
                metadata=metadata,
                dense_score=max(0.0, min(1.0, 1.0 - float(distances[index]))),
                dense_rank=len(output) + 1,
            )
        )
        if len(output) >= options.top_k_dense:
            break
    return output


def _sparse_search(
    *, path: Path, query: str, filters: dict[str, Any], limit: int
) -> list[dict[str, Any]]:
    tokens = list(dict.fromkeys(TOKEN_PATTERN.findall(query.lower())))
    if not tokens:
        return []
    match_query = " OR ".join(f'"{token}"' for token in tokens)
    fetch_limit = limit if not filters else max(limit * 10, 100)
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT f.chunk_id, f.text, m.metadata_json, bm25(chunks_fts) "
            "FROM chunks_fts AS f JOIN chunk_metadata AS m USING(chunk_id) "
            "WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts), f.chunk_id LIMIT ?",
            (match_query, fetch_limit),
        ).fetchall()
    finally:
        connection.close()
    output = []
    for chunk_id, text, metadata_json, bm25_score in rows:
        metadata = json.loads(metadata_json)
        if filters and not _metadata_matches(metadata, filters):
            continue
        output.append(
            _candidate(
                chunk_id=chunk_id,
                text=text,
                metadata=metadata,
                sparse_rank=len(output) + 1,
                sparse_score=float(bm25_score),
            )
        )
        if len(output) >= limit:
            break
    return output


def _reciprocal_rank_fusion(
    dense: list[dict[str, Any]], sparse: list[dict[str, Any]], rrf_k: int
) -> list[dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    for source in (dense, sparse):
        for item in source:
            existing = combined.setdefault(item["id"], item.copy())
            existing.update(
                {key: value for key, value in item.items() if value is not None}
            )
    for item in combined.values():
        score = 0.0
        if item.get("dense_rank") is not None:
            score += 1 / (rrf_k + item["dense_rank"])
        if item.get("sparse_rank") is not None:
            score += 1 / (rrf_k + item["sparse_rank"])
        item["rrf_score"] = score
    return sorted(
        combined.values(),
        key=lambda item: (-item["rrf_score"], item["id"]),
    )


def _candidate(
    *,
    chunk_id: str,
    text: str,
    metadata: dict[str, Any],
    dense_score: float | None = None,
    dense_rank: int | None = None,
    sparse_score: float | None = None,
    sparse_rank: int | None = None,
) -> dict[str, Any]:
    quick_facts = {
        key[3:]: value for key, value in metadata.items() if key.startswith("qf_")
    }
    return {
        "id": chunk_id,
        "document_id": str(metadata.get("document_id") or ""),
        "title": str(metadata.get("title") or ""),
        "imdb_id": str(metadata.get("imdb_id") or metadata.get("document_id") or ""),
        "year": metadata.get("year"),
        "genres": [
            value.strip()
            for value in str(metadata.get("genres") or "").split(",")
            if value.strip()
        ],
        "imdb_rating": metadata.get("imdb_rating"),
        "section": str(metadata.get("section") or ""),
        "url": str(metadata.get("url") or ""),
        "text": text,
        "quick_facts": quick_facts,
        "content_hash": str(
            metadata.get("content_hash") or hashlib.sha256(text.encode()).hexdigest()
        ),
        "chunk_number": int(metadata.get("chunk_number") or 0),
        "dense_score": dense_score,
        "dense_rank": dense_rank,
        "sparse_score": sparse_score,
        "sparse_rank": sparse_rank,
    }


def _public_result(item: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "score": round(item["score"], 6),
        "id": item["id"],
        "document_id": item["document_id"],
        "title": item["title"],
        "imdb_id": item["imdb_id"],
        "year": item["year"],
        "genres": item["genres"],
        "imdb_rating": item["imdb_rating"],
        "section": item["section"],
        "url": item["url"],
        "text": item["text"],
        "quick_facts": item["quick_facts"],
        "dense_score": (
            round(item["dense_score"], 6) if item.get("dense_score") is not None else None
        ),
        "sparse_rank": item.get("sparse_rank"),
        "rerank_score": round(item["rerank_score"], 6),
    }


def _remove_duplicates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    hashes: set[str] = set()
    normalized_texts: list[str] = []
    for item in items:
        if item["content_hash"] in hashes:
            continue
        normalized = _normalize_query(item["text"]).lower()
        is_near_duplicate = any(
            min(len(normalized), len(previous)) >= 0.8 * max(len(normalized), len(previous))
            and (normalized in previous or previous in normalized)
            for previous in normalized_texts
            if normalized and previous
        )
        if is_near_duplicate:
            continue
        hashes.add(item["content_hash"])
        normalized_texts.append(normalized)
        kept.append(item)
    return kept


def _apply_diversity(
    items: list[dict[str, Any]], max_per_document: int
) -> list[dict[str, Any]]:
    counts: defaultdict[str, int] = defaultdict(int)
    preferred = []
    for item in items:
        document_id = item["document_id"] or item["id"]
        if counts[document_id] < max_per_document:
            preferred.append(item)
            counts[document_id] += 1
    return preferred


def _parse_filters(query: str) -> dict[str, Any]:
    lowered = query.lower()
    filters: dict[str, Any] = {}
    for genre in KNOWN_GENRES:
        if genre.lower() in lowered:
            filters["genres"] = genre
            break
    if re.search(r"\bsci[\s-]?fi\b", lowered):
        filters["genres"] = "Science Fiction"
    year = re.search(r"\b(19\d{2}|20\d{2})\b", lowered)
    if year:
        filters["year"] = int(year.group(1))
    rating = re.search(
        r"\b(?:imdb\s+)?rat(?:ed|ing)?\s*(?:>=|>|at least|above|over)\s*"
        r"(\d(?:\.\d+)?)",
        lowered,
    )
    if rating:
        filters["min_imdb_rating"] = float(rating.group(1))
    return filters


def _metadata_matches(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        if key == "min_imdb_rating":
            try:
                if float(metadata.get("imdb_rating")) < expected:
                    return False
            except (TypeError, ValueError):
                return False
            continue
        if key == "year":
            if metadata.get("year") != expected:
                return False
            continue
        actual = str(metadata.get(key) or "").lower()
        if str(expected).lower() not in actual:
            return False
    return True


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "embedding_manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"embedding_manifest.json was not found for run {run_dir.name}.")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("embedding_manifest.json contains invalid JSON.") from exc
    if not isinstance(manifest, dict) or not manifest.get("active_collection"):
        raise ValueError("Embedding manifest does not name an active collection.")
    return manifest


def _validate_contract(manifest: dict[str, Any], options: RetrievalOptions) -> None:
    contract = manifest.get("contract")
    if not isinstance(contract, dict):
        raise ValueError("Embedding manifest is missing its query contract.")
    expected = {
        "model_name": options.model_name,
        "embed_dim": options.embed_dim,
        "normalize": options.normalize,
        "passage_prefix": options.passage_prefix,
    }
    mismatches = [
        name for name, value in expected.items() if contract.get(name) != value
    ]
    stored_instruction = str(contract.get("query_instruction") or "").strip()
    if stored_instruction != options.query_instruction.strip():
        mismatches.append("query_instruction")
    if mismatches:
        raise ValueError(
            "Retrieval configuration does not match the embedded index: "
            + ", ".join(mismatches)
            + "."
        )


def _load_collection(run_dir: Path, collection_name: str) -> Any:
    chroma_path = run_dir / "vector_db" / "chroma"
    if not chroma_path.is_dir():
        raise FileNotFoundError(f"Chroma database was not found for run {run_dir.name}.")
    client = chromadb.PersistentClient(
        path=str(chroma_path),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    try:
        return client.get_collection(collection_name)
    except Exception as exc:
        raise ValueError(
            f"Active Chroma collection {collection_name} could not be opened."
        ) from exc


def _normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1 + exponential)


def _response(
    *,
    status: str,
    original_query: str,
    normalized_query: str,
    results: list[dict[str, Any]],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": status,
        "query": {
            "original": original_query,
            "normalized": normalized_query,
        },
        "results": results,
        "diagnostics": diagnostics,
    }


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)
