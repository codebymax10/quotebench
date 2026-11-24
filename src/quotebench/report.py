"""Scoring every cached response, summary metrics, charts and the leaderboard page (SPEC §8, §10)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .questions import load_questions
from .runner import RESULTS_DIR, Cache, load_config
from .scoring import score_answer, score_lookup

SCORED_PATH = RESULTS_DIR / "scored.parquet"
HOST_ERROR = "the host ended the response with an error"


def call_error(rec: dict) -> str | None:
    """Why a call counts as ERROR (SPEC §6: never as a wrong answer), or None.

    A call fails as a whole, or the host stops in the middle of the answer and says so with the
    finish reason "error"; then the text so far is not an answer.
    """
    if rec["status"] == "error":
        return rec["error"]
    return HOST_ERROR if rec["finish_reason"] == "error" else None


def score_all(cache: Cache | None = None) -> pd.DataFrame:
    """One row per model × question × condition × repeat, with the label and its evidence."""
    cache = cache or Cache()
    questions = {q["id"]: q for q in load_questions()}
    labels = {m["id"]: m["label"] for m in load_config()["models"]}
    rows = []
    for rec in cache.rows():
        q = questions[rec["question_id"]]
        error = call_error(rec)
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

# "draft" shows a warning banner on the leaderboard page; "released" does not.
RELEASE_STATUS = "released"
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
    unreadable answers (e.g. thought until the token limit) as wrong (D14), and
    ``correct_of_all`` also counts declined questions as not correct (coverage). Calls that ended
    in ERROR are in no rate.

    Trick questions: ``trap_failure`` is any quote given; ``trap_presented`` leaves out the answers
    that say themselves that the line is not from the named text (flag SOURCE_CORRECTED).
    """
    real = d[~d["should_abstain"] & ~d["label"].isin(["UNPARSEABLE", "ERROR"])]
    answered = real[real["label"].isin(ANSWERED)]
    traps = d[d["should_abstain"] & d["label"].isin(["CORRECT_REFUSAL", "TRAP_FABRICATED"])]
    loc = d[(d["task"] == "topic") & d["location_correct"].notna()]
    n = len(answered)
    unreadable = int((d[~d["should_abstain"]]["label"] == "UNPARSEABLE").sum())
    partial = answered["flags"].fillna("").str.contains("PARTIAL")
    correct = int(((answered["label"] == "EXACT") & ~partial).sum())
    fell = traps["label"] == "TRAP_FABRICATED"
    corrected = traps["flags"].fillna("").str.contains("SOURCE_CORRECTED")
    return {
        "correct": wilson(correct, n),
        "correct_strict": wilson(correct, n + unreadable),
        "correct_of_all": wilson(correct, len(real) + unreadable),
        "spelling_only": wilson(int(((answered["label"] == "MINOR") & ~partial).sum()), n),
        "incomplete": wilson(int((answered["label"].isin(["EXACT", "MINOR"]) & partial).sum()), n),
        "altered": wilson((answered["label"] == "ALTERED").sum(), n),
        "wrong_place": wilson((answered["label"] == "WRONG_PLACE").sum(), n),
        "fabricated": wilson((answered["label"] == "FABRICATED").sum(), n),
        "abstained": wilson((real["label"] == "ABSTAINED").sum(), len(real)),
        "trap_failure": wilson(fell.sum(), len(traps)),
        "trap_presented": wilson((fell & ~corrected).sum(), len(traps)),
        "location_error": wilson((loc["location_correct"] == False).sum(), len(loc)),  # noqa: E712
        "unparseable": unreadable,
        "errors": int((d["label"] == "ERROR").sum()),
        "total": int(len(d)),
    }


