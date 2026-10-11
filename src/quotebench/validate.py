"""Human validation of the scorer (SPEC §8).

``export``: draws a stratified random sample of scored answers (fixed seed) and writes
  - ``validation/labeling_sheet.csv`` — what the human labeller sees: the question, the right
    passage, the model's answer and the closest real passage. No automatic label, no similarity.
  - ``validation/sample_key.csv`` — the same items with the automatic label and similarity, kept
    apart so the labeller is not anchored by them.
``agreement``: compares the human labels with the scorer's — overall agreement, Cohen's kappa,
  confusion matrix, every disagreement — and re-scores the sample under alternative settings
  (thresholds, MINOR rule) so threshold choices are made on evidence.
"""

from __future__ import annotations

import collections
import csv
import random
from dataclasses import replace
from pathlib import Path

import pandas as pd

from .questions import load_questions
from .report import SCORED_PATH
from .scoring import ScoringConfig, SourceIndex, parse_response
from .sources import ROOT, load_units

VALIDATION_DIR = ROOT / "validation"
SHEET_PATH = VALIDATION_DIR / "labeling_sheet.csv"
KEY_PATH = VALIDATION_DIR / "sample_key.csv"
SEED = 8150
SAMPLE_SIZE = 150

# How many items to draw per automatic label (rare labels are over-sampled so they can be checked).
STRATA = {"EXACT": 30, "MINOR": 15, "ALTERED": 30, "FABRICATED": 30, "WRONG_PLACE": 15,
          "TRAP_FABRICATED": 15, "ABSTAINED": 5, "CORRECT_REFUSAL": 5, "UNPARSEABLE": 5}

LABELS = ["EXACT", "MINOR", "ALTERED", "FABRICATED", "WRONG_PLACE", "ABSTAINED",
          "CORRECT_REFUSAL", "TRAP_FABRICATED", "UNPARSEABLE"]


def describe_units(text_id: str, idxs: list[int], units: list[dict]) -> str:
    """Human-readable location of matched units ("John 3:16-17", "Hamlet 3.1", "Chapter 4")."""
    if not idxs:
        return ""
    us = [units[i] for i in idxs]
    u = us[0]
    if text_id == "bible_kjv":
        end = f"-{us[-1]['verse']}" if len(us) > 1 and us[-1]["chapter"] == u["chapter"] else ""
        return f"{u['book']} {u['chapter']}:{u['verse']}{end}"
    if text_id == "shakespeare":
        return f"{u['play']} {u['act']}.{u['scene']}" + (" (prologue)" if u["scene"] == 0 else "")
    if text_id == "us_constitution":
        if u["part"] == "preamble":
            return "Preamble"
        head = f"Article {u['article']}" if u["part"] == "article" else f"Amendment {u['amendment']}"
        if u["section"] is not None:
            head += f", Section {u['section']}"
        return f"{head}, Clause {u['clause']}"
    return "Introduction" if u["chapter"] == 0 else f"Chapter {u['chapter']}"


def _asked(q: dict) -> str:
    v = q["prompt_vars"]
    if q["task"] == "reference":
        return f"Quote {v['reference']}"
    if q["task"] == "continuation":
        return f"Quote the passage that comes right after: “{v['given']}”"
    if q["task"] == "topic":
        return f"Give a verbatim quote about {v['theme']}, with its location"
    if q["trap_type"] == "misattribution":
        return f"TRAP: quote the passage that says “{v['content']}” (it is not in the text)"
    if q["trap_type"] == "absent_topic":
        return f"TRAP: quote about {v['theme']} (the text never covers it)"
    return f"TRAP: quote {v['reference']} (it does not exist)"


