# 03 — Golden Set

The evaluation subsection uses
[`evaluation/golden_set.csv`](evaluation/golden_set.csv), containing 40 items:
15 single-hop, 6 multi-hop, 4 comparative, 4 temporal, 8 unanswerable, and
3 ambiguous/adversarial. The split is stratified 24 dev / 16 test.

Automated validation passed for schema, category minimums, split, source
existence, evidence presence, and the 25-word quote limit. Human verification
is 0/40, so this set is an AI-drafted candidate and is not yet valid for an
official assessment.

The supplied `Golden Rules Validate(Questions).csv` was preserved and audited:
14/23 answers matched the corpus, 4 conflicted, and 5 were unsupported by the
current records. See
[`evaluation/seed_csv_validation.csv`](evaluation/seed_csv_validation.csv).
