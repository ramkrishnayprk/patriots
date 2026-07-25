import hashlib
import json
import math

import numpy as np

from app.embedding.pipeline import EmbeddingOptions, ingest_run
from app.retrieval.pipeline import RetrievalOptions, search_run


class FakeEmbeddingModel:
    @staticmethod
    def get_sentence_embedding_dimension():
        return 4

    @staticmethod
    def encode(texts, **_kwargs):
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vector = np.asarray([digest[index] + 1 for index in range(4)], dtype=np.float32)
            vector /= math.sqrt(float(np.dot(vector, vector)))
            vectors.append(vector)
        return np.asarray(vectors)


class FakeReranker:
    @staticmethod
    def rerank(query, documents):
        terms = set(query.lower().split())
        return [
            3.0 if terms.intersection(document.lower().split()) else -3.0
            for document in documents
        ]


def _chunk(chunk_id, document_id, text, *, genres=None):
    return {
        "id": chunk_id,
        "document_id": document_id,
        "chunk_number": int(chunk_id.rsplit("-", 1)[-1]),
        "title": f"Movie {document_id}",
        "section": "Overview",
        "year": 2026,
        "genres": genres or ["Science Fiction"],
        "imdb_rating": 7.4,
        "url": f"https://www.imdb.com/title/{document_id}/",
        "quick_facts": {"year": 2026, "imdb_rating": 7.4},
        "text": text,
        "strategy": "section_aware",
        "content_hash": hashlib.sha256(text.encode()).hexdigest(),
        "generation": 1,
    }


def _build_indexes(tmp_path):
    run_dir = tmp_path / "runs" / "retrieval-run"
    run_dir.mkdir(parents=True)
    chunks = [
        _chunk("future-0", "future", "A researcher receives a signal from tomorrow"),
        _chunk("future-1", "future", "The signal warns of a dangerous experiment"),
        _chunk("future-2", "future", "The researcher chooses whether to alter time"),
        _chunk("planet-0", "planet", "A pilot wakes on an unfamiliar planet"),
    ]
    (run_dir / "chunks.jsonl").write_text(
        "".join(json.dumps(chunk) + "\n" for chunk in chunks),
        encoding="utf-8",
    )
    ingest_run(
        data_dir=tmp_path,
        run_id="retrieval-run",
        options=EmbeddingOptions(
            model_name="fake/model",
            model_path=tmp_path / "models",
            embed_dim=4,
            batch_size=4,
        ),
        model=FakeEmbeddingModel(),
    )


def _options(tmp_path):
    return RetrievalOptions(
        model_name="fake/model",
        reranker_model_name="fake/reranker",
        model_path=tmp_path / "models",
        embed_dim=4,
        top_k_dense=4,
        top_k_sparse=4,
        rerank_top_n=4,
        final_k=3,
        confidence_threshold=0.45,
        max_per_document=2,
    )


def test_hybrid_search_reranks_and_limits_document_dominance(tmp_path):
    _build_indexes(tmp_path)

    response = search_run(
        data_dir=tmp_path,
        run_id="retrieval-run",
        query="researcher signal tomorrow",
        options=_options(tmp_path),
        embedding_model=FakeEmbeddingModel(),
        reranker=FakeReranker(),
    )

    assert response["status"] == "ok"
    assert [item["rank"] for item in response["results"]] == [1, 2, 3]
    assert sum(item["document_id"] == "future" for item in response["results"]) == 2
    assert response["diagnostics"]["candidates"]["dense"] == 4
    assert response["diagnostics"]["candidates"]["sparse"] >= 2
    assert response["results"][0]["rerank_score"] == 3.0
    assert response["results"][0]["quick_facts"]["year"] == 2026


def test_empty_query_returns_no_results_without_loading_indexes(tmp_path):
    response = search_run(
        data_dir=tmp_path,
        run_id="missing-run",
        query="   ",
        options=_options(tmp_path),
    )

    assert response["status"] == "no_results"
    assert response["results"] == []


def test_weak_results_are_reported_as_low_confidence(tmp_path):
    _build_indexes(tmp_path)

    response = search_run(
        data_dir=tmp_path,
        run_id="retrieval-run",
        query="unrelated cooking documentary",
        options=_options(tmp_path),
        embedding_model=FakeEmbeddingModel(),
        reranker=FakeReranker(),
    )

    assert response["status"] == "low_confidence"
    assert response["results"][0]["score"] < 0.45


def test_empty_metadata_filter_is_relaxed(tmp_path):
    _build_indexes(tmp_path)

    response = search_run(
        data_dir=tmp_path,
        run_id="retrieval-run",
        query="2025 time travel plot",
        options=_options(tmp_path),
        embedding_model=FakeEmbeddingModel(),
        reranker=FakeReranker(),
    )

    assert response["results"]
    assert response["diagnostics"]["filters"]["relaxed"] is True
    assert "metadata_filters_relaxed" in response["diagnostics"]["degradations"]
