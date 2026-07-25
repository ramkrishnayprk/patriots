# 06 — Exploratory Performance

These are exploratory local retrieval results, not official test scores.

| Configuration | Recall@5 | Recall@20 | MRR | nDCG@10 | Answer-support proxy | Correct refusal | Over-refusal | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 offline refusal control | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 | 1.000 | 0.0 |
| B1 BM25 | 1.000 | 1.000 | 0.977 | 0.983 | 1.000 | 0.000 | 0.000 | 19.1 |
| B2 dense, naive chunks | 0.966 | 0.966 | 0.966 | 0.966 | 0.966 | 0.000 | 0.000 | 36.3 |
| B3 final hybrid/reranked | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.091 | 0.000 | 1532.1 |

B3 minus B2 answer-support was +0.0345 with a paired 95% bootstrap
confidence interval of [0.0000, 0.1034]. This does not establish an
improvement. The key observed failure is refusal: B3 rejected only 9.1% of
questions whose requested fact was absent.

The detailed results and limitations are in
[`evaluation/metrics.json`](evaluation/metrics.json) and
[`evaluation/eval_metrics.pdf`](evaluation/eval_metrics.pdf).