def lookup_metrics(d: pd.DataFrame) -> dict:
    """Lookup condition: an error is a reference that does not exist or is not the one asked for.

    ``wrong_reference_strict`` also counts unreadable answers as wrong (D14, D16).
    """
    real = d[~d["should_abstain"] & ~d["label"].isin(["UNPARSEABLE", "ERROR"])]
    answered = real[real["label"].isin(ANSWERED)]
    traps = d[d["should_abstain"] & d["label"].isin(["CORRECT_REFUSAL", "TRAP_FABRICATED"])]
    unreadable = int((d[~d["should_abstain"]]["label"] == "UNPARSEABLE").sum())
    wrong = int(answered["label"].isin(["WRONG_PLACE", "FABRICATED"]).sum())
    return {
        "wrong_reference": wilson(wrong, len(answered)),
        "wrong_reference_strict": wilson(wrong + unreadable, len(answered) + unreadable),
        "nonexistent_reference": wilson((answered["label"] == "FABRICATED").sum(), len(answered)),
        "abstained": wilson((real["label"] == "ABSTAINED").sum(), len(real)),
        "trap_failure": wilson((traps["label"] == "TRAP_FABRICATED").sum(), len(traps)),
        "unparseable": int((d["label"] == "UNPARSEABLE").sum()),
        "errors": int((d["label"] == "ERROR").sum()),
        "total": int(len(d)),
    }