def export(df: pd.DataFrame | None = None, size: int = SAMPLE_SIZE) -> tuple[Path, Path]:
    df = df if df is not None else pd.read_parquet(SCORED_PATH)
    pool = df[(df["condition"] != "lookup") & (df["repeat"] == 0) & (df["label"] != "ERROR")].copy()
    rng = random.Random(SEED)
    picked: list[int] = []
    leftovers: list[int] = []
    for label, n in STRATA.items():
        rows = sorted(pool.index[pool["label"] == label].tolist())
        rng.shuffle(rows)
        picked += rows[:n]
        leftovers += rows[n:]
    rng.shuffle(leftovers)
    picked += leftovers[: max(0, size - len(picked))]
    picked = picked[:size]
    rng.shuffle(picked)  # mix the strata so the sheet does not reveal them by position

    questions = {q["id"]: q for q in load_questions()}
    units = {t: load_units(t) for t in pool["text_id"].unique()}
    sheet, key = [], []
    for n, i in enumerate(picked, start=1):
        r = pool.loc[i]
        q = questions[r["question_id"]]
        parsed = parse_response(r["content"])
        match_units = [int(u) for u in r["match_units"]] if r["match_units"] is not None else []
        source = q["text_id"] + (f" ({q['play']})" if q.get("play") else "")
        correct = q["ground_truth"] or ("(should refuse: it does not exist)" if q["should_abstain"]
                                         else "(any real passage on the theme)")
        sheet.append({
            "item": n, "text": source, "what_was_asked": _asked(q), "correct_passage": correct,
            "ai_said_cannot_quote": "yes" if parsed.ok and parsed.refused else ("unreadable" if not parsed.ok else "no"),
            "ai_quote": parsed.quote if parsed.ok else (r["content"] if isinstance(r["content"], str) else "(empty: no answer)")[:1500],
            "ai_location": parsed.location if parsed.ok else "",
            "closest_real_passage": r["match_text"] if isinstance(r["match_text"], str) else "",
            "closest_passage_location": describe_units(q["text_id"], match_units, units[q["text_id"]]),
            "your_label": "", "your_note": "",
        })
        key.append({"item": n, "model": r["model"], "question_id": r["question_id"], "condition": r["condition"],
                    "auto_label": r["label"], "quote_label": r["quote_label"], "similarity": r["similarity"],
                    "target_similarity": r["target_similarity"], "flags": r["flags"],
                    "location_correct": r["location_correct"]})
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(sheet).to_csv(SHEET_PATH, index=False, quoting=csv.QUOTE_ALL)
    pd.DataFrame(key).to_csv(KEY_PATH, index=False)
    return SHEET_PATH, KEY_PATH


# --------------------------------------------------------------------------------------
# Agreement


def cohen_kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = collections.Counter(a), collections.Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def _normalise_label(x: str) -> str:
    x = (x or "").strip().upper().replace(" ", "_").replace("-", "_")
    aliases = {"WRONGPLACE": "WRONG_PLACE", "FAB": "FABRICATED", "ALT": "ALTERED", "TRAP": "TRAP_FABRICATED",
               "REFUSAL": "CORRECT_REFUSAL", "ABSTAIN": "ABSTAINED"}
    return aliases.get(x, x)


def rescore(key: pd.DataFrame, cfg: ScoringConfig) -> list[str]:
    """Labels for the sample items under an alternative scoring config."""
    from . import scoring as S
    import sqlite3, json  # noqa: E401
    from .runner import CACHE_PATH

    questions = {q["id"]: q for q in load_questions()}
    db = sqlite3.connect(CACHE_PATH)
    saved = dict(S._INDEXES)
    S._INDEXES.clear()
    try:
        for t in {questions[q]["text_id"] for q in key["question_id"]}:
            units = load_units(t)
            S._INDEXES[t] = (SourceIndex([u["text"] for u in units], cfg), units,
                             frozenset(u["speaker"] for u in units if u.get("speaker")))
        out = []
        for _, r in key.iterrows():
            content = db.execute("SELECT content FROM calls WHERE model=? AND question_id=? AND condition=? AND repeat=0",
                                 (r["model"], r["question_id"], r["condition"])).fetchone()[0]
            out.append(S.score_answer(questions[r["question_id"]], content)["label"])
        return out
    finally:
        S._INDEXES.clear()
        S._INDEXES.update(saved)


def agreement() -> dict:
    sheet = pd.read_csv(SHEET_PATH)
    key = pd.read_csv(KEY_PATH)
    df = sheet.merge(key, on="item")
    df["human"] = df["your_label"].fillna("").map(_normalise_label)
    unknown = sorted(set(df.loc[df["human"] != "", "human"]) - set(LABELS))
    if unknown:
        raise ValueError(f"unknown labels in your_label: {unknown} (allowed: {', '.join(LABELS)})")
    done = df[df["human"] != ""].copy()
    if done.empty:
        raise ValueError("no human labels yet: fill in the your_label column of validation/labeling_sheet.csv")
    human, auto = done["human"].tolist(), done["auto_label"].tolist()
    result = {
        "n_labelled": len(done), "n_total": len(df),
        "agreement": sum(h == a for h, a in zip(human, auto)) / len(done),
        "kappa": cohen_kappa(human, auto),
        "confusion": pd.crosstab(done["human"], done["auto_label"], rownames=["human"], colnames=["scorer"]),
        "disagreements": done.loc[done["human"] != done["auto_label"],
                                  ["item", "what_was_asked", "ai_quote", "closest_real_passage", "human",
                                   "auto_label", "similarity", "flags"]],
    }
    base = ScoringConfig.load()
    variants = {"current": base, "MINOR by similarity (spec literal)": replace(base, minor_rule="similarity")}
    for upper in (0.95, 0.97, 0.99):
        for lower in (0.70, 0.75, 0.80, 0.85):
            variants[f"upper={upper} lower={lower}"] = replace(base, upper=upper, lower=lower)
    rows = []
    for name, cfg in variants.items():
        labels = rescore(done, cfg)
        rows.append({"setting": name, "agreement": sum(h == a for h, a in zip(human, labels)) / len(done),
                     "kappa": cohen_kappa(human, labels)})
    result["sensitivity"] = pd.DataFrame(rows)
    return result
