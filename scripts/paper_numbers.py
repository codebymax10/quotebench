"""Print every hand-written number in PAPER.md, labelled by section.

    .venv/bin/python scripts/paper_numbers.py

Reads results/scored.parquet, results/summary.json, results/raw/, results/archive/ and
data/questions.jsonl. Writes nothing and calls no API. Plain prompt (baseline), run 0, unless a
section says otherwise. Section 14 compares with the scoring before DECISIONS D19, which it reads
from git; without that commit (zip download, shallow clone) the comparison is skipped.
"""

from __future__ import annotations

import io
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))
from quotebench.scoring import normalize, parse_response  # noqa: E402

ANSWERED = ["EXACT", "MINOR", "ALTERED", "FABRICATED", "WRONG_PLACE"]
BEFORE = "cc1d009"  # results as first published, before the scorer fixes (DECISIONS D19)
PROSE = ["pride_prejudice", "origin_species"]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p, d = k / n, 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def w(k, n) -> str:
    p, lo, hi = wilson(int(k), int(n))
    return f"{100*p:.1f}% [{100*lo:.1f}, {100*hi:.1f}] ({int(k)}/{int(n)})"


def mcnemar(a: pd.Series, b: pd.Series) -> tuple[int, int, float]:
    """Exact (binomial) two-sided McNemar test; a, b are aligned booleans."""
    only_a, only_b = int((a & ~b).sum()), int((~a & b).sum())
    n = only_a + only_b
    return only_a, only_b, (binomtest(only_a, n, 0.5).pvalue if n else 1.0)


def holm(ps: list[float]) -> list[float]:
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    out, run = [0.0] * len(ps), 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - r) * ps[i]))
        out[i] = run
    return out


def head(s: str) -> None:
    print("\n" + "=" * 8, s)


def pv(p: float) -> str:
    return f"{p:.2g}" if p < 0.001 else f"{p:.3f}"


# ------------------------------------------------------------------------------- data
df = pd.read_parquet("results/scored.parquet")
df["fl"] = df["flags"].fillna("")
df["ok"] = (df["label"] == "EXACT") & ~df["fl"].str.contains("PARTIAL")
summary = json.loads(Path("results/summary.json").read_text())
questions = {q["id"]: q for q in map(json.loads, Path("data/questions.jsonl").read_text().splitlines())}
LABEL = {m["id"]: m["label"] for m in summary["models"]}

base = df[(df["condition"] == "baseline") & (df["repeat"] == 0)]
real = base[~base["should_abstain"]]


def counts(d: pd.DataFrame) -> dict:
    """Outcome counts for questions that have a real answer."""
    ans = d["label"].isin(ANSWERED)
    return {"n": len(d), "ok": int(d["ok"].sum()), "ans": int(ans.sum()), "wrong": int((ans & ~d["ok"]).sum()),
            "abst": int((d["label"] == "ABSTAINED").sum()), "unf": int((d["label"] == "UNPARSEABLE").sum()),
            "fab": int((d["label"] == "FABRICATED").sum()), "err": int((d["label"] == "ERROR").sum())}


C = {m: counts(g) for m, g in real.groupby("model")}
strict = lambda c: c["ok"] / (c["ans"] + c["unf"])  # noqa: E731
RANK = sorted(C, key=lambda m: -strict(C[m]))
RANK600 = sorted(C, key=lambda m: -C[m]["ok"])
for m in RANK:  # the summary must agree with the recomputation
    s = summary["per_model"][m]["baseline"]["correct_strict"]
    a = summary["per_model"][m]["baseline"]["correct_of_all"]
    assert (s["k"], s["n"]) == (C[m]["ok"], C[m]["ans"] + C[m]["unf"]), f"summary.json disagrees for {m}"
    assert (a["k"], a["n"]) == (C[m]["ok"], C[m]["n"] - C[m]["err"]), f"summary.json disagrees for {m}"

N = lambda c: c["n"] - c["err"]  # noqa: E731  real-answer questions that got an answer from the host