def summarise(df: pd.DataFrame | None = None) -> dict:
    df = df if df is not None else pd.read_parquet(SCORED_PATH)
    cfg = load_config()
    from .questions import META_PATH, load_questions

    n_questions = len(load_questions())
    expected_calls = len(__import__("quotebench.runner", fromlist=["build_jobs"]).build_jobs(["x/x"]))
    main = df[df["repeat"] == 0]
    out = {
        "benchmark": "QuoteBench", "version": json.loads(META_PATH.read_text())["version"],
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "status": RELEASE_STATUS, "n_questions": n_questions, "expected_calls_per_model": expected_calls,
        "scoring": {k: v for k, v in __import__("yaml").safe_load((ROOT_CONFIG / "scoring.yaml").read_text()).items()
                    if k in ("status", "thresholds", "partial_min_words", "fragment_min_words")},
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
        # run-to-run stability on the repeat sample (baseline, 4 runs): the share of questions, of
        # every kind incl. trick questions, whose scorer label is the same in all four runs. It
        # says nothing about being right, and the wording may differ while the label is the same.
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


def pct(k: int, n: int) -> str:
    """k/n as a percentage with one decimal, halves rounded up (same rule as the leaderboard page)."""
    if not n:
        return "–"
    tenths = (2000 * int(k) + int(n)) // (2 * int(n))
    return f"{tenths // 10}.{tenths % 10}%"


def interval(v: dict) -> str:
    """95% interval of a ``wilson`` dict, e.g. ``94.6–97.7%``."""
    return "–" if v["rate"] is None else f"{100 * v['lo']:.1f}–{100 * v['hi']:.1f}%"


def n_range(ns) -> str:
    ns = [n for n in ns if n is not None]
    if not ns:
        return "0"
    return str(min(ns)) if min(ns) == max(ns) else f"{min(ns)}–{max(ns)}"


def wrong_strict(q: dict) -> tuple[int, int]:
    """(wrong, base) on the strict base: answered + unfinished, unfinished counted as wrong (D14, D16)."""
    c = q["correct_strict"]
    return c["n"] - c["k"], c["n"]


def lookup_strict(p: dict) -> tuple[int, int]:
    v = p["lookup"]["wrong_reference_strict"]
    return v["k"], v["n"]


def error_segments(q: dict) -> list[tuple[str, int]]:
    """Wrong answers by kind, as counts that add up to the wrong answers of ``correct_strict``."""
    return [("Made up", q["fabricated"]["k"]), ("Altered", q["altered"]["k"]),
            ("Real, wrong place", q["wrong_place"]["k"]),
            ("Spelling only / incomplete", q["spelling_only"]["k"] + q["incomplete"]["k"]),
            ("Unfinished", q["unparseable"])]


def trap_segments(q: dict) -> list[tuple[str, int]]:
    """The two parts of ``trap_failure``, as counts."""
    k = q["trap_presented"]["k"]
    return [("Presented as from the named text", k),
            ("Said itself that it is not from the named text", q["trap_failure"]["k"] - k)]


UNFINISHED_NOTE = ("Unfinished = no readable answer (nearly always: still reasoning at the token limit); "
                   "counted as wrong.")

FIG_W = 7.5  # inches


def _save(fig, name: str, title: str, caption: str) -> None:
    """Add the caption below the axes (the figure grows by the height of the caption) and write files."""
    import textwrap

    lines = textwrap.wrap(caption.replace("n = ", "n\u00a0=\u00a0"), 120)  # never break "n = …"
    plot_h = fig.get_size_inches()[1]
    cap_h = 0.15 * len(lines) + 0.1
    h = plot_h + cap_h
    fig.set_size_inches(FIG_W, h)
    fig.subplots_adjust(left=1.6 / FIG_W, right=0.97, top=1 - 0.6 / h, bottom=(cap_h + 0.35) / h)
    fig.text(0.1 / FIG_W, cap_h / h, "\n".join(lines), fontsize=8, color=INK2, ha="left", va="top")
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        meta = {"Title": title, "Description": caption}
        if ext == "svg":
            meta["Date"] = None  # no timestamp, so unchanged figures give unchanged files
        fig.savefig(FIGURES_DIR / f"{name}.{ext}", dpi=200, facecolor=SURFACE, bbox_inches="tight",
                    pad_inches=0.12, metadata=meta)


def make_figures(summary: dict) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "sans-serif", "font.size": 9, "text.color": INK, "svg.hashsalt": "quotebench",
                         "axes.labelcolor": INK2, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE})
    models = _models_with_data(summary)
    if not models:
        return []
    expected = summary["expected_calls_per_model"]
    labels = [m["label"] + ("" if m["calls_done"] >= expected else " *") for m in models]
    pm = [summary["per_model"][m["id"]] for m in models]
    y = list(range(len(models)))
    h = 0.5
    partial = "* still running: partial data. " if any(m["calls_done"] < expected for m in models) else ""
    title_at = lambda ax, t, pad=22: ax.set_title(t, loc="left", x=0, fontsize=11, color=INK, pad=pad)  # noqa: E731
    legend_at = lambda ax, ncol, **kw: ax.legend(  # noqa: E731
        ncol=ncol, loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, fontsize=8, borderaxespad=0.2,
        borderpad=0, columnspacing=1.2, handletextpad=0.5, **kw)
    names = []

    # 1 — how often the quote was wrong, and how (strict base, like the ranking)
    fig, ax = plt.subplots(figsize=(FIG_W, 0.4 * len(models) + 1.1))
    seg = [error_segments(p["baseline"]) for p in pm]
    bases = [p["baseline"]["correct_strict"]["n"] for p in pm]
    left = [0.0] * len(models)
    for j, color in enumerate(SLOT + [SLOT4, MUTED]):
        vals = [s[j][1] / n if n else 0 for s, n in zip(seg, bases)]
        ax.barh(y, vals, left=left, height=h, color=color, edgecolor=SURFACE, linewidth=0.8, label=seg[0][j][0])
        left = [a + b for a, b in zip(left, vals)]
    xmax = max(0.05, max(left) * 1.4)
    for i, p in enumerate(pm):
        c = p["baseline"]["correct_strict"]
        ax.text(left[i] + xmax * 0.01, i, f"{pct(c['k'], c['n'])} correct (strict)", va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, labels)
    _style(ax, xmax)
    title = "How often each model's word-for-word quotation was wrong"
    title_at(ax, title)
    legend_at(ax, 5, handlelength=1)
    _save(fig, "1_errors_by_model", title, f"{partial}Plain prompt. Share of answered + unfinished questions that "
          f"have a real answer (n = {n_range(bases)} per model); declined questions are not in the base. "
          "Correct (strict) = every word matches the edition (punctuation and capitals ignored). "
          f"{UNFINISHED_NOTE} The split of wrong answers into kinds is approximate and was not checked against "
          "human labels.")
    plt.close(fig)
    names.append("1_errors_by_model")

    # 2 — famous vs random passages (dumbbell of the strict correct rate)
    fig, ax = plt.subplots(figsize=(FIG_W, 0.4 * len(models) + 1.1))
    fame = [{f: p["baseline"]["by_fame"].get(f, {}).get("correct_strict") for f in ("famous", "random")} for p in pm]
    both = [(i, f) for i, f in enumerate(fame) if all(v and v["rate"] is not None for v in f.values())]
    for i, f in both:
        r, fa = f["random"]["rate"], f["famous"]["rate"]
        ax.plot([r, fa], [i, i], color="#c3c2b7", linewidth=2, solid_capstyle="round", zorder=1)
        # the random dot is larger, so it still shows as a ring when the two coincide
        ax.scatter([r], [i], s=80, color=BLUE_LIGHT, linewidth=0, zorder=2,
                   label="Random passages" if i == both[0][0] else None)
        ax.scatter([fa], [i], s=32, color=SLOT[0], linewidth=0, zorder=3,
                   label="Famous passages" if i == both[0][0] else None)
    ax.set_yticks(y, labels)
    _style(ax, 1.02)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    title = "Correct (strict) word-for-word quotation: famous vs random passages"
    title_at(ax, title)
    if both:
        legend_at(ax, 2)
    ns = lambda f: n_range([x[f]["n"] for _, x in both])  # noqa: E731
    _save(fig, "2_famous_vs_random", title, f"{partial}Plain prompt, 'quote this reference' and 'what comes next' "
          f"questions. Share of answered + unfinished questions quoted word for word (famous n = {ns('famous')}, "
          f"random n = {ns('random')} per model). {UNFINISHED_NOTE}")
    plt.close(fig)
    names.append("2_famous_vs_random")

    # 3 — plain vs only-if-sure vs lookup, same questions (Bible + Constitution), strict base
    fig, ax = plt.subplots(figsize=(FIG_W, 0.55 * len(models) + 1.1))
    bh = 0.27
    series = [("Plain prompt", lambda p: wrong_strict(p["lookup_subset"]["baseline"])),
              ("Only if sure", lambda p: wrong_strict(p["lookup_subset"]["cautious"])),
              ("Lookup (model gives a reference)", lookup_strict)]
    got = [[get(p) for p in pm] for _, get in series]
    xmax = max(0.05, max(k / n for row in got for k, n in row if n) * 1.15)
    for k, ((name, _), color) in enumerate(zip(series, SLOT)):
        ax.barh([i + (k - 1) * bh for i in y], [a / n if n else 0 for a, n in got[k]], height=bh * 0.88,
                color=color, linewidth=0, label=name)
        for i, (a, n) in enumerate(got[k]):
            ax.text((a / n if n else 0) + xmax * 0.006, i + (k - 1) * bh, pct(a, n), va="center", fontsize=6.5, color=INK2)
    ax.set_yticks(y, labels)
    _style(ax, xmax)
    title = "Wrong answers by prompting condition"
    title_at(ax, title)
    legend_at(ax, 3, handlelength=1)
    real = [n_range([n for _, n in row]) for row in got]
    _save(fig, "3_conditions", title, f"{partial}Same Bible and Constitution questions in all three conditions (quote a "
          f"reference, quote on a topic; trick questions left out). Answered + unfinished, per model: plain n = {real[0]}, "
          f"only if sure n = {real[1]}, lookup n = {real[2]}; declined questions are not in the base. Plain / only if sure: "
          f"not word for word. Lookup: reference wrong or nonexistent. {UNFINISHED_NOTE}")
    plt.close(fig)
    names.append("3_conditions")

    # 4 — trick questions: quotes given, in two parts (95% CI whiskers on the total)
    fig, ax = plt.subplots(figsize=(FIG_W, 0.4 * len(models) + 1.1))
    vals = [p["baseline"]["trap_failure"] for p in pm]
    shown = [p["baseline"]["trap_presented"] for p in pm]
    seg = [trap_segments(p["baseline"]) for p in pm]
    xmax = max(0.1, max((v["hi"] or 0) for v in vals) * 1.35)
    left = [0.0] * len(models)
    for j, color in enumerate((SLOT[0], BLUE_LIGHT)):
        w = [s[j][1] / v["n"] if v["n"] else 0 for s, v in zip(seg, vals)]
        ax.barh(y, w, left=left, height=h, color=color, linewidth=0, label=seg[0][j][0])
        left = [a + b for a, b in zip(left, w)]
    for i, (v, g) in enumerate(zip(vals, shown)):
        if v["rate"] is not None:
            ax.plot([v["lo"], v["hi"]], [i, i], color=INK2, linewidth=1)
            ax.text(v["hi"] + xmax * 0.012, i, f"{pct(v['k'], v['n'])}, {pct(g['k'], g['n'])} as genuine",
                    va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, labels)
    _style(ax, xmax)
    title = "Trick questions: gave a quote, and presented it as genuine"
    title_at(ax, title)
    legend_at(ax, 2, handlelength=1)
    _save(fig, "4_trap_failure", title, f"{partial}Plain prompt. Share of trick questions (readable answers, "
          f"n = {n_range([v['n'] for v in vals])} per model) on which the model gave a quote although there is none to give; any "
          "quote is a failure. Light part: the answer itself says that the line is not from the named text, or is from another "
          "work (found by a word rule). Lines are 95% Wilson intervals of the whole bar. Models in leaderboard order.")
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
# Generated tables in README.md and PAPER.md (numbers only, from summary.json). A table is written
# between <!-- name:start --> and <!-- name:end -->; a file or marker that is missing is left alone.

