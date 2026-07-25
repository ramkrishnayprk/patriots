#!/usr/bin/env python3
"""Validate the golden CSV and audit the user's two-column seed CSV."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

CATEGORY_MINIMUMS = {
    "single_hop": 15,
    "multi_hop": 6,
    "comparative": 4,
    "temporal": 4,
    "unanswerable": 8,
    "ambiguous_adversarial": 3,
}
REQUIRED_COLUMNS = {
    "id",
    "category",
    "split",
    "question",
    "answerable",
    "gold_answer",
    "gold_document_ids",
    "source_urls",
    "evidence_quotes",
    "searched_for",
    "human_verified",
}
SEPARATOR = " || "


def _boolean(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"Expected true or false, got {value!r}.")
    return normalized == "true"


def _parts(value: str) -> list[str]:
    return [part.strip() for part in value.split(SEPARATOR) if part.strip()]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _word_count(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", value))


def _load_documents(path: Path) -> dict[str, dict[str, Any]]:
    documents = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                document = json.loads(line)
                documents[str(document["id"])] = document
    return documents


def validate_golden(path: Path, documents_path: Path) -> tuple[dict[str, Any], list[str]]:
    documents = _load_documents(documents_path)
    errors: list[str] = []
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        columns = set(reader.fieldnames or [])
        missing_columns = sorted(REQUIRED_COLUMNS - columns)
        if missing_columns:
            errors.append(f"Missing columns: {', '.join(missing_columns)}")
        rows = list(reader)

    ids = [row.get("id", "").strip() for row in rows]
    duplicate_ids = sorted(item for item, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        errors.append(f"Duplicate IDs: {', '.join(duplicate_ids)}")
    if len(rows) < 40:
        errors.append(f"Golden set has {len(rows)} items; at least 40 are required.")

    category_counts = Counter(row.get("category", "") for row in rows)
    split_counts = Counter(row.get("split", "") for row in rows)
    category_splits: dict[str, Counter[str]] = {}
    verified = 0
    answerable_count = 0

    for line_number, row in enumerate(rows, start=2):
        item_id = row.get("id", f"line-{line_number}")
        category = row.get("category", "")
        split = row.get("split", "")
        category_splits.setdefault(category, Counter())[split] += 1
        if category not in CATEGORY_MINIMUMS:
            errors.append(f"{item_id}: unsupported category {category!r}.")
        if split not in {"dev", "test"}:
            errors.append(f"{item_id}: split must be dev or test.")
        try:
            answerable = _boolean(row.get("answerable", ""))
            human_verified = _boolean(row.get("human_verified", ""))
        except ValueError as exc:
            errors.append(f"{item_id}: {exc}")
            continue
        verified += int(human_verified)
        answerable_count += int(answerable)

        document_ids = _parts(row.get("gold_document_ids", ""))
        urls = _parts(row.get("source_urls", ""))
        quotes = _parts(row.get("evidence_quotes", ""))
        if answerable:
            if not row.get("gold_answer", "").strip():
                errors.append(f"{item_id}: answerable item has no gold answer.")
            if not document_ids or len(document_ids) != len(urls):
                errors.append(f"{item_id}: document IDs and source URLs must align.")
            if len(quotes) != len(document_ids):
                errors.append(f"{item_id}: one evidence quote is required per document.")
            if row.get("searched_for", "").strip():
                errors.append(f"{item_id}: answerable item must not use searched_for.")
            if category == "multi_hop" and len(set(document_ids)) < 2:
                errors.append(f"{item_id}: multi-hop item needs at least two documents.")
            for document_id, quote in zip(document_ids, quotes):
                document = documents.get(document_id)
                if document is None:
                    errors.append(f"{item_id}: unknown document {document_id}.")
                    continue
                if _word_count(quote) > 25:
                    errors.append(f"{item_id}: evidence quote exceeds 25 words.")
                if _normalize(quote) not in _normalize(str(document.get("text") or "")):
                    errors.append(
                        f"{item_id}: evidence quote was not found in {document_id}."
                    )
        else:
            if document_ids or urls or quotes:
                errors.append(f"{item_id}: non-answerable item must not cite gold evidence.")
            if not row.get("searched_for", "").strip():
                errors.append(f"{item_id}: non-answerable item needs searched_for.")

    for category, minimum in CATEGORY_MINIMUMS.items():
        if category_counts[category] < minimum:
            errors.append(
                f"{category} has {category_counts[category]} items; minimum is {minimum}."
            )
        if category_splits.get(category, Counter())["dev"] == 0:
            errors.append(f"{category} has no dev items.")
        if category_splits.get(category, Counter())["test"] == 0:
            errors.append(f"{category} has no test items.")

    expected_dev = round(len(rows) * 0.60)
    if split_counts["dev"] != expected_dev or split_counts["test"] != len(rows) - expected_dev:
        errors.append(
            f"Split is dev={split_counts['dev']}, test={split_counts['test']}; "
            f"expected {expected_dev}/{len(rows) - expected_dev}."
        )

    result = {
        "structurally_valid": not errors,
        "assessment_ready": not errors and verified == len(rows),
        "human_verification_required": verified != len(rows),
        "items": len(rows),
        "answerable": answerable_count,
        "unanswerable_or_adversarial": len(rows) - answerable_count,
        "human_verified": verified,
        "category_counts": dict(category_counts),
        "split_counts": dict(split_counts),
        "category_splits": {
            category: dict(counts) for category, counts in category_splits.items()
        },
        "errors": errors,
    }
    return result, errors


def _record_answer(question: str, record: dict[str, Any]) -> tuple[str, str]:
    lowered = question.casefold()
    if "release date" in lowered:
        value = record.get("release_date")
        if not value:
            return "release_date", ""
        return "release_date", datetime.strptime(value, "%Y-%m-%d").strftime("%B %-d, %Y")
    if "directed" in lowered:
        return "directors", ", ".join(record.get("directors") or [])
    if "wrote" in lowered:
        return "writers", ", ".join(record.get("writers") or [])
    if "runtime" in lowered:
        value = record.get("runtime")
        return "runtime", f"{value} minutes" if value else ""
    if "genre" in lowered:
        return "genres", ", ".join(record.get("genres") or [])
    if "lead stars" in lowered:
        cast = record.get("top_cast") or []
        return "top_cast", ", ".join(
            str(item.get("name") or "") for item in cast[:3] if isinstance(item, dict)
        )
    if "overview" in lowered or "plot summary" in lowered or " about?" in lowered:
        return "overview", str(record.get("overview") or "")
    return "unknown", ""


def _expected_matches(field: str, expected: str, canonical: str) -> bool:
    expected_norm = _normalize(expected)
    canonical_norm = _normalize(canonical)
    if field == "runtime":
        hours = re.search(r"(\d+)\s*hour", expected_norm)
        minutes = re.search(r"(\d+)\s*minute", expected_norm)
        total = (int(hours.group(1)) * 60 if hours else 0) + (
            int(minutes.group(1)) if minutes else 0
        )
        canonical_minutes = re.search(r"\d+", canonical_norm)
        return bool(canonical_minutes and total == int(canonical_minutes.group()))
    if field == "release_date":
        return canonical_norm in expected_norm
    canonical_tokens = [
        token for token in re.findall(r"[a-z0-9]+", canonical_norm) if len(token) > 1
    ]
    expected_tokens = set(re.findall(r"[a-z0-9]+", expected_norm))
    return bool(canonical_tokens) and all(token in expected_tokens for token in canonical_tokens)


def audit_seed(seed_path: Path, structured_path: Path, output_path: Path) -> dict[str, int]:
    records = []
    with structured_path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                records.append(json.loads(line))
    titles = sorted(
        ((str(record.get("title") or ""), record) for record in records),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    with seed_path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        seed_rows = list(reader)

    audited = []
    counts: Counter[str] = Counter()
    for row in seed_rows:
        question = row.get("Questions", "").strip()
        expected = row.get("Expected Answers", "").strip()
        match = next(
            (
                record
                for title, record in titles
                if title and title.casefold() in question.casefold()
            ),
            None,
        )
        if not match:
            status, field, canonical = "title_not_found", "", ""
        else:
            field, canonical = _record_answer(question, match)
            if field == "unknown":
                status = "unsupported_question_pattern"
            elif not canonical:
                status = "gold_not_supported_by_corpus"
            elif _expected_matches(field, expected, canonical):
                status = "matches_corpus"
            else:
                status = "mismatch"
        counts[status] += 1
        audited.append(
            {
                "question": question,
                "provided_expected_answer": expected,
                "matched_title": str(match.get("title") or "") if match else "",
                "field": field,
                "corpus_answer": canonical,
                "status": status,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(audited[0]))
        writer.writeheader()
        writer.writerows(audited)
    return dict(counts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--documents", type=Path, required=True)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--structured", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--allow-unverified", action="store_true")
    args = parser.parse_args()

    validation, errors = validate_golden(args.golden, args.documents)
    seed_counts = audit_seed(
        args.seed,
        args.structured,
        args.output_dir / "seed_csv_validation.csv",
    )
    validation["seed_csv_audit"] = seed_counts
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "golden_validation.json").write_text(
        json.dumps(validation, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(validation, indent=2))
    if errors or (not validation["assessment_ready"] and not args.allow_unverified):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
