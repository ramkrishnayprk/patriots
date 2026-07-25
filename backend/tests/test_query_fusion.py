from app.retrieval.fusion import fuse_retrieval_attempts


def _attempt(kind, query, status, results):
    return {
        "_kind": kind,
        "status": status,
        "query": {"original": query, "normalized": query.lower()},
        "results": results,
    }


def _result(chunk_id, rank, rerank_score):
    return {
        "id": chunk_id,
        "document_id": chunk_id.split("-")[0],
        "chunk_number": 0,
        "rank": rank,
        "title": chunk_id,
        "text": f"Evidence for {chunk_id}",
        "score": 0.9,
        "rerank_score": rerank_score,
    }


def test_fusion_rewards_results_seen_across_multiple_queries():
    attempts = [
        _attempt(
            "original",
            "original query",
            "low_confidence",
            [_result("a-0", 1, -5), _result("shared-0", 2, -4)],
        ),
        _attempt(
            "query_variation_1",
            "variation one",
            "ok",
            [_result("shared-0", 1, 3), _result("b-0", 2, 2)],
        ),
        _attempt(
            "hyde",
            "hypothetical passage",
            "ok",
            [_result("shared-0", 1, 4), _result("c-0", 2, 1)],
        ),
    ]

    fused = fuse_retrieval_attempts(
        original_query="original query",
        attempts=attempts,
        final_k=3,
        rrf_k=60,
    )

    assert fused["status"] == "ok"
    assert fused["query"]["original"] == "original query"
    assert fused["results"][0]["id"] == "shared-0"
    assert fused["results"][0]["rerank_score"] == 4
    assert fused["results"][0]["query_fusion_score"] > 0
    assert fused["diagnostics"]["strategy"] == "multi_query_hyde_rrf"
    assert len(fused["diagnostics"]["attempts"]) == 3


def test_fusion_returns_no_results_when_every_attempt_is_empty():
    fused = fuse_retrieval_attempts(
        original_query="unknown",
        attempts=[_attempt("original", "unknown", "no_results", [])],
        final_k=5,
        rrf_k=60,
    )

    assert fused["status"] == "no_results"
    assert fused["results"] == []