README_PATH = _ROOT / "README.md"
PAPER_PATH = _ROOT / "PAPER.md"
TEXT_LABELS = {"bible_kjv": "KJV Bible", "shakespeare": "Shakespeare", "us_constitution": "Constitution",
               "pride_prejudice": "Pride and Prejudice", "origin_species": "Origin of Species"}


def _md(head: list[str], rows: list[list[str]], note: str) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows]) + "\n\n" + note


def _cell(k: int, n: int) -> str:
    return f"{pct(k, n)} ({k}/{n})" if n else "–"


def _strict(q: dict | None) -> str:
    return _cell(q["correct_strict"]["k"], q["correct_strict"]["n"]) if q else "–"


def _with_interval(v: dict) -> str:
    return f"{_cell(v['k'], v['n'])}, {interval(v)}" if v["n"] else "–"


TRICK_HEADS = ["Gave a quote on a trick question", "of which presented as genuine"]
TRICK_NOTE = ("*Gave a quote on a trick question*: any quote although there is none to give; always a failure. *Of which "
              "presented as genuine*: without the answers that say themselves that the line is not from the named text, or "
              "is from another work (found by a word rule).")


def errors_note(summary: dict) -> str:
    """Calls that ended in ERROR, plain and cautious prompt: reported here, excluded from every rate."""
    found = []
    for m in _models_with_data(summary):
        b, c = (summary["per_model"][m["id"]][x]["errors"] for x in ("baseline", "cautious"))
        if b or c:
            found.append(f"{m['label']} {b} plain, {c} cautious")
    return f" Answers that the model's host ended with an error are in no rate: {'; '.join(found)}." if found else ""


