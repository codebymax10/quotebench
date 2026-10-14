"""Scoring every cached response, summary metrics, charts and the leaderboard page (SPEC §8, §10)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .questions import load_questions
from .runner import RESULTS_DIR, Cache, load_config
from .scoring import score_answer, score_lookup

SCORED_PATH = RESULTS_DIR / "scored.parquet"


def score_all(cache: Cache | None = None) -> pd.DataFrame:
    """One row per model × question × condition × repeat, with the label and its evidence."""
    cache = cache or Cache()
    questions = {q["id"]: q for q in load_questions()}
    labels = {m["id"]: m["label"] for m in load_config()["models"]}
    rows = []
    for rec in cache.rows():
        q = questions[rec["question_id"]]
        error = rec["error"] if rec["status"] == "error" else None
        scorer = score_lookup if rec["condition"] == "lookup" else score_answer
        s = scorer(q, rec["content"], error=error)
        if rec["finish_reason"] not in (None, "stop", "end_turn"):
            s["flags"] = s["flags"] + [f"FINISH_{str(rec['finish_reason']).upper()}"]
        rows.append({
            "model": rec["model"], "model_label": labels.get(rec["model"], rec["model"]),
            "question_id": q["id"], "task": q["task"], "text_id": q["text_id"], "play": q["play"],
            "fame": q["fame"], "trap_type": q["trap_type"], "should_abstain": q["should_abstain"],
            "condition": rec["condition"], "repeat": rec["repeat"],
            "label": s["label"], "quote_label": s["quote_label"], "similarity": s["similarity"],
            "target_similarity": s["target_similarity"], "flags": ",".join(s["flags"]),
            "location_correct": s["location_correct"], "parse_method": s["parse_method"],
            "match_text": s["match_text"], "match_units": list(s["match_units"]), "content": rec["content"],
            "finish_reason": rec["finish_reason"], "prompt_tokens": rec["prompt_tokens"],
            "completion_tokens": rec["completion_tokens"], "reasoning_tokens": rec["reasoning_tokens"],
            "cost": rec["cost"], "latency": rec["latency"], "timestamp": rec["timestamp"],
            "served_model": rec["served_model"], "provider": rec["provider"],
        })
    df = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SCORED_PATH, index=False)
    return df


# --------------------------------------------------------------------------------------
# Summary metrics (SPEC §8 "Headline metrics")

import datetime as dt
import json
import math

from .runner import CACHE_PATH, PRICING_PATH, archived_costs

SUMMARY_PATH = RESULTS_DIR / "summary.json"
FIGURES_DIR = RESULTS_DIR / "figures"
ANSWERED = ["EXACT", "MINOR", "ALTERED", "FABRICATED", "WRONG_PLACE"]


def wilson(k: int, n: int, z: float = 1.96) -> dict:
    """Rate with a 95% Wilson score interval."""
    if n == 0:
        return {"k": 0, "n": 0, "rate": None, "lo": None, "hi": None}
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {"k": int(k), "n": int(n), "rate": p, "lo": max(0.0, c - h), "hi": min(1.0, c + h)}


def quote_metrics(d: pd.DataFrame) -> dict:
    """Headline metrics for one slice of baseline/cautious answers (DECISIONS D15).

    Correct = verbatim: every word matches the named edition letter for letter (punctuation
    and capitals ignored); a complete quote with extra text after it also counts. Everything
    else is wrong, broken down into spelling only, incomplete, altered, wrong place, made up.
    Base: answered questions that have a real answer; ``correct_strict`` also counts
    unreadable answers (e.g. thought until the token limit) as wrong (D14).
    """
    real = d[~d["should_abstain"] & ~d["label"].isin(["UNPARSEABLE", "ERROR"])]
    answered = real[real["label"].isin(ANSWERED)]
    traps = d[d["should_abstain"] & d["label"].isin(["CORRECT_REFUSAL", "TRAP_FABRICATED"])]
    loc = d[(d["task"] == "topic") & d["location_correct"].notna()]
    n = len(answered)
    unreadable = int((d[~d["should_abstain"]]["label"] == "UNPARSEABLE").sum())
    partial = answered["flags"].fillna("").str.contains("PARTIAL")
    correct = int(((answered["label"] == "EXACT") & ~partial).sum())
    return {
        "correct": wilson(correct, n),
        "correct_strict": wilson(correct, n + unreadable),
        "spelling_only": wilson(int(((answered["label"] == "MINOR") & ~partial).sum()), n),
        "incomplete": wilson(int((answered["label"].isin(["EXACT", "MINOR"]) & partial).sum()), n),
        "altered": wilson((answered["label"] == "ALTERED").sum(), n),
        "wrong_place": wilson((answered["label"] == "WRONG_PLACE").sum(), n),
        "fabricated": wilson((answered["label"] == "FABRICATED").sum(), n),
        "abstained": wilson((real["label"] == "ABSTAINED").sum(), len(real)),
        "trap_failure": wilson((traps["label"] == "TRAP_FABRICATED").sum(), len(traps)),
        "location_error": wilson((loc["location_correct"] == False).sum(), len(loc)),  # noqa: E712
        "unparseable": unreadable,
        "errors": int((d["label"] == "ERROR").sum()),
        "total": int(len(d)),
    }


def lookup_metrics(d: pd.DataFrame) -> dict:
    """Lookup condition: an error is a reference that does not exist or is not the one asked for."""
    real = d[~d["should_abstain"] & ~d["label"].isin(["UNPARSEABLE", "ERROR"])]
    answered = real[real["label"].isin(ANSWERED)]
    traps = d[d["should_abstain"] & d["label"].isin(["CORRECT_REFUSAL", "TRAP_FABRICATED"])]
    return {
        "wrong_reference": wilson(answered["label"].isin(["WRONG_PLACE", "FABRICATED"]).sum(), len(answered)),
        "nonexistent_reference": wilson((answered["label"] == "FABRICATED").sum(), len(answered)),
        "abstained": wilson((real["label"] == "ABSTAINED").sum(), len(real)),
        "trap_failure": wilson((traps["label"] == "TRAP_FABRICATED").sum(), len(traps)),
        "unparseable": int((d["label"] == "UNPARSEABLE").sum()),
        "total": int(len(d)),
    }


def summarise(df: pd.DataFrame | None = None) -> dict:
    df = df if df is not None else pd.read_parquet(SCORED_PATH)
    cfg = load_config()
    from .questions import META_PATH, load_questions

    n_questions = len(load_questions())
    expected_calls = len(__import__("quotebench.runner", fromlist=["build_jobs"]).build_jobs(["x/x"]))
    main = df[df["repeat"] == 0]
    status = "draft"  # becomes "released" at v1.0 release
    out = {
        "benchmark": "QuoteBench", "version": json.loads(META_PATH.read_text())["version"],
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "status": status, "n_questions": n_questions, "expected_calls_per_model": expected_calls,
        "scoring": {k: v for k, v in __import__("yaml").safe_load((ROOT_CONFIG / "scoring.yaml").read_text()).items()
                    if k in ("status", "thresholds", "partial_min_words")},
        "models": [], "per_model": {},
    }
    pricing = json.loads(PRICING_PATH.read_text()) if PRICING_PATH.exists() else {"models": {}}
    archived = archived_costs()
    for m in cfg["models"]:
        mid = m["id"]
        d = main[main["model"] == mid]
        info = {k: m.get(k) for k in ("id", "label", "provider", "role", "note")}
        info["api"] = m.get("api", "openrouter")
        info["hosts"] = sorted(x for x in d["provider"].dropna().unique()) if len(d) else []
        info["calls_done"] = int((df["model"] == mid).sum())
        # incl. answers that were later replaced (dry runs, cut-off answers re-asked, D16)
        info["cost_usd"] = float(df.loc[df["model"] == mid, "cost"].fillna(0).sum()) + archived.get(mid, 0.0)
        info["run_dates"] = [d["timestamp"].min()[:10], d["timestamp"].max()[:10]] if len(d) else []
        info["mean_output_tokens"] = float(d["completion_tokens"].mean()) if len(d) else None
        out["models"].append(info)
        if d.empty:
            continue
        pm = {}
        for cond in ("baseline", "cautious"):
            dc = d[d["condition"] == cond]
            pm[cond] = quote_metrics(dc)
            pm[cond]["by_text"] = {t: quote_metrics(g) for t, g in dc.groupby("text_id")}
            pm[cond]["by_task"] = {t: quote_metrics(g) for t, g in dc.groupby("task")}
            pm[cond]["by_fame"] = {f: quote_metrics(g) for f, g in dc[dc["fame"].notna()].groupby("fame")}
        # like-for-like comparison of the three conditions on the questions that have a lookup version
        lk = d[d["condition"] == "lookup"]
        ids = set(lk["question_id"])
        sub = d[d["question_id"].isin(ids)]
        pm["lookup"] = lookup_metrics(lk)
        pm["lookup_subset"] = {
            "n_questions": len(ids),
            "baseline": quote_metrics(sub[sub["condition"] == "baseline"]),
            "cautious": quote_metrics(sub[sub["condition"] == "cautious"]),
        }
        # run-to-run stability on the repeat sample (baseline, 4 runs)
        rep = df[(df["model"] == mid) & (df["condition"] == "baseline")]
        reps = rep.groupby("question_id")["label"].agg(list)
        reps = reps[reps.map(len) == 4]
        pm["stability"] = wilson(int(sum(len(set(x)) == 1 for x in reps)), len(reps))
        out["per_model"][mid] = pm
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(out, indent=1, default=str) + "\n", encoding="utf-8")
    return out


from .sources import ROOT as _ROOT  # noqa: E402

ROOT_VALIDATION = _ROOT / "validation"
ROOT_CONFIG = _ROOT / "config"


# --------------------------------------------------------------------------------------
# Figures (PNG + SVG, light theme, for README / paper). Palette: dataviz reference palette,
# categorical slots 1-3 validated (scripts/validate_palette.js) in fixed order.

INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
SLOT = ["#2a78d6", "#eb6834", "#1baf7a"]
SLOT4 = "#eda100"
BLUE_LIGHT = "#86b6ef"


def _models_with_data(summary: dict) -> list[dict]:
    ms = [m for m in summary["models"] if m["id"] in summary["per_model"]]
    # ranked by the strict score: an answer the model never finished counts as wrong (D14, D16)
    return sorted(ms, key=lambda m: -(summary["per_model"][m["id"]]["baseline"]["correct_strict"]["rate"] or 0))


def _style(ax, xmax: float):
    import matplotlib.ticker as mt

    ax.set_xlim(0, xmax)
    ax.xaxis.set_major_formatter(mt.PercentFormatter(1.0, decimals=0))
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    ax.invert_yaxis()


def _save(fig, name: str, caption: str) -> None:
    fig.text(0.01, 0.01, caption, fontsize=8, color=INK2, ha="left", va="bottom", wrap=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        fig.savefig(FIGURES_DIR / f"{name}.{ext}", dpi=200, facecolor=SURFACE, bbox_inches="tight")


def make_figures(summary: dict) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "sans-serif", "font.size": 9, "text.color": INK,
                         "axes.labelcolor": INK2, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE})
    models = _models_with_data(summary)
    if not models:
        return []
    expected = summary["expected_calls_per_model"]
    labels = [m["label"] + ("" if m["calls_done"] >= expected else " *") for m in models]
    pm = [summary["per_model"][m["id"]] for m in models]
    y = list(range(len(models)))
    h = 0.5
    draft = "DRAFT — scorer not yet validated by a human. " if summary["status"] != "validated" else ""
    if any(m["calls_done"] < expected for m in models):
        draft += "* still running: partial data. "
    names = []

    # 1 — how often the quote was wrong, and how
    fig, ax = plt.subplots(figsize=(7.5, 0.45 * len(models) + 1.6))
    nearly = lambda b: {"rate": (b["spelling_only"]["rate"] or 0) + (b["incomplete"]["rate"] or 0)}
    parts = [("Made up", lambda b: b["fabricated"]), ("Altered", lambda b: b["altered"]),
             ("Real, wrong place", lambda b: b["wrong_place"]), ("Spelling only / incomplete", nearly)]
    left = [0.0] * len(models)
    for (name, get), color in zip(parts, SLOT + [SLOT4]):
        vals = [get(p["baseline"])["rate"] or 0 for p in pm]
        ax.barh(y, vals, left=left, height=h, color=color, edgecolor=SURFACE, linewidth=1, label=name)
        left = [a + b for a, b in zip(left, vals)]
    xmax = max(0.05, max(left) * 1.3)
    for i, p in enumerate(pm):
        ax.text(left[i] + xmax * 0.01, i, f"{p['baseline']['correct']['rate']:.0%} correct", va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, labels)
    _style(ax, xmax)
    ax.set_title("How often each model's word-for-word quotation was wrong", loc="left", fontsize=11, color=INK, pad=22)
    ax.legend(ncol=4, loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, fontsize=8, handlelength=1)
    ns = [p["baseline"]["correct"]["n"] for p in pm]
    _save(fig, "1_errors_by_model", f"{draft}Plain prompt. Share of answered questions that have a real answer "
          f"(n = {min(ns)}–{max(ns)} per model). Correct = every word matches the edition (punctuation and "
          "capitals ignored). The split of wrong answers into kinds is approximate.")
    plt.close(fig)
    names.append("1_errors_by_model")

    # 2 — famous vs random passages (dumbbell of exact rate)
    fig, ax = plt.subplots(figsize=(7.5, 0.45 * len(models) + 1.6))
    for i, p in enumerate(pm):
        f = p["baseline"]["by_fame"].get("famous", {}).get("correct", {}).get("rate")
        r = p["baseline"]["by_fame"].get("random", {}).get("correct", {}).get("rate")
        if f is None or r is None:
            continue
        ax.plot([r, f], [i, i], color="#c3c2b7", linewidth=2, solid_capstyle="round", zorder=1)
        ax.scatter([r], [i], s=60, color=BLUE_LIGHT, edgecolor=SURFACE, linewidth=2, zorder=2, label="Random passages" if i == 0 else None)
        ax.scatter([f], [i], s=60, color=SLOT[0], edgecolor=SURFACE, linewidth=2, zorder=3, label="Famous passages" if i == 0 else None)
    ax.set_yticks(y, labels)
    _style(ax, 1.0)
    ax.set_title("Correct word-for-word quotation: famous vs random passages", loc="left", fontsize=11, color=INK, pad=22)
    ax.legend(ncol=2, loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, fontsize=8)
    nf = [p["baseline"]["by_fame"].get("famous", {}).get("correct", {}).get("n", 0) for p in pm]
    nr = [p["baseline"]["by_fame"].get("random", {}).get("correct", {}).get("n", 0) for p in pm]
    _save(fig, "2_famous_vs_random", f"{draft}Plain prompt, 'quote this reference' and 'what comes next' questions. "
          f"Answered famous n = {min(nf)}–{max(nf)}, random n = {min(nr)}–{max(nr)} per model.")
    plt.close(fig)
    names.append("2_famous_vs_random")

    # 3 — plain vs only-if-sure vs lookup, same questions (Bible + Constitution)
    fig, ax = plt.subplots(figsize=(7.5, 0.6 * len(models) + 1.6))
    bh = 0.25
    series = [("Plain prompt", lambda p: p["lookup_subset"]["baseline"]),
              ("Only if sure", lambda p: p["lookup_subset"]["cautious"]),
              ("Lookup (model gives a reference)", None)]
    for k, ((name, get), color) in enumerate(zip(series, SLOT)):
        vals = []
        for p in pm:
            if get is None:
                vals.append(p["lookup"]["wrong_reference"]["rate"] or 0)
            else:
                m = get(p)
                vals.append(1 - m["correct"]["rate"] if m["correct"]["rate"] is not None else 0)
        ax.barh([i + (k - 1) * bh for i in y], vals, height=bh * 0.9, color=color, edgecolor=SURFACE, linewidth=1, label=name)
    ax.set_yticks(y, labels)
    _style(ax, max(0.05, ax.get_xlim()[1]))
    ax.set_title("Wrong answers by prompting condition", loc="left", fontsize=11, color=INK, pad=22)
    ax.legend(ncol=3, loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, fontsize=8)
    nq = max(p["lookup_subset"]["n_questions"] for p in pm)
    _save(fig, "3_conditions", f"{draft}Same {nq} questions (Bible and Constitution: quote a reference, quote on a topic, traps). "
          "Plain / only-if-sure: not word-for-word correct, of answered. Lookup: reference wrong or nonexistent, of answered.")
    plt.close(fig)
    names.append("3_conditions")

    # 4 — trap failure rate (single series, 95% CI whiskers)
    fig, ax = plt.subplots(figsize=(7.5, 0.45 * len(models) + 1.4))
    vals = [p["baseline"]["trap_failure"] for p in pm]
    ax.barh(y, [v["rate"] or 0 for v in vals], height=h, color=SLOT[0])
    for i, v in enumerate(vals):
        if v["rate"] is not None:
            ax.plot([v["lo"], v["hi"]], [i, i], color=INK2, linewidth=1)
            ax.text(v["hi"] + 0.01, i, f"{v['rate']:.0%}", va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, labels)
    _style(ax, max(0.1, max((v["hi"] or 0) for v in vals) * 1.3))
    ax.set_title("Trick questions: how often the model quoted something that does not exist", loc="left", fontsize=11, color=INK, pad=10)
    nt = [v["n"] for v in vals]
    _save(fig, "4_trap_failure", f"{draft}Plain prompt. n = {min(nt)}–{max(nt)} trap questions per model; lines are 95% Wilson intervals.")
    plt.close(fig)
    names.append("4_trap_failure")
    return names


# --------------------------------------------------------------------------------------
# Leaderboard page (static, no framework, no build step: docs/index.html)

PAGE_TEMPLATE = Path(__file__).with_name("leaderboard.html")
PAGE_PATH = _ROOT / "docs" / "index.html"


def build_page(summary: dict) -> Path:
    data = json.dumps(summary, default=str).replace("</", "<\\/")
    PAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PAGE_PATH.write_text(PAGE_TEMPLATE.read_text(encoding="utf-8").replace("__SUMMARY_JSON__", data), encoding="utf-8")
    return PAGE_PATH


# --------------------------------------------------------------------------------------
# README results table (numbers only, generated from summary.json)

README_PATH = _ROOT / "README.md"


def readme_table(summary: dict) -> str:
    rows = []
    for m in _models_with_data(summary):
        b = summary["per_model"][m["id"]]["baseline"]
        f = lambda v: "–" if v["rate"] is None else f"{100 * v['rate']:.1f}%"  # noqa: E731
        rows.append(f"| {m['label']} | {f(b['correct_strict'])} | {f(b['correct'])} | {f(b['fabricated'])} "
                    f"| {f(b['trap_failure'])} | {b['correct']['n']} |")
    head = ("| Model | Correct (strict) | Correct | Made up | Fell for trick questions | Answered |\n"
            "|---|---|---|---|---|---|")
    note = (f"\n\nPlain prompt; shares of answered questions that have a real answer. Ranked by *Correct "
            f"(strict)*, which also counts answers the model never finished (it reasoned past the token "
            f"limit) as wrong; *Correct* leaves those out. Generated "
            f"{summary['generated'][:10]} from `results/summary.json`; 95% intervals and all breakdowns "
            f"are in that file and on the leaderboard.")
    return head + "\n" + "\n".join(rows) + note


def update_readme(summary: dict) -> bool:
    if not README_PATH.exists():
        return False
    text = README_PATH.read_text(encoding="utf-8")
    start, end = "<!-- results:start -->", "<!-- results:end -->"
    if start not in text or end not in text:
        return False
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    README_PATH.write_text(f"{before}{start}\n{readme_table(summary)}\n{end}{after}", encoding="utf-8")
    return True
