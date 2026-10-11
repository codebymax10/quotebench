"""Test-set invariants (SPEC §4–5): determinism, answer keys, Task 2 rules, verified traps."""

import hashlib
import json
import re

import pytest

from quotebench import questions as Q
from quotebench.scoring import (
    ABSTAINED, CORRECT_REFUSAL, EXACT, FABRICATED, TRAP_FABRICATED, UNPARSEABLE, WRONG_PLACE,
    load_index, score_free, score_lookup, tokenize,
)
from quotebench.sources import load_units


@pytest.fixture(scope="module")
def qs():
    return Q.load_questions()


def test_build_is_deterministic():
    before = hashlib.sha256(Q.QUESTIONS_PATH.read_bytes()).hexdigest()
    Q.build()
    assert hashlib.sha256(Q.QUESTIONS_PATH.read_bytes()).hexdigest() == before


def test_ids_unique_and_counts(qs):
    assert len({q["id"] for q in qs}) == len(qs) == 700
    meta = json.loads(Q.META_PATH.read_text())
    assert meta["seed"] == Q.SEED and len(meta["repeat_sample"]) == 70


def test_ground_truth_matches_source(qs):
    units = {t: load_units(t) for t in Q.TEXTS}
    for q in qs:
        if q["task"] in ("reference", "continuation"):
            assert [units[q["text_id"]][i]["text"] for i in q["target_units"]] == [q["ground_truth"]], q["id"]


def test_continuation_rules(qs):
    for q in [q for q in qs if q["task"] == "continuation"]:
        given = q["prompt_vars"]["given"]
        assert Q.words(given) >= Q.GIVEN_MIN_WORDS, q["id"]
        assert Q.ANSWER_MIN_WORDS <= Q.words(q["ground_truth"]) <= Q.ANSWER_MAX_WORDS, q["id"]
        assert int(q["note"].split("=")[1]) + 1 == q["target_units"][0], q["id"]  # answer follows given


def test_traps_have_no_match_in_source(qs):
    for q in [q for q in qs if q["task"] == "trap" and q["trap_type"] == "misattribution"]:
        index, units, _ = load_index(q["text_id"])
        if q["play"]:
            from quotebench.scoring import SourceIndex
            index = SourceIndex([u["text"] for u in units if u["play"] == q["play"]])
        m = score_free([t.norm for t in tokenize(q["prompt_vars"]["content"])], index).match
        assert m is None or m.similarity < index.cfg.lower, (q["id"], m.text)


def test_prompts_fully_rendered(qs):
    for q in qs:
        for c in q["conditions"]:
            p = Q.render_prompt(q, c)
            assert not re.search(r"\{(?!\")\w+\}", p), (q["id"], c, p)


def _lookup(location="", cannot=False):
    return json.dumps({"location": location, "cannot_locate": cannot})


def test_lookup_scoring(qs):
    by = {q["id"]: q for q in qs}
    gen11 = by["t1-kjv-0001"]  # Genesis 1:1
    assert score_lookup(gen11, _lookup("Genesis 1:1"))["label"] == EXACT
    assert score_lookup(gen11, _lookup("Genesis chapter 1, verse 1"))["label"] == EXACT
    assert score_lookup(gen11, _lookup("Genesis 1:2"))["label"] == WRONG_PLACE
    assert score_lookup(gen11, _lookup("Genesis 1:99"))["label"] == FABRICATED
    assert score_lookup(gen11, _lookup("", True))["label"] == ABSTAINED
    assert score_lookup(gen11, _lookup("the first verse of the Bible"))["label"] == UNPARSEABLE
    trap = next(q for q in qs if q["task"] == "trap" and q["prompt_vars"].get("reference") == "John 22:1")
    assert score_lookup(trap, _lookup("", True))["label"] == CORRECT_REFUSAL
    assert score_lookup(trap, _lookup("John 22:1"))["label"] == TRAP_FABRICATED
    topic = by["t3-kjv-0001"]
    r = score_lookup(topic, _lookup("1 Corinthians 13:4"))
    assert r["label"] == EXACT and "THEME_UNCHECKED" in r["flags"]