head("0 Data set")
print("answers scored:", len(df), "| per model:", df.groupby("model").size().unique(), "| models:", len(RANK))
print("questions:", len(questions), "| real-answer:", sum(not q["should_abstain"] for q in questions.values()))
print("ERROR labels:", int((df["label"] == "ERROR").sum()), "| UNPARSEABLE:", int((df["label"] == "UNPARSEABLE").sum()))
print("run dates:", sorted({t[:10] for t in df["timestamp"]}))

head("1 Ranking: strict (README), and out of all 600 real-answer questions")
for m in RANK:
    c = C[m]
    print(f"{LABEL[m]:22s} strict {w(c['ok'], c['ans']+c['unf'])} | of answered {w(c['ok'], c['ans'])} | "
          f"of 600 {w(c['ok'], N(c))} | declined {w(c['abst'], N(c))} | wrong quote {w(c['wrong'], N(c))} | "
          f"unfinished {c['unf']} host errors {c['err']} | made up of answered {w(c['fab'], c['ans'])}")
print("quoted although cannot_quote was true (counted as declined), real-answer questions:",
      {LABEL[m]: int(g.fl.str.contains("QUOTE_DESPITE_REFUSAL").sum()) for m, g in real.groupby("model")})
print("spelling only / incomplete of answered:", {LABEL[m]: (int((g.label == "MINOR").sum()), int((g.label.isin(["EXACT", "MINOR"]) & ~g.ok).sum())) for m, g in real.groupby("model")})
print("rank strict :", " > ".join(LABEL[m] for m in RANK))
print("rank of 600 :", " > ".join(LABEL[m] for m in RANK600))
print("rank by fewest wrong quotes:", " < ".join(f"{LABEL[m]} {C[m]['wrong']}" for m in sorted(C, key=lambda m: C[m]['wrong'])))

head("2 Paired McNemar (exact, two-sided). (a) all 600, abstained/unfinished = not correct; "
     "(b) only questions neither model declined, unfinished = not correct. Holm over all 36 pairs.")
ok = real.pivot(index="question_id", columns="model", values="ok")
lab = real.pivot(index="question_id", columns="model", values="label")
pairs = [(a, b) for i, a in enumerate(RANK) for b in RANK[i + 1:]]
R = {}
for a, b in pairs:
    good = (lab[a] != "ERROR") & (lab[b] != "ERROR")  # host errors: pair dropped
    keep = good & (lab[a] != "ABSTAINED") & (lab[b] != "ABSTAINED")
    R[a, b] = (*mcnemar(ok.loc[good, a], ok.loc[good, b]), int(keep.sum()), *mcnemar(ok.loc[keep, a], ok.loc[keep, b]),
               int(ok.loc[keep, a].sum()), int(ok.loc[keep, b].sum()))
ha, hb = holm([R[p][2] for p in pairs]), holm([R[p][6] for p in pairs])
H = {p: (x, y) for p, x, y in zip(pairs, ha, hb)}


def show_pair(a, b):
    if (a, b) not in R:
        a, b = b, a
    r = R[a, b]
    print(f"{LABEL[a]:20s} vs {LABEL[b]:22s} (a) only-1st {r[0]} only-2nd {r[1]} p={pv(r[2])} holm={pv(H[a,b][0])} | "
          f"(b) n={r[3]} correct {r[7]} vs {r[8]} only-1st {r[4]} only-2nd {r[5]} p={pv(r[6])} holm={pv(H[a,b][1])}")


print("- adjacent in the strict ranking")
for a, b in zip(RANK, RANK[1:]):
    show_pair(a, b)
print("- adjacent in the out-of-600 ranking")
for a, b in zip(RANK600, RANK600[1:]):
    show_pair(a, b)
S = {v: k for k, v in LABEL.items()}
print("- others used in the text")
for a, b in [("Claude Opus 5.5", "Claude Sonnet 5.5"), ("Claude Sonnet 4.6", "Claude Haiku 5.5"),
             ("Claude Haiku 5.5", "Claude Haiku 4.5"), ("Claude Sonnet 5.5", "Claude Sonnet 4.6"),
             ("GPT-6 Luna", "DeepSeek V4 Pro"), ("Claude Sonnet 4.6", "Gemini 3.1 Flash Lite")]:
    show_pair(S[a], S[b])
