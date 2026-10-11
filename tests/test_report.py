"""Counting rules for the headline metric (DECISIONS D15)."""

import pandas as pd

from quotebench.report import quote_metrics


def frame(rows):
    base = {"should_abstain": False, "task": "reference", "location_correct": None, "flags": ""}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_verbatim_counting_rules():
    d = frame([
        {"label": "EXACT"},                       # correct
        {"label": "EXACT", "flags": "OVERLONG"},  # complete quote + extra text: correct
        {"label": "EXACT", "flags": "PARTIAL"},   # cut short: wrong (incomplete)
        {"label": "MINOR"},                       # spelling only: wrong
        {"label": "ALTERED"}, {"label": "FABRICATED"}, {"label": "WRONG_PLACE"},
        {"label": "UNPARSEABLE"},                 # excluded, but counted in correct_strict
        {"label": "ABSTAINED"},
        {"label": "CORRECT_REFUSAL", "should_abstain": True},
        {"label": "TRAP_FABRICATED", "should_abstain": True},
    ])
    m = quote_metrics(d)
    assert (m["correct"]["k"], m["correct"]["n"]) == (2, 7)
    assert (m["correct_strict"]["k"], m["correct_strict"]["n"]) == (2, 8)
    assert m["incomplete"]["k"] == 1 and m["spelling_only"]["k"] == 1
    assert m["altered"]["k"] == m["fabricated"]["k"] == m["wrong_place"]["k"] == 1
    assert (m["abstained"]["k"], m["abstained"]["n"]) == (1, 8)
    assert (m["trap_failure"]["k"], m["trap_failure"]["n"]) == (1, 2)
    assert m["unparseable"] == 1
