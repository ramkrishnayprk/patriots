#!/usr/bin/env python3
"""Measure retrieval-gate refusal behavior on entirely unrelated queries."""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import time
from pathlib import Path
from typing import Any

from app.config import Settings
from app.embedding.model import load_local_model, load_local_reranker
from app.retrieval.pipeline import _dense_search, _sparse_search, search_run
from run_retrieval_eval import (
    BASELINES,
    _build_naive_collection,
    _load_collection,
    _options,
    _percentile,
    _read_documents,
    _unique_document_ids,
    _write_csv,
)


def _read_queries(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        return list(csv.DictReader(source))


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, float | int | None]:
    latencies = [float(row["latency_ms"]) for row in rows]
    refused = [float(row["correct_refusal"]) for row in rows]
    return {
        "queries": len(rows),
        "recall_at_5": None,
        "recall_at_20": None,
        "mrr": None,
        "ndcg_at_10": None,
        "answer_correctness": None,
        "citation_validity": None,
        "correct_refusal_rate": statistics.fmean(refused) if refused else 0.0,
        "failure_to_refuse_rate": (
            1.0 - statistics.fmean(refused) if refused else 0.0
        ),
        "mean_returned_documents": statistics.fmean(
            float(row["returned_documents"]) for row in rows
        )
        if rows
        else 0.0,
        "latency_p50_ms": _percentile(latencies, 0.50),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "cost_per_query_usd": 0.0,
    }


def _bootstrap_delta(
    paired: list[tuple[float, float]], samples: int = 5000
) -> dict[str, float | int]:
    rng = random.Random(20260726)
    observed = statistics.fmean(final - baseline for baseline, final in paired)
    values = []
    for _ in range(samples):
        sample = [paired[rng.randrange(len(paired))] for _ in paired]
        values.append(statistics.fmean(final - baseline for baseline, final in sample))
    return {
        "delta": observed,
        "ci95_low": _percentile(values, 0.025),
        "ci95_high": _percentile(values, 0.975),
        "bootstrap_samples": samples,
    }


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
    queries = _read_queries(args.golden)
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
    naive_collection = _build_naive_collection(documents, model, settings)
    bm25_path = run_dir / "bm25.sqlite3"

    per_item: list[dict[str, Any]] = []
    for item in queries:
        for baseline in BASELINES:
            started = time.perf_counter()
            if baseline == "B0_closed_book_refusal":
                candidates: list[dict[str, Any]] = []
                status = "refused"
                refused = True
            elif baseline == "B1_bm25":
                candidates = _sparse_search(
                    path=bm25_path,
                    query=item["question"],
                    filters={},
                    limit=20,
                )
                refused = not candidates
                status = "no_results" if refused else "ok"
            elif baseline == "B2_dense_naive":
                candidates = _dense_search(
                    collection=naive_collection,
                    query=item["question"],
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
                    query=item["question"],
                    options=options,
                    embedding_model=model,
                    reranker=reranker,
                )
                candidates = result["results"]
                status = str(result["status"])
                refused = status != "ok"

            ranked_ids = _unique_document_ids(candidates)
            per_item.append(
                {
                    "id": item["id"],
                    "split": item["split"],
                    "question": item["question"],
                    "baseline": baseline,
                    "status": status,
                    "correct_refusal": float(refused),
                    "returned_documents": len(ranked_ids),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                    "top_20_document_ids": " || ".join(ranked_ids[:20]),
                }
            )

    result: dict[str, Any] = {
        "run_id": args.run_id,
        "items": len(queries),
        "evaluation_status": "exploratory_unverified_out_of_domain",
        "metric_scope": {
            "retrieval_metrics": "not_applicable_no_relevant_documents",
            "primary_metric": "correct_refusal_rate",
            "generation_evaluated": False,
        },
        "baselines": {},
    }
    for baseline in BASELINES:
        rows = [row for row in per_item if row["baseline"] == baseline]
        result["baselines"][baseline] = {
            "all": _aggregate(rows),
            "dev": _aggregate([row for row in rows if row["split"] == "dev"]),
            "test": _aggregate([row for row in rows if row["split"] == "test"]),
        }

    pairs = []
    for item in queries:
        b2 = next(
            row
            for row in per_item
            if row["id"] == item["id"] and row["baseline"] == "B2_dense_naive"
        )
        b3 = next(
            row
            for row in per_item
            if row["id"] == item["id"] and row["baseline"] == "B3_final"
        )
        pairs.append((float(b2["correct_refusal"]), float(b3["correct_refusal"])))
    result["uncertainty"] = {
        "B3_minus_B2_correct_refusal": _bootstrap_delta(pairs)
    }

    failures = [
        {
            "id": row["id"],
            "baseline": row["baseline"],
            "error_label": "out_of_domain_not_refused",
            "status": row["status"],
            "question": row["question"],
            "top_20_document_ids": row["top_20_document_ids"],
        }
        for row in per_item
        if row["baseline"] != "B0_closed_book_refusal"
        and not bool(row["correct_refusal"])
    ]
    result["error_analysis"] = {
        "labeled_failures": min(15, len(failures)),
        "total_failures_across_B1_B2_B3": len(failures),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(args.output_dir / "per_item_results.csv", per_item)
    _write_csv(args.output_dir / "error_analysis.csv", failures[:15])
    summary = [
        {"baseline": baseline, **values["all"]}
        for baseline, values in result["baselines"].items()
    ]
    _write_csv(args.output_dir / "metrics.csv", summary)
    (args.output_dir / "metrics.json").write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