print("- pairs not significant at Holm 0.05: (a)", [f"{LABEL[a]}/{LABEL[b]}" for (a, b) in pairs if H[a, b][0] >= .05],
      "(b)", [f"{LABEL[a]}/{LABEL[b]}" for (a, b) in pairs if H[a, b][1] >= .05])

head("3 By text (correct of answered + unfinished; declined)")
TEXTS = ["bible_kjv", "us_constitution", "shakespeare", "pride_prejudice", "origin_species"]
for m in RANK:
    print(f"{LABEL[m]:22s}", " | ".join(f"{t[:9]} {w((c:=counts(g))['ok'], c['ans']+c['unf'])} decl {c['abst']}/{c['n']}"
                                       for t in TEXTS for g in [real[(real.model == m) & (real.text_id == t)]]))
print("- Bible vs both prose texts together")
for m in RANK:
    g = real[real.model == m]
    b, p = counts(g[g.text_id == "bible_kjv"]), counts(g[g.text_id.isin(PROSE)])
    print(f"{LABEL[m]:22s} Bible {w(b['ok'], b['ans']+b['unf'])} prose {w(p['ok'], p['ans']+p['unf'])} | "
          f"of all: Bible {w(b['ok'], N(b))} prose {w(p['ok'], N(p))} | declined Bible {b['abst']}/{b['n']} prose {p['abst']}/{p['n']}")
print("- continuation task only, 50 Bible vs 100 prose questions")
for m in RANK:
    g = real[(real.model == m) & (real.task == "continuation")]
    b, p = counts(g[g.text_id == "bible_kjv"]), counts(g[g.text_id.isin(PROSE)])
    print(f"{LABEL[m]:22s} Bible {w(b['ok'], b['ans']+b['unf'])} prose {w(p['ok'], p['ans']+p['unf'])} | of all: Bible {w(b['ok'], N(b))} prose {w(p['ok'], N(p))}")
print("- by task")
for m in RANK:
    print(f"{LABEL[m]:22s}", " | ".join(f"{t} {w((c:=counts(g))['ok'], c['ans']+c['unf'])} decl {c['abst']}/{c['n']}"
                                       for t in ["reference", "continuation", "topic"] for g in [real[(real.model == m) & (real.task == t)]]))
allq = ok.sum(axis=1)
print("questions all 9 models got right:", int((allq == 9).sum()), "| none right:", int((allq == 0).sum()), "|",
      pd.Series([f"{questions[q]['task']}/{questions[q]['text_id']}" for q in allq[allq == 0].index]).value_counts().to_dict())

head("4 Famous vs random (reference + continuation)")
for m in RANK:
    g = real[(real.model == m) & real.fame.notna()]
    f, r = counts(g[g.fame == "famous"]), counts(g[g.fame == "random"])
    print(f"{LABEL[m]:22s} famous {w(f['ok'], f['ans']+f['unf'])} random {w(r['ok'], r['ans']+r['unf'])} | "
          f"declined {f['abst']}/{f['n']} vs {r['abst']}/{r['n']} | of all: {w(f['ok'], N(f))} vs {w(r['ok'], N(r))}")
    overlap = wilson(f['ok'], f['ans']+f['unf'])[1] <= wilson(r['ok'], r['ans']+r['unf'])[2]
    print("   intervals overlap (answered):", overlap, "| by text (famous/random of all):",
          {t[:6]: f"{counts(x[x.fame=='famous'])['ok']}/{len(x[x.fame=='famous'])} vs {counts(x[x.fame=='random'])['ok']}/{len(x[x.fame=='random'])}"
           for t in TEXTS for x in [g[g.text_id == t]]})

head("5 Topic task: quote really in the source, and location")
for m in RANK:
    g = real[(real.model == m) & (real.task == "topic")]
    c = counts(g)
    loc = summary["per_model"][m]["baseline"]["location_error"]
    short = int((g.ok & g.fl.str.contains("SHORT_QUOTE")).sum())
    print(f"{LABEL[m]:22s} correct {w(c['ok'], c['ans']+c['unf'])} declined {c['abst']}/150 | verbatim but wrong location "
          f"{int(((g.label == 'WRONG_PLACE')).sum())} | location_error {w(loc['k'], loc['n'])} | correct quotes under 6 words {short}")