def readme_table(summary: dict) -> str:
    rows, traps = [], []
    for m in _models_with_data(summary):
        b = summary["per_model"][m["id"]]["baseline"]
        f = lambda v: pct(v["k"], v["n"])  # noqa: E731
        traps.append(b["trap_failure"]["n"])
        rows.append([m["label"], f(b["correct_strict"]), f(b["correct"]), _with_interval(b["correct_of_all"]),
                     f(b["fabricated"]), f(b["trap_failure"]), f(b["trap_presented"]),
                     str(b["correct"]["n"]), str(b["unparseable"])])
    return _md(["Model", "Correct (strict)", "Correct", "Correct of all asked (k/n, 95% interval)", "Made up", *TRICK_HEADS,
                "Answered", "Unfinished"], rows,
               f"Plain prompt; questions that have a real answer. Ranked by *Correct (strict)*: share of *Answered* + "
               f"*Unfinished*, where an unfinished answer (no readable answer, nearly always because the model was "
               f"still reasoning at the token limit) counts as wrong. *Correct* and *Made up* are shares of *Answered* "
               f"only. Questions the model declined are in neither. *Correct of all asked*: correct answers as a share of "
               f"all questions with a real answer, so declining counts as not correct. {TRICK_NOTE} Both are shares of all "
               f"trick questions, n = {n_range(traps)} per model.{errors_note(summary)} "
               f"Generated {summary['generated'][:10]} from `results/summary.json`; 95% intervals and all breakdowns "
               f"are in that file and on the leaderboard.")


