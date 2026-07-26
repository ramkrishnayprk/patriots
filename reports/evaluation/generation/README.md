# End-to-end generation evaluation

This directory contains a separate exploratory evaluation of the final B3
grounded answer output. It does not replace the retrieval-only reports in the
parent directory.

The evaluator forces questions through the semantic path, runs the production
weak-query escalation and final OpenAI generation stages, and grades generated
answers against the golden answer and evidence. The golden set remains
unverified, so these results are not official assessment scores.

Outputs:

- `per_item_generation.csv`: every generated answer, grade, citation decision,
  retrieval result, latency, escalation decision, and token count.
- `metrics_generation.csv` and `metrics_generation.json`: aggregate metrics.
- `failure_analysis_generation.csv`: observed final-answer failures.
- `eval_metrics_generation.tex` and `eval_metrics_generation.pdf`: report.

Run:

```bash
docker compose run --rm --no-deps \
  -v "$PWD/backend/evaluation:/app/evaluation:ro" \
  -v "$PWD/reports/evaluation:/app/reports/evaluation:ro" \
  -v "$PWD/reports/evaluation/generation:/app/reports/evaluation/generation" \
  backend python /app/evaluation/run_generation_eval.py \
  --golden /app/reports/evaluation/golden_set.csv \
  --data-dir /app/data \
  --run-id combined-movies \
  --output-dir /app/reports/evaluation/generation
```
