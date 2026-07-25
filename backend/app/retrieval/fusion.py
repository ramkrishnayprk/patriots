from typing import Any


def fuse_retrieval_attempts(
    *,
    original_query: str,
    attempts: list[dict[str, Any]],
    final_k: int,
    rrf_k: int,
) -> dict[str, Any]:
    """Fuse already reranked result lists while preserving grounded records."""
    if final_k < 1:
        raise ValueError("final_k must be positive.")
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive.")

    fused_scores: dict[str, float] = {}
    records: dict[str, dict[str, Any]] = {}
    best_strength: dict[str, tuple[float, float]] = {}
    attempt_summaries = []

    for attempt_number, attempt in enumerate(attempts, start=1):
        results = attempt.get("results")
        results = results if isinstance(results, list) else []
        attempt_summaries.append(
            {
                "attempt": attempt_number,
                "kind": attempt.get("_kind", "query"),
                "query": (attempt.get("query") or {}).get("original"),
                "status": attempt.get("status"),
                "result_count": len(results),
                "top_score": results[0].get("score") if results else None,
                "top_rerank_score": (
                    results[0].get("rerank_score") if results else None
                ),
            }
        )
        seen_in_attempt = set()
        for fallback_rank, result in enumerate(results, start=1):
            if not isinstance(result, dict):
                continue
            key = _result_key(result)
            if not key or key in seen_in_attempt:
                continue
            seen_in_attempt.add(key)
            rank = _positive_integer(result.get("rank"), fallback_rank)
            fused_scores[key] = fused_scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
            strength = (
                _number(result.get("rerank_score")),
                _number(result.get("score")),
            )
            if key not in records or strength > best_strength[key]:
                records[key] = dict(result)
                best_strength[key] = strength

    ordered_keys = sorted(
        records,
        key=lambda key: (
            -fused_scores[key],
            -best_strength[key][0],
            -best_strength[key][1],
            key,
        ),
    )
    output = []
    for rank, key in enumerate(ordered_keys[:final_k], start=1):
        record = records[key]
        record["rank"] = rank
        record["query_fusion_score"] = round(fused_scores[key], 8)
        output.append(record)

    if not output:
        status = "no_results"
    elif any(attempt.get("status") == "ok" for attempt in attempts):
        status = "ok"
    else:
        status = "low_confidence"

    return {
        "status": status,
        "query": {
            "original": original_query,
            "normalized": " ".join(original_query.lower().split()),
        },
        "results": output,
        "diagnostics": {
            "strategy": "multi_query_hyde_rrf",
            "rrf_k": rrf_k,
            "attempts": attempt_summaries,
            "candidates": {
                "unique": len(records),
                "returned": len(output),
            },
        },
    }


def _result_key(result: dict[str, Any]) -> str:
    value = result.get("id")
    if value:
        return str(value)
    document_id = result.get("document_id")
    chunk_number = result.get("chunk_number")
    if document_id is not None and chunk_number is not None:
        return f"{document_id}:{chunk_number}"
    return ""


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def _positive_integer(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