head("6 Trap questions by type")
tr = base[base["should_abstain"]]
T = tr[tr.label.isin(["CORRECT_REFUSAL", "TRAP_FABRICATED"])]
tf = T[T.label == "TRAP_FABRICATED"].copy()
tf["other"] = tf.fl.str.contains("SOURCE_CORRECTED")  # says itself that it is not from the named text
for m in RANK:
    g, f = T[T.model == m], tf[tf.model == m]
    k = lambda t: f"{int((f.trap_type == t).sum())}/{int((g.trap_type == t).sum())}"  # noqa: E731
    print(f"{LABEL[m]:22s} all {w(len(f), len(g))} | nonexistent {k('nonexistent_reference')} {w((f.trap_type=='nonexistent_reference').sum(), (g.trap_type=='nonexistent_reference').sum())}"
          f" misattribution {k('misattribution')} absent_topic {k('absent_topic')} | corrected the source {int(f.other.sum())} | "
          f"presented {w(len(f)-f.other.sum(), len(g))} | quote text exists in the named text (EXACT) {int((f.quote_label=='EXACT').sum())}")
print("total failures", len(tf), "| corrected the source", int(tf.other.sum()), "| misattribution", int((tf.trap_type == 'misattribution').sum()),
      "| EXACT in source", int((tf.quote_label == 'EXACT').sum()), "| presented as genuine", int((~tf.other).sum()))
print("t4-origin-0001 (Chapter XV of a 14-chapter book): failures", sorted(tf[tf.question_id == "t4-origin-0001"].model_label), "EXACT:", int((tf[tf.question_id == "t4-origin-0001"].quote_label == "EXACT").sum()))
for m in RANK:
    b = summary["per_model"][m]["baseline"]
    f = tf[tf.model == m]
    assert (b["trap_failure"]["k"], b["trap_presented"]["k"]) == (len(f), int((~f.other).sum())), m
print("unreadable trap answers:", tr[tr.label == "UNPARSEABLE"].model_label.tolist())
print("trap_failure in summary:", {LABEL[m]: summary['per_model'][m]['baseline']['trap_failure']['k'] for m in RANK})

head("7 Conditions on the shared Bible + Constitution subset (310 questions: 260 real, 50 traps)")
lk = df[df.condition == "lookup"]
ids = set(lk.question_id)
print("subset by task:", {t: sum(questions[q]["task"] == t for q in ids) for t in ["reference", "topic", "trap"]})
for m in RANK:
    g = df[(df.model == m) & (df.repeat == 0) & df.question_id.isin(ids)]
    out = []
    for cond in ["baseline", "cautious"]:
        x = g[(g.condition == cond) & ~g.should_abstain]
        c = counts(x)
        tt = g[(g.condition == cond) & g.should_abstain]
        out.append(f"{cond}: correct {w(c['ok'], c['ans']+c['unf'])} of260 {c['ok']} wrong {c['wrong']} decl {c['abst']} unf {c['unf']} traps {int((tt.label=='TRAP_FABRICATED').sum())}")
    x = g[(g.condition == "lookup") & ~g.should_abstain]
    tt = g[(g.condition == "lookup") & g.should_abstain]
    ref, top = x[x.task == "reference"], x[x.task == "topic"]
    out.append(f"lookup: ref right {int((ref.label=='EXACT').sum())}/200 decl {int((ref.label=='ABSTAINED').sum())}; topic existing ref {int((top.label=='EXACT').sum())}/60 "
               f"nonexistent {int((top.label=='FABRICATED').sum())} decl {int((top.label=='ABSTAINED').sum())} unread {int((top.label=='UNPARSEABLE').sum())}; traps {int((tt.label=='TRAP_FABRICATED').sum())}/50")
    print(f"{LABEL[m]:22s}", " | ".join(out))
