#!/usr/bin/env python3
"""Validate an out-of-domain refusal set without changing the main validator."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

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
MOVIE_TERMS = re.compile(
    r"\b(?:imdb|tmdb|movie|movies|film|films|cinema|actor|actress|cast|director|"
    r"screenplay|runtime|box[\s-]?office|genre|release date)\b",
    re.IGNORECASE,
)


def validate(path: Path) -> dict:
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        columns = set(reader.fieldnames or [])
        rows = list(reader)

    errors: list[str] = []
    missing = sorted(REQUIRED_COLUMNS - columns)
    if missing:
        errors.append(f"Missing columns: {', '.join(missing)}")
    if len(rows) < 40:
        errors.append(f"Expected at least 40 items; found {len(rows)}.")

    identifiers = [row.get("id", "").strip() for row in rows]
    duplicates = sorted(item for item, count in Counter(identifiers).items() if count > 1)
    if duplicates:
        errors.append(f"Duplicate IDs: {', '.join(duplicates)}")

    splits = Counter(row.get("split", "").strip() for row in rows)
    verified = 0
    for line_number, row in enumerate(rows, start=2):
        item_id = row.get("id", f"line-{line_number}")
        if row.get("category", "").strip() != "out_of_domain":
            errors.append(f"{item_id}: category must be out_of_domain.")
        if row.get("split", "").strip() not in {"dev", "test"}:
            errors.append(f"{item_id}: split must be dev or test.")
        if row.get("answerable", "").strip().lower() != "false":
            errors.append(f"{item_id}: every out-of-domain item must be unanswerable.")
        if row.get("gold_document_ids", "").strip():
            errors.append(f"{item_id}: must not contain gold document IDs.")
        if row.get("source_urls", "").strip():
            errors.append(f"{item_id}: must not contain source URLs.")
        if row.get("evidence_quotes", "").strip():
            errors.append(f"{item_id}: must not contain evidence quotes.")
        if not row.get("searched_for", "").strip():
            errors.append(f"{item_id}: searched_for is required.")
        if not row.get("gold_answer", "").strip():
            errors.append(f"{item_id}: expected refusal behavior is required.")
        question = row.get("question", "").strip()
        if not question:
            errors.append(f"{item_id}: question is required.")
        elif MOVIE_TERMS.search(question):
            errors.append(f"{item_id}: question contains a movie-domain term.")
        human_value = row.get("human_verified", "").strip().lower()
        if human_value not in {"true", "false"}:
            errors.append(f"{item_id}: human_verified must be true or false.")
        verified += int(human_value == "true")

    expected_dev = round(len(rows) * 0.60)
    expected_test = len(rows) - expected_dev
    if splits["dev"] != expected_dev or splits["test"] != expected_test:
        errors.append(
            f"Expected dev/test={expected_dev}/{expected_test}; "
            f"found {splits['dev']}/{splits['test']}."
        )

    return {
        "structurally_valid": not errors,
        "assessment_ready": not errors and verified == len(rows),
        "human_verification_required": verified != len(rows),
        "items": len(rows),
        "answerable": 0,
        "out_of_domain": len(rows),
        "human_verified": verified,
        "split_counts": dict(splits),
        "movie_domain_terms_found": sum(
            bool(MOVIE_TERMS.search(row.get("question", ""))) for row in rows
        ),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-unverified", action="store_true")
    args = parser.parse_args()

    result = validate(args.golden)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if result["errors"] or (
        not result["assessment_ready"] and not args.allow_unverified
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

