"""Prints a markdown table of example metric calculations, for pasting into reports.

Loads app/eval/metrics.py directly by file path so this script has no
dependency on the rest of the app (Flask, redis, chromadb, ...) -- it exists
purely to generate documentation-ready example rows, not to exercise the app.

Usage:
    python backend/scripts/eval/metrics_demo.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_metrics() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "app" / "eval" / "metrics.py"
    spec = importlib.util.spec_from_file_location("eval_metrics", path)
    module = importlib.util.module_from_spec(spec)
    # dataclasses needs the module registered in sys.modules before exec_module
    # runs, or its ClassVar/KW_ONLY type checks fail with an AttributeError.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    metrics = _load_metrics()
    rows: list[tuple[str, str, str]] = []

    retrieved = ["chunk-3", "chunk-1", "chunk-9", "chunk-2", "chunk-5"]
    relevant = {"chunk-1", "chunk-7"}
    rows.append(
        (
            "Recall@5",
            f"retrieved={retrieved}, relevant={sorted(relevant)}",
            f"{metrics.recall_at_k(retrieved, relevant, k=5):.3f}",
        )
    )
    rows.append(
        (
            "Recall@20",
            f"retrieved={retrieved} (only 5 returned), relevant={sorted(relevant)}",
            f"{metrics.recall_at_k(retrieved, relevant, k=20):.3f}",
        )
    )

    per_item_retrieved = [["chunk-1", "chunk-4"], ["chunk-9", "chunk-2", "chunk-7"]]
    per_item_relevant = [{"chunk-1"}, {"chunk-7"}]
    rows.append(
        (
            "MRR",
            f"items={per_item_retrieved}, relevant={per_item_relevant}",
            f"{metrics.mean_reciprocal_rank(per_item_retrieved, per_item_relevant):.3f}",
        )
    )

    ndcg_retrieved = ["chunk-9", "chunk-1", "chunk-4"]
    ndcg_relevant = {"chunk-1", "chunk-4"}
    rows.append(
        (
            "nDCG@10",
            f"retrieved={ndcg_retrieved}, relevant={sorted(ndcg_relevant)}",
            f"{metrics.ndcg_at_k(ndcg_retrieved, ndcg_relevant, k=10):.3f}",
        )
    )

    judgments = [True, True, False, True, True]
    rows.append(
        (
            "Answer correctness",
            f"per-item judgments={judgments}",
            f"{metrics.answer_correctness_rate(judgments):.3f}",
        )
    )

    citations, num_sources = {1, 2}, 3
    rows.append(
        (
            "Citation validity (one answer)",
            f"citations={sorted(citations)}, num_sources={num_sources}",
            str(metrics.citation_validity(citations, num_sources)),
        )
    )
    validity_outcomes = [True, True, False, True]
    rows.append(
        (
            "Citation validity rate",
            f"per-answer outcomes={validity_outcomes}",
            f"{metrics.citation_validity_rate(validity_outcomes):.3f}",
        )
    )

    unanswerable_refusals = [True, True, False, True, True]
    rows.append(
        (
            "Correct-refusal rate",
            f"unanswerable items refused={unanswerable_refusals}",
            f"{metrics.correct_refusal_rate(unanswerable_refusals):.3f}",
        )
    )
    answerable_refusals = [False, False, True, False]
    rows.append(
        (
            "Over-refusal rate",
            f"answerable items refused={answerable_refusals}",
            f"{metrics.over_refusal_rate(answerable_refusals):.3f}",
        )
    )

    latencies_ms = [180, 210, 240, 260, 310, 420, 900]
    rows.append(
        (
            "p50 latency (ms)",
            f"latencies={latencies_ms}",
            f"{metrics.latency_percentile(latencies_ms, 50):.1f}",
        )
    )
    rows.append(
        (
            "p95 latency (ms)",
            f"latencies={latencies_ms}",
            f"{metrics.latency_percentile(latencies_ms, 95):.1f}",
        )
    )

    pricing = metrics.TokenPricing(input_per_million=0.15, output_per_million=0.60)
    rows.append(
        (
            "Cost per query (USD)",
            f"input_tokens=850, output_tokens=180, pricing={pricing}",
            f"${metrics.cost_per_query_usd(850, 180, pricing):.6f}",
        )
    )

    print("| Metric | Example | Score |")
    print("| --- | --- | --- |")
    for metric_name, example, score in rows:
        print(f"| {metric_name} | {example} | {score} |")


if __name__ == "__main__":
    main()
