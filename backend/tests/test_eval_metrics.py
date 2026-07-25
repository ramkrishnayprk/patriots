import math

import pytest

from app.eval.metrics import (
    TokenPricing,
    answer_correctness_rate,
    citation_validity,
    citation_validity_rate,
    correct_refusal_rate,
    cost_per_query_usd,
    latency_percentile,
    mean_reciprocal_rank,
    ndcg_at_k,
    over_refusal_rate,
    recall_at_k,
    reciprocal_rank,
)


def test_recall_at_k_counts_hits_within_the_cutoff():
    retrieved = ["a", "b", "c", "d", "e", "f"]
    relevant = {"c", "f", "z"}

    assert recall_at_k(retrieved, relevant, k=5) == pytest.approx(1 / 3)
    assert recall_at_k(retrieved, relevant, k=6) == pytest.approx(2 / 3)


def test_recall_at_k_rejects_empty_relevant_set():
    with pytest.raises(ValueError):
        recall_at_k(["a"], set(), k=5)


def test_reciprocal_rank_and_mrr():
    assert reciprocal_rank(["a", "b", "c"], {"b"}) == pytest.approx(0.5)
    assert reciprocal_rank(["a", "b"], {"z"}) == 0.0

    mrr = mean_reciprocal_rank(
        per_item_retrieved=[["a", "b"], ["x", "y", "z"]],
        per_item_relevant=[{"a"}, {"z"}],
    )
    assert mrr == pytest.approx((1.0 + 1 / 3) / 2)


def test_ndcg_at_k_perfect_and_partial_ranking():
    relevant = {"a", "b"}
    assert ndcg_at_k(["a", "b", "c"], relevant, k=10) == pytest.approx(1.0)

    partial = ndcg_at_k(["c", "a", "b"], relevant, k=10)
    ideal_dcg = 1.0 + 1.0 / math.log2(3)
    dcg = 1.0 / math.log2(3) + 1.0 / math.log2(4)
    assert partial == pytest.approx(dcg / ideal_dcg)


def test_answer_correctness_rate_averages_booleans_and_partial_scores():
    assert answer_correctness_rate([True, False, True, True]) == pytest.approx(0.75)
    assert answer_correctness_rate([1.0, 0.5, 0.0]) == pytest.approx(0.5)


def test_citation_validity_requires_at_least_one_in_range_citation():
    assert citation_validity({1, 2}, num_sources=3) is True
    assert citation_validity(set(), num_sources=3) is False
    assert citation_validity({1, 99}, num_sources=3) is False


def test_citation_validity_rate_averages_per_item_outcomes():
    assert citation_validity_rate([True, True, False, True]) == pytest.approx(0.75)


def test_refusal_rates_are_fractions_of_their_own_subset():
    unanswerable_refusals = [True, True, False]
    answerable_refusals = [False, True, False, False]

    assert correct_refusal_rate(unanswerable_refusals) == pytest.approx(2 / 3)
    assert over_refusal_rate(answerable_refusals) == pytest.approx(1 / 4)


def test_latency_percentile_p50_and_p95():
    latencies = [100, 200, 300, 400, 500]

    assert latency_percentile(latencies, 50) == pytest.approx(300)
    assert latency_percentile(latencies, 95) == pytest.approx(480)


def test_latency_percentile_single_value():
    assert latency_percentile([123.0], 95) == pytest.approx(123.0)


def test_cost_per_query_usd_combines_input_and_output_pricing():
    pricing = TokenPricing(input_per_million=1.0, output_per_million=2.0)

    cost = cost_per_query_usd(input_tokens=500_000, output_tokens=250_000, pricing=pricing)

    assert cost == pytest.approx(0.5 * 1.0 + 0.25 * 2.0)


def test_cost_per_query_usd_rejects_negative_tokens():
    with pytest.raises(ValueError):
        cost_per_query_usd(-1, 0, TokenPricing(1.0, 1.0))