lr = lk[~lk.should_abstain]
print("lookup totals: wrong place", int((lr.label == "WRONG_PLACE").sum()), "nonexistent", int((lr.label == "FABRICATED").sum()),
      "declined", int((lr.label == "ABSTAINED").sum()), "of", len(lr), "| reference task right", int(((lr.task == 'reference') & (lr.label == 'EXACT')).sum()), "of", int((lr.task == 'reference').sum()))
print("plain totals on the same 260 x 9:", counts(real[real.question_id.isin(ids)]))
for cond in ["baseline", "cautious", "lookup"]:
    x = df[(df.condition == cond) & (df.repeat == 0) & df.question_id.isin(ids) & df.should_abstain]
    print(f"{cond} trap failures on the 50 subset traps, all models:", int((x.label == "TRAP_FABRICATED").sum()), "of", len(x))
lt = lk[lk.should_abstain & (lk.label == "TRAP_FABRICATED")]
print("lookup trap failures:", [(r.model_label, r.question_id, r.fl) for r in lt.itertuples()])
print("lookup nonexistent refs:", [(r.model_label, r.question_id, parse_response(r.content).location) for r in lr[lr.label == "FABRICATED"].itertuples()])
print("- cautious vs plain, all 600 real-answer questions and 100 traps")
for m in RANK:
    c0 = C[m]
    x = df[(df.model == m) & (df.repeat == 0) & (df.condition == "cautious")]
    c1 = counts(x[~x.should_abstain])
    xr = x[~x.should_abstain].set_index("question_id")
    br = real[real.model == m].set_index("question_id").loc[xr.index]
    wr0, wr1 = br.label.isin(ANSWERED) & ~br.ok, xr.label.isin(ANSWERED) & ~xr.ok
    mw, mc = mcnemar(wr0, wr1), mcnemar(br.ok, xr.ok)
    t1, t0 = int((x.label == "TRAP_FABRICATED").sum()), int((tr[tr.model == m].label == "TRAP_FABRICATED").sum())
    print(f"{LABEL[m]:22s} correct {c0['ok']}->{c1['ok']} wrong {c0['wrong']}->{c1['wrong']} declined {c0['abst']}->{c1['abst']} unf {c0['unf']}->{c1['unf']} "
          f"made up {c0['fab']}->{c1['fab']} strict {100*strict(c0):.1f}->{w(c1['ok'], c1['ans']+c1['unf'])} traps {t0}->{t1} | McNemar wrong p={pv(mw[2])}, correct p={pv(mc[2])}")

head("8 Stability: 70 questions x 4 runs (plain prompt); same label in all four")
for m in RANK:
    g = df[(df.model == m) & (df.condition == "baseline")]
    g = g[g.question_id.isin(g[g.repeat == 1].question_id)]
    per = g.groupby("question_id")
    same = int((per.label.nunique() == 1).sum())
    okk = g[~g.should_abstain].groupby("question_id").ok
    mixed = int((okk.nunique() > 1).sum())
    st = summary["per_model"][m]["stability"]
    g2 = g.assign(q=[parse_response(x).quote for x in g.content])
    word = int((g2.groupby("question_id").q.nunique() == 1).sum())
    print(f"{LABEL[m]:22s} {w(same, 70)} summary k={st['k']} | real-answer questions right in some runs and not others {mixed}/{okk.ngroups} | identical quote string {word}/70")

head("9 Generations")
for a, b in [("Claude Haiku 5.5", "Claude Haiku 4.5"), ("Claude Sonnet 5.5", "Claude Sonnet 4.6")]:
    show_pair(S[a], S[b])

head("10 Settings and cost (cost includes replaced answers)")
for m in summary["models"]:
    d = df[df.model == m["id"]]
    print(f"{m['label']:22s} total ${m['cost_usd']:.2f} final answers ${d.cost.sum():.2f} = {1000*d.cost.sum()/len(d):.2f} USD per 1,000 calls | "
          f"mean output tokens {m['mean_output_tokens']:.0f} | dates {m['run_dates']} | hosts {m['hosts']}")
print("total", round(sum(m["cost_usd"] for m in summary["models"]), 2))
print("JSON not strict (code fence etc.), share of plain answers:", {LABEL[m]: int((base[base.model == m].parse_method == 'extracted').sum()) for m in RANK})

