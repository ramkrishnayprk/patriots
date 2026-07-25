import json
from pathlib import Path

from app.rechunking.pipeline import RechunkOptions, rechunk_run


def _document(document_id: str = "doc-1") -> dict:
    overview = (
        "Students develop practical analytical skills for modern organizations. "
        "The curriculum emphasizes applied projects and responsible decision making."
    )
    outcomes = " ".join(
        [
            "Graduates evaluate evidence, communicate findings, and build reliable systems."
            for _ in range(8)
        ]
    )
    return {
        "id": document_id,
        "title": "Data Science, M.S.",
        "url": "https://example.edu/programs/data-science/",
        "category": "Information Technology",
        "quick_facts": {"credit_hours": "30", "delivery_format": "Online"},
        "sections": [
            {"heading": "Notice", "content": "Apply today."},
            {"heading": "Overview", "content": overview},
            {"heading": "Outcomes", "content": outcomes},
        ],
        "text": f"Data Science, M.S.\n\n{overview}\n\n{outcomes}",
    }


def _write_documents(run_dir: Path, records: list[dict]) -> None:
    run_dir.mkdir(parents=True)
    with (run_dir / "documents.jsonl").open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_section_aware_rechunk_adds_metadata_and_report(tmp_path):
    run_dir = tmp_path / "runs" / "run-1"
    _write_documents(run_dir, [_document()])
    options = RechunkOptions(
        chunk_size=220,
        overlap=40,
        min_chunk=80,
        strategy="section_aware",
        embed_prefix=True,
    )

    report = rechunk_run(data_dir=tmp_path, run_id="run-1", options=options)
    chunks = _read_jsonl(run_dir / "chunks.jsonl")

    assert report["generation"] == 1
    assert report["documents_processed"] == 1
    assert report["oversized_sections_split"] == 1
    assert report["tiny_sections_merged"] == 1
    assert report["total_chunks"] == len(chunks)
    assert chunks[0]["text"].startswith("Program: Data Science, M.S.")
    assert "Quick facts: Credit Hours: 30 | Delivery Format: Online" in chunks[0]["text"]
    assert "Apply today." in chunks[0]["text"]
    assert [chunk["chunk_number"] for chunk in chunks] == list(range(len(chunks)))
    assert all(
        chunk["id"] == f"doc-1::section_aware::{index}" for index, chunk in enumerate(chunks)
    )
    assert all(chunk["strategy"] == "section_aware" for chunk in chunks)
    assert all(chunk["generation"] == 1 for chunk in chunks)
    assert all(chunk["char_len"] == len(chunk["text"]) for chunk in chunks)
    assert all(len(chunk["content_hash"]) == 64 for chunk in chunks)
    assert (run_dir / "chunk_manifest.json").exists()
    assert (run_dir / "chunk_report.json").exists()
    assert (run_dir / "chunk_errors.log").exists()

    original_ids = [chunk["id"] for chunk in chunks]
    second_report = rechunk_run(data_dir=tmp_path, run_id="run-1", options=options)
    second_chunks = _read_jsonl(run_dir / "chunks.jsonl")
    assert second_report["generation"] == 2
    assert [chunk["id"] for chunk in second_chunks] == original_ids


def test_rechunk_increments_generation_and_sweeps_old_chunks(tmp_path):
    run_dir = tmp_path / "runs" / "run-2"
    document = _document()
    _write_documents(run_dir, [document])
    section_options = RechunkOptions(
        chunk_size=220,
        overlap=40,
        min_chunk=80,
        strategy="section_aware",
        embed_prefix=False,
    )
    recursive_options = RechunkOptions(
        chunk_size=220,
        overlap=40,
        min_chunk=80,
        strategy="recursive",
        embed_prefix=False,
    )

    rechunk_run(data_dir=tmp_path, run_id="run-2", options=section_options)
    report = rechunk_run(data_dir=tmp_path, run_id="run-2", options=recursive_options)
    chunks = _read_jsonl(run_dir / "chunks.jsonl")

    assert report["generation"] == 2
    assert all(chunk["generation"] == 2 for chunk in chunks)
    assert all(chunk["strategy"] == "recursive" for chunk in chunks)
    assert all("::section_aware::" not in chunk["id"] for chunk in chunks)


def test_section_aware_falls_back_for_single_section(tmp_path):
    run_dir = tmp_path / "runs" / "run-3"
    document = _document()
    document["sections"] = [document["sections"][1]]
    _write_documents(run_dir, [document])

    report = rechunk_run(
        data_dir=tmp_path,
        run_id="run-3",
        options=RechunkOptions(
            chunk_size=220,
            overlap=40,
            min_chunk=80,
            strategy="section_aware",
            embed_prefix=False,
        ),
    )
    chunks = _read_jsonl(run_dir / "chunks.jsonl")

    assert report["fallback_documents"] == ["doc-1"]
    assert all(chunk["section"] == document["title"] for chunk in chunks)


def test_rechunk_logs_invalid_documents(tmp_path):
    run_dir = tmp_path / "runs" / "run-4"
    _write_documents(
        run_dir,
        [
            _document(),
            {"id": "empty", "text": "", "sections": []},
            ["not", "an", "object"],
        ],
    )

    report = rechunk_run(
        data_dir=tmp_path,
        run_id="run-4",
        options=RechunkOptions(
            chunk_size=220,
            overlap=40,
            min_chunk=80,
            strategy="recursive",
            embed_prefix=False,
        ),
    )
    errors = _read_jsonl(run_dir / "chunk_errors.log")

    assert report["documents_processed"] == 1
    assert report["documents_skipped"] == 2
    assert errors[0]["document_id"] == "empty"
    assert errors[0]["reason"] == "missing_text_and_sections"
    assert errors[1]["reason"] == "document_must_be_an_object"
