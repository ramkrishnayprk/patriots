# Out-of-domain refusal evaluation

This directory is independent of the existing movie golden-set evaluation.
It contains 40 non-movie questions and measures whether the retrieval evidence
gate refuses them.

Validate the CSV:

```bash
python3 backend/evaluation/validate_unrelated_set.py \
  --golden reports/evaluation/unrelated/golden_set_unrelated.csv \
  --output reports/evaluation/unrelated/golden_validation.json \
  --allow-unverified
```

Run B0–B3 using the existing Docker backend and local corpus:

```bash
docker compose run --rm --no-deps \
  -v "$PWD/backend/evaluation:/app/evaluation:ro" \
  -v "$PWD/reports/evaluation/unrelated:/app/reports/evaluation/unrelated" \
  backend python /app/evaluation/run_out_of_domain_eval.py \
  --golden /app/reports/evaluation/unrelated/golden_set_unrelated.csv \
  --data-dir /app/data \
  --run-id combined-movies \
  --output-dir /app/reports/evaluation/unrelated
```

Compile the report with the repository's LaTeX image:

```bash
docker run --rm \
  -v "$PWD/reports/evaluation/unrelated:/docs" \
  movie-rag-latex pdflatex -interaction=nonstopmode -halt-on-error \
  -output-directory=/docs /docs/eval_metrics_unrelated.tex
```

The CSV is structurally valid but not ready for official assessment until a
human verifies all 40 rows and changes `human_verified` to `true`.