raw = {m: [json.loads(x) for x in Path("results/raw", m.replace("/", "__") + ".jsonl").read_text().splitlines()] for m in RANK}
for m, rows in raw.items():
    req = [r["request"] if isinstance(r["request"], dict) else json.loads(r["request"]) for r in rows]
    if not any(q.get("api") == "anthropic" for q in req):
        print(f"{LABEL[m]:22s} calls without a pinned host: {sum('provider' not in q for q in req)} | hosts {pd.Series([r['provider'] for r in rows]).value_counts().to_dict()}")

head("11 Re-asked cut-off answers (D16), plain prompt, repeat 0, real-answer questions")
tot = 0
for p in sorted(Path("results/archive/cut_off_at_lower_limit").glob("*.jsonl")):
    rows = [json.loads(x) for x in p.read_text().splitlines()]
    tot += len(rows)
    keys = {r["question_id"] for r in rows if r["condition"] == "baseline" and r["repeat"] == 0 and not questions[r["question_id"]]["should_abstain"]}
    m = rows[0]["model"]
    g = real[(real.model == m) & real.question_id.isin(keys)]
    c = counts(g)
    rest = counts(real[(real.model == m) & ~real.question_id.isin(keys)])
    print(f"{LABEL[m]:22s} all conditions {len(rows)} | plain real {len(keys)}: now correct {c['ok']} wrong {c['wrong']} declined {c['abst']} unfinished {c['unf']} | "
          f"other questions strict {w(rest['ok'], rest['ans']+rest['unf'])}")
print("total re-asked:", tot)
print("UNPARSEABLE now:", df[df.label == 'UNPARSEABLE'].groupby(['model_label', 'condition', 'finish_reason']).size().to_dict())

head("12 Examples in the Limitations section")
for q in ["t2-pride-0001", "t2-origin-0003", "t2-pride-0011", "t2-shakespeare-0040", "t2-shakespeare-0003", "t3-constitution-0013"]:
    g = real[(real.question_id == q) & real.label.isin(ANSWERED)]
    top = pd.Series([normalize(parse_response(x).quote) for x in g[~g.ok].content]).value_counts()
    print(f"{q}: answered {len(g)} correct {int(g.ok.sum())} | commonest wrong answer ({int(top.iloc[0]) if len(top) else 0} models): {top.index[0][-110:] if len(top) else '-'} | source: {normalize(questions[q].get('ground_truth') or '')[-110:]}")
words = pd.Series({q: len(normalize(v["ground_truth"]).split()) for q, v in questions.items() if v["task"] == "continuation"})
wt = pd.Series({q: questions[q]["text_id"] for q in words.index})
print("median words of the continuation answers by text:", words.groupby(wt).median().to_dict())
la = lr[lr.label.isin(ANSWERED)]
print("lookup answered (readable reference):", len(la), "valid and as requested:", int((la.label == "EXACT").sum()))

head("13 Markdown tables pasted into PAPER.md")


def ci(k, n):
    p, lo, hi = wilson(k, n)
    return f"{100*p:.1f}% ({100*lo:.1f}–{100*hi:.1f})"


print("| Model | Correct, strict | Strict rank | Correct of all | Rank of all | Wrong quotation | Declined | Unfinished |\n|---|---|---|---|---|---|---|---|")
for m in RANK600:
    c = C[m]
    print(f"| {LABEL[m]} | {ci(c['ok'], c['ans']+c['unf'])}, n = {c['ans']+c['unf']} | {RANK.index(m)+1} | {100*c['ok']/N(c):.1f}%, {c['ok']}/{N(c)} | {RANK600.index(m)+1} | "
          f"{c['wrong']} ({100*c['wrong']/N(c):.1f}%) | {c['abst']} ({100*c['abst']/N(c):.1f}%) | {c['unf']} |")
