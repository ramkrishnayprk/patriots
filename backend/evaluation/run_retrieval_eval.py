#!/usr/bin/env python3
"""Run reproducible offline retrieval baselines against a validated golden CSV."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import chromadb
import numpy as np
from chromadb.config import Settings as ChromaSettings

from app.config import Settings
from app.embedding.model import load_local_model, load_local_reranker
from app.retrieval.pipeline import (
    RetrievalOptions,
    _dense_search,
    _load_collection,
    _sparse_search,
    search_run,
)

SEPARATOR = " || "
BASELINES = ("B0_closed_book_refusal", "B1_bm25", "B2_dense_naive", "B3_final")


def _parts(value: str) -> list[str]:
    return [part.strip() for part in value.split(SEPARATOR) if part.strip()]


def _read_golden(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        rows = list(csv.DictReader(source))
    for row in rows:
        row["answerable_bool"] = row["answerable"].strip().lower() == "true"
        row["gold_ids"] = _parts(row["gold_document_ids"])
    return rows


def _read_documents(path: Path) -> list[dict[str, Any]]:
    documents = []
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                documents.append(json.loads(line))
    return documents


def _options(settings: Settings, *, final_k: int = 20) -> RetrievalOptions:
    return RetrievalOptions(
        model_name=settings.embedding_model_name,
        reranker_model_name=settings.reranker_model_name,
        model_path=settings.embedding_model_path,
        embed_dim=settings.embedding_dimension,
        normalize=settings.embedding_normalize,
        device=settings.embedding_device,
        query_instruction=settings.embedding_query_instruction,
        passage_prefix=settings.embedding_passage_prefix,
        top_k_dense=max(20, settings.retrieval_top_k_dense),
        top_k_sparse=max(20, settings.retrieval_top_k_sparse),
        rrf_k=settings.retrieval_rrf_k,
        rerank_top_n=max(30, settings.retrieval_rerank_top_n),
        final_k=final_k,
        confidence_threshold=settings.retrieval_confidence_threshold,
        max_per_document=max(5, settings.retrieval_max_per_document),
        max_query_chars=settings.retrieval_max_query_chars,
        enable_filters=settings.retrieval_enable_filters,
    )


def _naive_chunks(documents: list[dict[str, Any]], size: int = 1200) -> list[dict[str, Any]]:
    chunks = []
    for document in documents:
        text = str(document.get("text") or "").strip()
        if not text:
            continue
        for number, start in enumerate(range(0, len(text), size)):
            chunk_text = text[start : start + size].strip()
            if not chunk_text:
                continue
            chunks.append(
                {
                    "id": f"{document['id']}::naive::{number}",
                    "text": chunk_text,
                    "metadata": {
                        "document_id": str(document["id"]),
                        "title": str(document.get("title") or ""),
                        "year": document.get("year") or 0,
                        "genres": ", ".join(document.get("genres") or []),
                        "imdb_rating": document.get("imdb_rating") or 0.0,
                        "section": "naive_window",
                        "url": str(document.get("url") or ""),
                        "chunk_number": number,
                    },
                }
            )
    return chunks


def _build_naive_collection(
    documents: list[dict[str, Any]],
    model: Any,
    settings: Settings,
) -> Any:
    client = chromadb.EphemeralClient(
        settings=ChromaSettings(anonymized_telemetry=False)
    )
    collection = client.create_collection(
        "naive_chunks",
        metadata={"hnsw:space": settings.embedding_distance_metric},
    )
    chunks = _naive_chunks(documents)
    for start in range(0, len(chunks), settings.embedding_batch_size):
        batch = chunks[start : start + settings.embedding_batch_size]
        texts = [item["text"] for item in batch]
        vectors = np.asarray(
            model.encode(
                texts,
                batch_size=settings.embedding_batch_size,
                normalize_embeddings=settings.embedding_normalize,
                convert_to_numpy=True,
                show_progress_bar=False,
            ),
            dtype=np.float32,
        )
        collection.add(
            ids=[item["id"] for item in batch],
            documents=texts,
            metadatas=[item["metadata"] for item in batch],
            embeddings=vectors.tolist(),
        )
    return collection


def _unique_document_ids(candidates: list[dict[str, Any]]) -> list[str]:
    seen = set()
    output = []
    for candidate in candidates:
        document_id = str(candidate.get("document_id") or "")
        if document_id and document_id not in seen:
            seen.add(document_id)
            output.append(document_id)
    return output


def _dcg(relevances: list[int]) -> float:
    return sum(value / math.log2(index + 2) for index, value in enumerate(relevances))


def _item_metrics(
    *,
    gold_ids: list[str],
    ranked_ids: list[str],
    answerable: bool,
    refused: bool,
) -> dict[str, float | None]:
    if not answerable:
        return {
            "recall_at_5": None,
            "recall_at_20": None,
            "reciprocal_rank": None,
            "ndcg_at_10": None,
            "answer_support_at_5": None,
            "citation_valid_at_5": None,
            "correct_refusal": float(refused),
            "over_refusal": None,
        }

    gold = set(gold_ids)
    top5 = ranked_ids[:5]
    top20 = ranked_ids[:20]
    ranks = [index + 1 for index, item in enumerate(ranked_ids) if item in gold]
    ideal = _dcg([1] * min(len(gold), 10))
    actual = _dcg([int(item in gold) for item in ranked_ids[:10]])
    return {
        "recall_at_5": len(gold.intersection(top5)) / len(gold),
        "recall_at_20": len(gold.intersection(top20)) / len(gold),
        "reciprocal_rank": 1 / min(ranks) if ranks else 0.0,
        "ndcg_at_10": actual / ideal if ideal else 0.0,
        "answer_support_at_5": float(gold.issubset(top5)),
        "citation_valid_at_5": float(bool(gold.intersection(top5))),
        "correct_refusal": None,
        "over_refusal": float(refused),
    }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _mean_present(rows: list[dict[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return statistics.fmean(values) if values else 0.0


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    latencies = [float(row["latency_ms"]) for row in rows]
    return {
        "queries": len(rows),
        "recall_at_5": _mean_present(rows, "recall_at_5"),
        "recall_at_20": _mean_present(rows, "recall_at_20"),
        "mrr": _mean_present(rows, "reciprocal_rank"),
        "ndcg_at_10": _mean_present(rows, "ndcg_at_10"),
        "answer_correctness_proxy": _mean_present(rows, "answer_support_at_5"),
        "citation_validity_proxy": _mean_present(rows, "citation_valid_at_5"),
        "correct_refusal_rate": _mean_present(rows, "correct_refusal"),
        "over_refusal_rate": _mean_present(rows, "over_refusal"),
        "latency_p50_ms": _percentile(latencies, 0.50),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "cost_per_query_usd": 0.0,
    }


def _bootstrap_delta(
    paired: list[tuple[float, float]], *, samples: int = 5000
) -> dict[str, float]:
    rng = random.Random(20260725)
    observed = statistics.fmean(final - baseline for baseline, final in paired)
    deltas = []
    for _ in range(samples):
        sample = [paired[rng.randrange(len(paired))] for _ in paired]
        deltas.append(statistics.fmean(final - baseline for baseline, final in sample))
    return {
        "delta": observed,
        "ci95_low": _percentile(deltas, 0.025),
        "ci95_high": _percentile(deltas, 0.975),
        "bootstrap_samples": samples,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--run-id", default="combined-movies")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dense-refusal-threshold", type=float, default=0.50)
    args = parser.parse_args()

    settings = Settings.from_env()
    run_dir = args.data_dir / "runs" / args.run_id
    golden = _read_golden(args.golden)
    documents = _read_documents(run_dir / "documents.jsonl")
    options = _options(settings)
    model = load_local_model(
        settings.embedding_model_path,
        model_name=settings.embedding_model_name,
        device=settings.embedding_device,
    )
    reranker = load_local_reranker(
        settings.embedding_model_path,
        model_name=settings.reranker_model_name,
    )
    manifest = json.loads((run_dir / "embedding_manifest.json").read_text())
    final_collection = _load_collection(run_dir, manifest["active_collection"])
    naive_collection = _build_naive_collection(documents, model, settings)
    bm25_path = run_dir / "bm25.sqlite3"

    per_item: list[dict[str, Any]] = []
    for item in golden:
        query = item["question"]
        answerable = bool(item["answerable_bool"])
        gold_ids = item["gold_ids"]

        for baseline in BASELINES:
            started = time.perf_counter()
            if baseline == "B0_closed_book_refusal":
                candidates: list[dict[str, Any]] = []
                status = "refused"
                refused = True
            elif baseline == "B1_bm25":
                candidates = _sparse_search(
                    path=bm25_path,
                    query=query,
                    filters={},
                    limit=20,
                )
                status = "ok" if candidates else "no_results"
                refused = not candidates
            elif baseline == "B2_dense_naive":
                candidates = _dense_search(
                    collection=naive_collection,
                    query=query,
                    filters={},
                    options=options,
                    model=model,
                )
                top_score = float(candidates[0].get("dense_score") or 0) if candidates else 0
                refused = top_score < args.dense_refusal_threshold
                status = "low_confidence" if refused else "ok"
            else:
                result = search_run(
                    data_dir=args.data_dir,
                    run_id=args.run_id,
                    query=query,
                    options=options,
                    embedding_model=model,
                    reranker=reranker,
                )
                candidates = result["results"]
                status = str(result["status"])
                refused = status != "ok"

            latency_ms = (time.perf_counter() - started) * 1000
            ranked_ids = _unique_document_ids(candidates)
            metrics = _item_metrics(
                gold_ids=gold_ids,
                ranked_ids=ranked_ids,
                answerable=answerable,
                refused=refused,
            )
            per_item.append(
                {
                    "id": item["id"],
                    "category": item["category"],
                    "split": item["split"],
                    "baseline": baseline,
                    "answerable": answerable,
                    "status": status,
                    "latency_ms": round(latency_ms, 3),
                    "gold_document_ids": SEPARATOR.join(gold_ids),
                    "top_20_document_ids": SEPARATOR.join(ranked_ids[:20]),
                    **metrics,
                }
            )

    metrics: dict[str, Any] = {
        "run_id": args.run_id,
        "items": len(golden),
        "evaluation_status": "exploratory_unverified_gold",
        "notes": [
            "B0 is an offline always-refuse control, not an LLM closed-book run.",
            "Answer correctness and citation validity are retrieval-support proxies.",
            "Refusal metrics use retrieval-gate decisions; no paid generation calls were made.",
            "The test split is exploratory and must be rerun once after human verification.",
        ],
        "baselines": {},
    }
    for baseline in BASELINES:
        baseline_rows = [row for row in per_item if row["baseline"] == baseline]
        metrics["baselines"][baseline] = {
            "all": _aggregate(baseline_rows),
            "dev": _aggregate([row for row in baseline_rows if row["split"] == "dev"]),
            "test": _aggregate([row for row in baseline_rows if row["split"] == "test"]),
        }

    answerable_pairs = []
    for item in golden:
        if not item["answerable_bool"]:
            continue
        baseline_row = next(
            row
            for row in per_item
            if row["id"] == item["id"] and row["baseline"] == "B2_dense_naive"
        )
        final_row = next(
            row
            for row in per_item
            if row["id"] == item["id"] and row["baseline"] == "B3_final"
        )
        answerable_pairs.append(
            (
                float(baseline_row["answer_support_at_5"]),
                float(final_row["answer_support_at_5"]),
            )
        )
    metrics["uncertainty"] = {
        "B3_minus_B2_answer_correctness_proxy": _bootstrap_delta(answerable_pairs)
    }
    metrics["b0_incorrect_subset"] = {
        "items": len(answerable_pairs),
        "definition": "All answerable items because the offline B0 control refused all.",
        "B3_answer_correctness_proxy": metrics["baselines"]["B3_final"]["all"][
            "answer_correctness_proxy"
        ],
    }

    failures = []
    for row in per_item:
        if row["baseline"] == "B0_closed_book_refusal":
            continue
        if row["answerable"] and float(row["answer_support_at_5"] or 0) < 1:
            top20 = _parts(str(row["top_20_document_ids"]))
            gold = _parts(str(row["gold_document_ids"]))
            label = (
                "rank_failure"
                if set(gold).intersection(top20)
                else "retrieval_miss"
            )
            if bool(row["over_refusal"]):
                label = "over_refusal"
            failures.append(
                {
                    "id": row["id"],
                    "baseline": row["baseline"],
                    "error_label": label,
                    "status": row["status"],
                    "gold_document_ids": row["gold_document_ids"],
                    "top_20_document_ids": row["top_20_document_ids"],
                }
            )
        elif not row["answerable"] and not bool(row["correct_refusal"]):
            failures.append(
                {
                    "id": row["id"],
                    "baseline": row["baseline"],
                    "error_label": "hallucination_risk_no_refusal",
                    "status": row["status"],
                    "gold_document_ids": "",
                    "top_20_document_ids": row["top_20_document_ids"],
                }
            )
    metrics["error_analysis"] = {
        "labeled_failures": min(15, len(failures)),
        "source": "First 15 deterministic failures across B1-B3.",
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(args.output_dir / "per_item_results.csv", per_item)
    _write_csv(args.output_dir / "error_analysis.csv", failures[:15])
    (args.output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n",
        encoding="utf-8",
    )
    summary_rows = []
    for baseline, values in metrics["baselines"].items():
        summary_rows.append({"baseline": baseline, **values["all"]})
    _write_csv(args.output_dir / "metrics.csv", summary_rows)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
