# Validation

No human labelling step in v1.0 (DECISIONS D15). The headline metric is mechanical: a quote is
correct only if every word matches the named edition (punctuation and capitals ignored), which
is verified by the unit tests in `tests/test_scoring.py`.

The split of *wrong* answers into spelling only / incomplete / altered / wrong place / made up
depends on similarity thresholds (`config/scoring.yaml`) and was not checked against human
labels; treat it as approximate. The tooling to run such a check later is kept:
`quotebench validate export` writes a labelling sheet and `quotebench validate agree` computes
agreement and Cohen's kappa.
