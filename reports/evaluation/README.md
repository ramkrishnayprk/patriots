# Evaluation subsection

This directory contains a reproducible, exploratory 40-item evaluation for
the `combined-movies` run.

The golden set is structurally valid but is **not assessment-ready**:
`human_verified` is false for every AI-drafted row. A person must open each
source PDF, verify the gold answer and evidence quote, and change that field
only after verification. Freeze the CSV before the official once-only test
run.

## Reproduce

Validate the golden set and audit the supplied seed CSV:

```bash
python3 backend/evaluation/validate_golden_set.py \
  --golden reports/evaluation/golden_set.csv \
  --documents backend/data/runs/combined-movies/documents.jsonl \
  --seed "Golden Rules Validate(Questions).csv" \
  --structured backend/data/runs/combined-movies/movies_2026.jsonl \
  --output-dir reports/evaluation \
  --allow-unverified
```

Run the four offline configurations:

```bash
docker compose run --rm --no-deps \
  -v "$PWD/backend/evaluation:/app/evaluation:ro" \
  -v "$PWD/reports/evaluation:/app/reports/evaluation" \
  backend python /app/evaluation/run_retrieval_eval.py \
  --golden /app/reports/evaluation/golden_set.csv \
  --data-dir /app/data \
  --run-id combined-movies \
  --output-dir /app/reports/evaluation
```

Compile the PDF:

```bash
docker run --rm \
  -v "$PWD/reports/evaluation:/docs" \
  movie-rag-latex \
  pdflatex -interaction=nonstopmode -halt-on-error \
  -output-directory=/docs /docs/eval_metrics.tex
```

## Outputs

- `golden_set.csv`: 40 rubric-shaped items with a 24/16 stratified split.
- `golden_validation.json`: schema, category, evidence, and readiness checks.
- `seed_csv_validation.csv`: audit of the supplied 23-question CSV.
- `per_item_results.csv`: rankings and per-item metric values.
- `metrics.csv` and `metrics.json`: aggregate real numbers.
- `error_analysis.csv`: 15 deterministically labeled failures.
- `eval_metrics.tex` and `eval_metrics.pdf`: concise evaluation report.

## Limitations

- B0 is an always-refuse offline control, not a closed-book LLM run.
- Answer correctness and citation validity are retrieval-support proxies.
- Refusal metrics measure the retrieval evidence gate, not final generated text.
- The reported test split is exploratory and must be rerun once after human
  verification.
- The questions focus on five fictional PDF records and are not representative
  of the full 1,826-record catalog.
- Local inference has zero paid API cost; host compute cost is not estimated.

AI drafted the evaluation questions, code, and report. Human verification is
deliberately left incomplete and is never implied.