print("\n| Strict ranks | Pair | (a) All questions: only first / only second correct | p | (b) Neither declined: n, correct first / second | p |\n|---|---|---|---|---|---|")
extra = [("Claude Haiku 5.5", "Claude Haiku 4.5"), ("Claude Opus 5.5", "Claude Sonnet 5.5"), ("Claude Sonnet 5.5", "DeepSeek V4 Pro"), ("DeepSeek V4 Pro", "GPT-6 Luna"), ("Claude Sonnet 4.6", "Gemini 3.1 Flash Lite")]
for a, b in list(zip(RANK, RANK[1:])) + [(S[x], S[y]) for x, y in extra]:
    sw = (a, b) not in R
    r = R[(b, a) if sw else (a, b)]
    h = H[(b, a) if sw else (a, b)]
    x = (r[1], r[0], r[8], r[7]) if sw else (r[0], r[1], r[7], r[8])
    q = lambda v: "<0.001" if v < 0.001 else f"{v:.3f}"  # noqa: E731
    print(f"| {RANK.index(a)+1}–{RANK.index(b)+1} | {LABEL[a]} vs {LABEL[b]} | {x[0]} / {x[1]} | {q(h[0])} | {r[3]}: {x[2]} / {x[3]} | {q(h[1])} |")
print("\n| Model | Nonexistent reference | Misattribution | Absent topic | All | Corrected the source | Presented as genuine |\n|---|---|---|---|---|---|---|")
for m in RANK:
    g, f = T[T.model == m], tf[tf.model == m]
    k = lambda t: f"{int((f.trap_type == t).sum())}/{int((g.trap_type == t).sum())}"  # noqa: E731
    print(f"| {LABEL[m]} | {k('nonexistent_reference')} | {k('misattribution')} | {k('absent_topic')} | {len(f)}/{len(g)}, {ci(len(f), len(g))} | {int(f.other.sum())} | {len(f)-int(f.other.sum())}/{len(g)}, {ci(len(f)-int(f.other.sum()), len(g))} |")
head("14 Scorer fixes: before (git " + BEFORE + ") and after")
try:
    blob = subprocess.run(["git", "show", f"{BEFORE}:results/scored.parquet"], capture_output=True, check=True).stdout
except (OSError, subprocess.CalledProcessError):
    sys.exit(f"skipped: commit {BEFORE} is not available here (all other sections are above)")
old = pd.read_parquet(io.BytesIO(blob))
old["ok"] = (old["label"] == "EXACT") & ~old["flags"].fillna("").str.contains("PARTIAL")
key = ["model", "question_id", "condition", "repeat"]
j = df.merge(old[key + ["label", "ok", "location_correct"]], on=key, how="outer", suffixes=("", "_old"), indicator=True)
print("rows only in one file:", int((j["_merge"] != "both").sum()), "| labels changed, all conditions and repeats:", int((j.label != j.label_old).sum()))
ob = old[(old.condition == "baseline") & (old.repeat == 0) & ~old.should_abstain]
for m in RANK:
    c0, c1 = counts(ob[ob.model == m]), C[m]
    ch = j[(j.model == m) & (j.label != j.label_old)]
    pl = ch[(ch.condition == "baseline") & (ch.repeat == 0)]
    print(f"{LABEL[m]:22s} correct {c0['ok']} -> {c1['ok']} of 600 | strict {w(c0['ok'], c0['ans']+c0['unf'])} -> {w(c1['ok'], c1['ans']+c1['unf'])} | "
          f"changed labels: plain {len(pl)}, all {len(ch)}:", [f"{r.question_id} {r.label_old}->{r.label}" for r in pl.itertuples()])
ro = sorted(C, key=lambda m: -(lambda c: c["ok"] / (c["ans"] + c["unf"]))(counts(ob[ob.model == m])))
print("strict ranking before:", " > ".join(LABEL[m] for m in ro), "| same order:", ro == RANK)

print("\n| Model | Correct before | Correct after | Gain | Strict before | Strict after | Strict rank |\n|---|---|---|---|---|---|---|")
for m in RANK:
    c0, c1 = counts(ob[ob.model == m]), C[m]
    print(f"| {LABEL[m]} | {c0['ok']} | {c1['ok']} | +{c1['ok']-c0['ok']} | {100*c0['ok']/(c0['ans']+c0['unf']):.1f}% | {100*strict(c1):.1f}% | {ro.index(m)+1} → {RANK.index(m)+1} |")
