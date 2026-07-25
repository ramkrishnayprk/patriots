"""Metrics for RAG evaluation: Recall@5/@20, MRR, nDCG@10, answer correctness,
citation validity, correct-refusal / over-refusal rate, p50/p95 latency, and
cost per query.

Every function takes already-computed per-item outcomes (retrieved id lists,
pass/fail flags, token counts, latencies) rather than reaching into the
retrieval or generation pipelines itself, so the module stays pure and
independently testable.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Retrieval quality (binary relevance): Recall@5, Recall@20, MRR, nDCG@10
# ---------------------------------------------------------------------------


def recall_at_k(retrieved_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    """Fraction of `relevant_ids` present anywhere in the top-k of `retrieved_ids`.

    Call with k=5 and k=20 for Recall@5 / Recall@20.
    """
    if not relevant_ids:
        raise ValueError("relevant_ids cannot be empty.")
    if k < 1:
        raise ValueError("k must be positive.")
    top_k = set(retrieved_ids[:k])
    return len(top_k & relevant_ids) / len(relevant_ids)


def reciprocal_rank(retrieved_ids: Sequence[str], relevant_ids: set[str]) -> float:
    """1/rank of the first relevant id in `retrieved_ids`, or 0.0 if none appear."""
    if not relevant_ids:
        raise ValueError("relevant_ids cannot be empty.")
    for rank, chunk_id in enumerate(retrieved_ids, start=1):
        if chunk_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def mean_reciprocal_rank(
    per_item_retrieved: Sequence[Sequence[str]],
    per_item_relevant: Sequence[set[str]],
) -> float:
    """MRR across items: the mean of each item's reciprocal_rank."""
    if len(per_item_retrieved) != len(per_item_relevant):
        raise ValueError("per_item_retrieved and per_item_relevant must be equal length.")
    if not per_item_retrieved:
        raise ValueError("Cannot compute MRR over zero items.")
    scores = [
        reciprocal_rank(retrieved, relevant)
        for retrieved, relevant in zip(per_item_retrieved, per_item_relevant, strict=True)
    ]
    return sum(scores) / len(scores)


def ndcg_at_k(retrieved_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    """Binary-relevance nDCG@k: DCG of `retrieved_ids` over the ideal DCG.

    Call with k=10 for nDCG@10.
    """
    if not relevant_ids:
        raise ValueError("relevant_ids cannot be empty.")
    if k < 1:
        raise ValueError("k must be positive.")
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, chunk_id in enumerate(retrieved_ids[:k], start=1)
        if chunk_id in relevant_ids
    )
    ideal_hits = min(len(relevant_ids), k)
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / ideal_dcg if ideal_dcg else 0.0


# ---------------------------------------------------------------------------
# Answer correctness
# ---------------------------------------------------------------------------


def answer_correctness_rate(judgments: Sequence[bool | float]) -> float:
    """Mean of per-item correctness judgments (booleans, or [0, 1] partial-credit scores).

    Judgments themselves (exact-match, rubric grading, LLM-as-judge, ...) are
    produced elsewhere; this only aggregates them into the headline rate.
    """
    if not judgments:
        raise ValueError("Cannot average zero judgments.")
    return sum(float(value) for value in judgments) / len(judgments)


# ---------------------------------------------------------------------------
# Citation validity
# ---------------------------------------------------------------------------


def citation_validity(citations: set[int], num_sources: int) -> bool:
    """True if an answer cited at least one source and every citation number resolves.

    Extract `citations` with `app.generation.pipeline.citation_numbers(answer)` so
    the citation-bracket regex has exactly one implementation.
    """
    if num_sources < 1:
        raise ValueError("num_sources must be positive.")
    if not citations:
        return False
    return all(1 <= number <= num_sources for number in citations)


def citation_validity_rate(valid: Sequence[bool]) -> float:
    """Fraction of answers (that cited anything) whose citations were all valid."""
    if not valid:
        raise ValueError("Cannot average zero citation-validity outcomes.")
    return sum(1 for item in valid if item) / len(valid)


# ---------------------------------------------------------------------------
# Refusal behavior
# ---------------------------------------------------------------------------


def correct_refusal_rate(refused: Sequence[bool]) -> float:
    """Over unanswerable items: fraction the system correctly refused to answer."""
    if not refused:
        raise ValueError("Cannot average zero refusal outcomes.")
    return sum(1 for item in refused if item) / len(refused)


def over_refusal_rate(refused: Sequence[bool]) -> float:
    """Over answerable items: fraction the system incorrectly refused to answer."""
    if not refused:
        raise ValueError("Cannot average zero refusal outcomes.")
    return sum(1 for item in refused if item) / len(refused)


# ---------------------------------------------------------------------------
# Latency
# ---------------------------------------------------------------------------


def latency_percentile(latencies_ms: Sequence[float], percentile: float) -> float:
    """Linear-interpolation percentile over per-query latencies, in milliseconds.

    Call with percentile=50 and percentile=95 for p50/p95 latency.
    """
    if not latencies_ms:
        raise ValueError("Cannot compute a percentile over zero latencies.")
    if not 0 <= percentile <= 100:
        raise ValueError("percentile must be between 0 and 100.")
    ordered = sorted(latencies_ms)
    if len(ordered) == 1:
        return ordered[0]
    rank = (percentile / 100) * (len(ordered) - 1)
    lower_index = math.floor(rank)
    upper_index = math.ceil(rank)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = rank - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


# ---------------------------------------------------------------------------
# Cost per query
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenPricing:
    """USD price per 1,000,000 tokens, matching how providers publish pricing."""

    input_per_million: float
    output_per_million: float

    def validate(self) -> None:
        if self.input_per_million < 0 or self.output_per_million < 0:
            raise ValueError("Token prices cannot be negative.")


def cost_per_query_usd(input_tokens: int, output_tokens: int, pricing: TokenPricing) -> float:
    """Estimated USD cost of one query given its prompt/completion token counts."""
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Token counts cannot be negative.")
    pricing.validate()
    return (
        input_tokens / 1_000_000 * pricing.input_per_million
        + output_tokens / 1_000_000 * pricing.output_per_million
    )
