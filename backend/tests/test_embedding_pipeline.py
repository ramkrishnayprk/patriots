import hashlib
import json
import math

import numpy as np

from app.embedding.pipeline import EmbeddingOptions, ingest_run


class FakeTokenizer:
    @staticmethod
    def encode(text, **_kwargs):
        return text.split()


class FakeModel:
    max_seq_length = 512
    tokenizer = FakeTokenizer()

    @staticmethod
    def get_sentence_embedding_dimension():
        return 4

    @staticmethod
    def encode(texts, **_kwargs):
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vector = np.array([digest[index] + 1 for index in range(4)], dtype=np.float32)
            vector /= math.sqrt(float(np.dot(vector, vector)))
            vectors.append(vector)
        return np.asarray(vectors)


def _chunk(chunk_id: str, text: str, *, generation: int) -> dict:
    return {
        "id": chunk_id,
        "document_id": chunk_id.split("::")[0],
        "chunk_number": 0,
        "title": "The Future Film",
        "section": "Overview",
        "year": 2026,
        "genres": ["Science Fiction", "Drama"],
        "imdb_rating": 7.4,
        "url": "https://www.imdb.com/title/tt0000001/",
        "quick_facts": {"year": 2026, "genres": ["Science Fiction"]},
        "text": text,
        "strategy": "section_aware",
        "content_hash": hashlib.sha256(text.encode()).hexdigest(),
        "generation": generation,
        "char_len": len(text),
    }


def _write_chunks(path, chunks):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(chunk) + "\n" for chunk in chunks),
        encoding="utf-8",
    )


def test_embedding_pipeline_is_idempotent_and_sweeps(tmp_path):
    run_dir = tmp_path / "runs" / "embedding-run"
    chunks_path = run_dir / "chunks.jsonl"
    first_chunks = [
        _chunk("tt1::section_aware::0", "A signal arrives from tomorrow.", generation=2),
        _chunk("tt2::section_aware::0", "A family searches an abandoned city.", generation=2),
    ]
    _write_chunks(chunks_path, first_chunks)
    options = EmbeddingOptions(
        model_name="fake/model",
        model_path=tmp_path / "model",
        embed_dim=4,
        batch_size=2,
    )

    first = ingest_run(
        data_dir=tmp_path,
        run_id="embedding-run",
        options=options,
        model=FakeModel(),
    )
    second = ingest_run(
        data_dir=tmp_path,
        run_id="embedding-run",
        options=options,
        model=FakeModel(),
    )

    assert first["embedded"] == 2
    assert first["reused_from_cache"] == 0
    assert first["vector_count"] == 2
    assert second["embedded"] == 0
    assert second["reused_from_cache"] == 2
    assert second["vector_count"] == 2

    replacement_chunks = [
        _chunk("tt2::section_aware::0", "A family searches an abandoned city.", generation=3),
        _chunk("tt3::section_aware::0", "A detective investigates a vanished ship.", generation=3),
    ]
    _write_chunks(chunks_path, replacement_chunks)
    third = ingest_run(
        data_dir=tmp_path,
        run_id="embedding-run",
        options=options,
        model=FakeModel(),
    )

    assert third["embedded"] == 1
    assert third["reused_from_cache"] == 1
    assert third["swept"] == 1
    assert third["vector_count"] == 2
    assert third["generation"] == 3
    assert (run_dir / "bm25.sqlite3").exists()
    assert (run_dir / "embedding_manifest.json").exists()
    assert (run_dir / "embedding_report.json").exists()
    assert (run_dir / "embedding_errors.log").read_text(encoding="utf-8") == ""