def stability_table(summary: dict) -> str:
    rows = []
    for m in _models_with_data(summary):
        v = summary["per_model"][m["id"]].get("stability")
        if v and v["n"]:
            rows.append([m["label"], _cell(v["k"], v["n"]), interval(v)])
    return _md(["Model", "Same label in all 4 runs", "95% interval"], rows,
               "Share of the repeated questions (fixed sample, plain prompt, all question types including trick "
               "questions) that got the same scorer label (exact, altered, made up, declined, …) in all four runs. "
               "It measures consistency, not correctness: the same wrong label four times counts as stable, and the "
               "wording may differ.")


def by_text_table(summary: dict) -> str:
    rows = []
    for m in _models_with_data(summary):
        bt = summary["per_model"][m["id"]]["baseline"]["by_text"]
        rows.append([m["label"]] + [_cell(*wrong_strict(bt[t])) if t in bt else "–" for t in TEXT_LABELS])
    return _md(["Model", *TEXT_LABELS.values()], rows,
               "Plain prompt. Share quoted wrong (not word for word), strict base: wrong / (answered + unfinished). "
               "Declined questions are not in the base, so n differs between models.")


def fame_table(summary: dict) -> str:
    rows = []
    for m in _models_with_data(summary):
        bf = summary["per_model"][m["id"]]["baseline"]["by_fame"]
        rows.append([m["label"], _strict(bf.get("famous")), _strict(bf.get("random"))])
    return _md(["Model", "Famous passages", "Random passages"], rows,
               "Plain prompt, quote-a-reference and what-comes-next questions. *Correct (strict)*: correct / (answered "
               "+ unfinished). Declined questions are not in the base.")


def conditions_table(summary: dict) -> str:
    rows, nq = [], 0
    for m in _models_with_data(summary):
        p = summary["per_model"][m["id"]]
        nq = max(nq, p["lookup_subset"]["n_questions"])
        rows.append([m["label"], _cell(*wrong_strict(p["lookup_subset"]["baseline"])),
                     _cell(*wrong_strict(p["lookup_subset"]["cautious"])), _cell(*lookup_strict(p))])
    return _md(["Model", "Plain", "Cautious (only if sure)", "Lookup"], rows,
               f"The same {nq} Bible and Constitution questions in all three conditions; the trick questions among them "
               "are not in these rates. Share wrong: wrong / (answered + unfinished), unfinished counted as wrong, "
               "declined questions not in the base. Plain and cautious: not word for word. Lookup: the reference is "
               "nonexistent or not the one asked for.")


def traps_table(summary: dict) -> str:
    rows = []
    for m in _models_with_data(summary):
        row = [m["label"]]
        for cond in ("baseline", "cautious"):
            for key in ("trap_failure", "trap_presented"):
                row.append(_with_interval(summary["per_model"][m["id"]][cond][key]))
        rows.append(row)
    return _md(["Model", *(f"{cond}: {head}" for cond in ("Plain", "Cautious")
                           for head in ("gave a quote", "of which presented as genuine"))], rows,
               "Trick questions (readable answers), where the right answer is that there is nothing to quote. "
               f"{TRICK_NOTE} Both are shares of all trick questions; k/n and 95% Wilson intervals.")


TABLES = {"results": readme_table, "stability": stability_table, "by_text": by_text_table, "fame": fame_table,
          "conditions": conditions_table, "traps": traps_table}


def update_blocks(path: Path, summary: dict) -> list[str]:
    """Rewrite the generated blocks that exist in ``path``; returns the names of the blocks found."""
    import re

    if not path.exists():
        return []
    text = new = path.read_text(encoding="utf-8")
    found = []
    for name, make in TABLES.items():
        # the block must not contain another marker, so a lost end marker never swallows prose
        block = re.compile(rf"(<!-- {name}:start -->)(?:(?!<!-- \w+:(?:start|end) -->).)*(<!-- {name}:end -->)", re.S)
        if block.search(new):
            found.append(name)
            new = block.sub(lambda m: f"{m[1]}\n{make(summary)}\n{m[2]}", new)
    if new != text:
        path.write_text(new, encoding="utf-8")
    return found


def update_readme(summary: dict) -> bool:
    """Refresh the generated tables in README.md and, if it exists, PAPER.md."""
    update_blocks(PAPER_PATH, summary)
    return "results" in update_blocks(README_PATH, summary)
