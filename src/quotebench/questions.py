"""Build the test set (SPEC §4–5) and render prompts (SPEC §7).

Inputs: parsed sources, the hand-written CSVs in data/handwritten/ (famous passages, topic
themes, traps) and config/prompts.yaml. Output: data/questions.jsonl (one question per line),
data/questions.meta.json (version, seed, counts, repeat sample, source checksums) and
data/questions_preview.csv (every question with its rendered baseline prompt, for review).

Generation is deterministic: random choices use ``random.Random(SEED)`` and never depend on
dict or set ordering.
"""

from __future__ import annotations

import collections
import csv
import functools
import hashlib
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import locations as L
from .scoring import load_index, normalize, score_free, tokenize
from .sources import PARSED_DIR, ROOT, load_units

VERSION = "v1.0"
SEED = 20261011
TEXTS = ["bible_kjv", "shakespeare", "us_constitution", "pride_prejudice", "origin_species"]
DATA_DIR = ROOT / "data"
HANDWRITTEN = DATA_DIR / "handwritten"
QUESTIONS_PATH = DATA_DIR / "questions.jsonl"
META_PATH = DATA_DIR / "questions.meta.json"
PREVIEW_PATH = DATA_DIR / "questions_preview.csv"
PROMPTS_PATH = ROOT / "config" / "prompts.yaml"

# How many questions of each kind (English-only v1; see DECISIONS D5, D7).
REFERENCE_COUNTS = {"bible_kjv": 150, "us_constitution": 50}  # incl. the famous ones
CONTINUATION_PER_TEXT = 50
REPEAT_FRACTION = 0.10

# Task rules (SPEC §4)
GIVEN_MIN_WORDS = 8
ANSWER_MIN_WORDS, ANSWER_MAX_WORDS = 6, 60
REFERENCE_MIN_WORDS = 6  # random Task 1 passages; shorter ones make one wrong word = FABRICATED
CONSTITUTION_MAX_WORDS = 150  # keeps answers well inside the 400-token output limit
# Misattribution traps: rejected if the saying matches the source at ALTERED level or better
# (the scorer's lower threshold, SPEC §4); flagged for a hand check from TRAP_NEAR_MISS up.
TRAP_NEAR_MISS = 0.50

# Lookup only where a reference resolves to a quotable unit (verse / clause); see DECISIONS D7.
LOOKUP_TEXTS = {"bible_kjv", "us_constitution"}

# Units of the same "run" for continuation pairs: the next unit must share these fields.
SAME_RUN = {
    "bible_kjv": ("book", "chapter"),
    "shakespeare": ("play", "act", "scene", "speaker"),
    "us_constitution": ("part",),
    "pride_prejudice": ("chapter",),
    "origin_species": ("chapter",),
}
# Darwin's run-in section headings ("Organs of extreme perfection.—To suppose ...")
RUN_IN_HEADING = re.compile(r"^[A-Z][^.!?]{2,90}\.—")

STRUCT_FIELDS = ("book", "book_code", "chapter", "verse", "play", "act", "scene", "line", "part",
                 "article", "amendment", "section", "clause", "sentence")

ROMAN_NUMERALS = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII",
                  "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI", "XXII", "XXIII", "XXIV",
                  "XXV", "XXVI", "XXVII"]


# --------------------------------------------------------------------------------------
# Helpers


def words(text: str) -> int:
    return len(normalize(text).split())


def read_csv(name: str) -> list[dict]:
    with (HANDWRITTEN / name).open(encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r["text_id"] and not r["text_id"].startswith("#")]


def location_of(unit: dict) -> dict:
    return {k: unit[k] for k in STRUCT_FIELDS if unit.get(k) is not None}


def constitution_citation(unit: dict, units: list[dict]) -> str | None:
    """Standard citation for a clause, or None if it has no conventional one."""
    if unit["part"] == "preamble":
        return "the Preamble"
    key = "article" if unit["part"] == "article" else "amendment"
    siblings = [u for u in units if u["part"] == unit["part"] and u[key] == unit[key] and u["section"] == unit["section"]]
    head = f"{key.title()} {ROMAN_NUMERALS[unit[key]]}"
    if unit["section"] is not None:
        head += f", Section {unit['section']}"
    if len(siblings) == 1:
        return head
    if key == "amendment":
        return None  # "Amendment XXV, Section 4, Clause 2" is not a conventional citation
    return f"{head}, Clause {unit['clause']}"


def bible_citation(unit: dict) -> str:
    return f"{unit['book']} {unit['chapter']}:{unit['verse']}"


@dataclass
class Text:
    id: str
    units: list[dict]
    norm_counts: collections.Counter

    @classmethod
    def load(cls, text_id: str) -> "Text":
        units = load_units(text_id)
        return cls(text_id, units, collections.Counter(normalize(u["text"]) for u in units))

    def unique(self, unit: dict) -> bool:
        return self.norm_counts[normalize(unit["text"])] == 1

    def next_in_run(self, unit: dict) -> dict | None:
        i = unit["idx"] + 1
        if i >= len(self.units):
            return None
        nxt = self.units[i]
        if self.id == "us_constitution":
            # The Preamble runs straight into Article I; the amendments are a separate run.
            body = lambda u: u["part"] in ("preamble", "article")
            return nxt if body(unit) == body(nxt) else None
        return nxt if all(unit.get(k) == nxt.get(k) for k in SAME_RUN[self.id]) else None

    def find_passage(self, passage: str, play: str | None = None) -> dict:
        """Resolve a famous-list entry: a reference (Bible / Constitution) or opening words."""
        if self.id == "bible_kjv":
            loc = L.parse_bible(passage)
            hits = L.resolve(self.id, loc, self.units) if loc and "verse_start" in loc else []
        elif self.id == "us_constitution":
            loc = L.parse_constitution(passage)
            hits = L.resolve(self.id, loc, self.units) if loc else []
        else:
            target = normalize(passage)
            pool = [u for u in self.units if play is None or u.get("play") == play]
            hits = [u["idx"] for u in pool if normalize(u["text"]).startswith(target)]
            if not hits:
                hits = [u["idx"] for u in pool if target in normalize(u["text"])]
        if len(hits) != 1:
            raise ValueError(f"{self.id}: famous passage {passage!r} matched {len(hits)} units")
        return self.units[hits[0]]


# --------------------------------------------------------------------------------------
# Question builders


def _q(**kw) -> dict:
    base = {
        "id": None, "version": VERSION, "task": None, "text_id": None, "language": "en",
        "fame": None, "parallel_id": None, "play": None, "prompt_vars": {}, "ground_truth": None,
        "target_units": [], "location": None, "should_abstain": False, "trap_type": None,
        "conditions": ["baseline", "cautious"], "note": "",
    }
    base.update(kw)
    if base["text_id"] in LOOKUP_TEXTS and base["task"] in ("reference", "topic", "trap"):
        base["conditions"] = ["baseline", "cautious", "lookup"]
    return base


def build_reference(texts: dict[str, Text], famous: list[dict], rng: random.Random, problems: list[str]) -> list[dict]:
    out = []
    for text_id, total in REFERENCE_COUNTS.items():
        t = texts[text_id]
        chosen: list[tuple[dict, str]] = []
        for row in [r for r in famous if r["text_id"] == text_id and r["task"] == "reference"]:
            try:
                chosen.append((t.find_passage(row["passage"]), "famous"))
            except ValueError as e:
                problems.append(str(e))
        taken = {u["idx"] for u, _ in chosen}

        def citation(u):
            return bible_citation(u) if text_id == "bible_kjv" else constitution_citation(u, t.units)

        max_words = 60 if text_id == "bible_kjv" else CONSTITUTION_MAX_WORDS
        pool = [u for u in t.units if u["idx"] not in taken and t.unique(u)
                and REFERENCE_MIN_WORDS <= words(u["text"]) <= max_words and citation(u)]
        n_random = total - len(chosen)
        chosen += [(u, "random") for u in rng.sample(pool, n_random)]
        for u, fame in chosen:
            ref = citation(u)
            out.append(_q(task="reference", text_id=text_id, fame=fame, prompt_vars={"reference": ref},
                          ground_truth=u["text"], target_units=[u["idx"]], location=location_of(u),
                          parallel_id=None))
    return out


def build_continuation(texts: dict[str, Text], famous: list[dict], rng: random.Random, problems: list[str]) -> list[dict]:
    out = []

    def eligible(t: Text, given: dict) -> dict | None:
        nxt = t.next_in_run(given)
        if nxt is None or not t.unique(given) or words(given["text"]) < GIVEN_MIN_WORDS:
            return None
        if not ANSWER_MIN_WORDS <= words(nxt["text"]) <= ANSWER_MAX_WORDS:
            return None
        if RUN_IN_HEADING.match(given["text"]) or RUN_IN_HEADING.match(nxt["text"]):
            return None
        return nxt

    for text_id in TEXTS:
        t = texts[text_id]
        chosen: list[tuple[dict, dict, str]] = []
        for row in [r for r in famous if r["text_id"] == text_id and r["task"] == "continuation"]:
            try:
                given = t.find_passage(row["passage"], row.get("play") or None)
            except ValueError as e:
                problems.append(str(e))
                continue
            nxt = eligible(t, given)
            if nxt is None:
                problems.append(f"{text_id}: famous continuation {row['passage']!r} breaks the Task 2 rules")
                continue
            chosen.append((given, nxt, "famous"))
        used = {u["idx"] for g, n, _ in chosen for u in (g, n)}
        pool = []
        for given in t.units:
            nxt = eligible(t, given)
            if nxt is not None and given["idx"] not in used and nxt["idx"] not in used:
                pool.append((given, nxt))
        chosen += [(g, n, "random") for g, n in rng.sample(pool, CONTINUATION_PER_TEXT - len(chosen))]
        for given, nxt, fame in chosen:
            unit = "sentence" if given.get("form") == "prose" else None
            out.append(_q(task="continuation", text_id=text_id, fame=fame, play=given.get("play"),
                          prompt_vars={"given": given["text"], **({"unit": unit} if unit else {})},
                          ground_truth=nxt["text"], target_units=[nxt["idx"]], location=location_of(nxt),
                          note=f"given_unit={given['idx']}"))
    return out


def build_topic(themes: list[dict]) -> list[dict]:
    out = []
    for row in themes:
        out.append(_q(task="topic", text_id=row["text_id"], play=row.get("play") or None,
                      prompt_vars={"theme": row["theme"]}))
    return out


def build_traps(texts: dict[str, Text], traps: list[dict], problems: list[str]) -> tuple[list[dict], list[dict]]:
    """Trap questions plus a verification report (one row per trap)."""
    out, report = [], []
    for row in traps:
        text_id, play, kind, content = row["text_id"], row.get("play") or None, row["trap_type"], row["content"]
        t = texts[text_id]
        verdict, detail = "ok", ""
        if kind == "nonexistent_reference":
            if text_id == "bible_kjv":
                loc = L.parse_bible(content)
            elif text_id == "shakespeare":
                loc = L.parse_play(content)
            elif text_id == "us_constitution":
                loc = L.parse_constitution(content)
            else:
                loc = L.parse_chapter(content, text_id)
            if loc is None:
                verdict, detail = "check by hand", "reference not machine-readable (e.g. unknown book or section name)"
            else:
                hits = L.resolve(text_id, loc, t.units, play)
                if hits:
                    verdict, detail = "REJECTED", f"reference exists: {t.units[hits[0]]['text'][:80]!r}"
            vars_ = {"reference": content}
        elif kind == "misattribution":
            index, units, speakers = load_index(text_id)
            q = [x.norm for x in tokenize(content)]
            if play:
                sub = [u for u in units if u["play"] == play]
                from .scoring import SourceIndex
                index = SourceIndex([u["text"] for u in sub], index.cfg)
            m = score_free(q, index).match
            sim = m.similarity if m else 0.0
            detail = f"closest: {sim:.2f} {m.text[:70]!r}" if m else "no shared words"
            if sim >= index.cfg.lower:
                verdict = "REJECTED"
            elif sim >= TRAP_NEAR_MISS:
                verdict, detail = "check by hand", f"near miss — {detail}"
            vars_ = {"content": content}
        elif kind == "absent_topic":
            verdict, detail = "check by hand", "absence of a topic cannot be verified automatically"
            vars_ = {"theme": content}
        else:
            raise ValueError(f"unknown trap_type {kind!r}")
        if verdict == "check by hand" and row.get("hand_checked", "").startswith("yes"):
            verdict, detail = "ok (hand-checked)", f"{detail} | {row['hand_checked']}"
        report.append({"text_id": text_id, "play": play or "", "trap_type": kind, "content": content,
                       "verdict": verdict, "detail": detail})
        if verdict == "REJECTED":
            problems.append(f"trap rejected ({text_id}): {content!r} — {detail}")
            continue
        out.append(_q(task="trap", text_id=text_id, play=play, prompt_vars=vars_, should_abstain=True,
                      trap_type=kind, note=row.get("note", "")))
    return out, report


# --------------------------------------------------------------------------------------
# Prompts


_VAR = re.compile(r"\{(\w+)\}")


def _fill(template: str, values: dict) -> str:
    """Substitute {name} for known names only, so literal JSON braces are left alone."""
    def rep(m):
        return str(values[m.group(1)]) if m.group(1) in values else m.group(0)
    for _ in range(3):  # values may themselves contain {play}
        template = _VAR.sub(rep, template)
    return " ".join(template.split())


@functools.lru_cache(maxsize=1)
def _load_prompts_cached(mtime: float) -> dict:
    return yaml.safe_load(PROMPTS_PATH.read_text(encoding="utf-8"))


def load_prompts() -> dict:
    return _load_prompts_cached(PROMPTS_PATH.stat().st_mtime)


def render_prompt(q: dict, condition: str, prompts: dict | None = None) -> str:
    prompts = prompts or load_prompts()
    tpl = prompts[q["language"]]
    text = dict(prompts["texts"][q["text_id"]])
    values = {**text, "play": q.get("play") or "", **q["prompt_vars"]}
    values["json"] = tpl["json"]
    task = q["task"]
    if task == "trap":
        if q["trap_type"] == "misattribution":
            unit = text.get("misattribution_unit", text["unit"])
            values["reference"] = _fill(tpl["misattribution_reference"], {**values, "unit": unit})
        task = "topic" if q["trap_type"] == "absent_topic" else "reference"
    if condition == "lookup":
        req_tpl = tpl["lookup_request_topic"] if task == "topic" else tpl["lookup_request_reference"]
        values["request"] = _fill(req_tpl, values)
        return _fill(tpl["lookup"], values)
    prompt = _fill(tpl[task], values)
    if condition == "cautious":
        prompt += " " + _fill(tpl["cautious_suffix"], values)
    elif condition != "baseline":
        raise ValueError(f"unknown condition {condition!r}")
    return prompt


# --------------------------------------------------------------------------------------
# Build


def build() -> dict:
    rng = random.Random(SEED)
    texts = {t: Text.load(t) for t in TEXTS}
    famous, themes, traps = read_csv("famous.csv"), read_csv("themes.csv"), read_csv("traps.csv")
    problems: list[str] = []

    questions = build_reference(texts, famous, rng, problems)
    questions += build_continuation(texts, famous, rng, problems)
    questions += build_topic(themes)
    trap_qs, trap_report = build_traps(texts, traps, problems)
    questions += trap_qs

    prefix = {"reference": "t1", "continuation": "t2", "topic": "t3", "trap": "t4"}
    short = {"bible_kjv": "kjv", "shakespeare": "shakespeare", "us_constitution": "constitution",
             "pride_prejudice": "pride", "origin_species": "origin"}
    counters: collections.Counter = collections.Counter()
    for q in questions:
        key = (q["task"], q["text_id"])
        counters[key] += 1
        q["id"] = f"{prefix[q['task']]}-{short[q['text_id']]}-{counters[key]:04d}"

    ids = [q["id"] for q in questions]
    assert len(ids) == len(set(ids))
    repeat = sorted(rng.sample(ids, round(REPEAT_FRACTION * len(ids))))

    prompts = load_prompts()
    QUESTIONS_PATH.write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in questions), encoding="utf-8")
    with PREVIEW_PATH.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "task", "text_id", "fame", "trap_type", "conditions", "baseline_prompt", "ground_truth"])
        for q in questions:
            w.writerow([q["id"], q["task"], q["text_id"], q["fame"] or "", q["trap_type"] or "",
                        " ".join(q["conditions"]), render_prompt(q, "baseline", prompts), q["ground_truth"] or ""])
    with (DATA_DIR / "trap_verification.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(trap_report[0]))
        w.writeheader()
        w.writerows(trap_report)

    counts = collections.Counter((q["task"], q["text_id"], q["fame"] or q["trap_type"] or "-") for q in questions)
    meta = {
        "version": VERSION,
        "seed": SEED,
        "n_questions": len(questions),
        "counts": {f"{t}/{x}/{f}": n for (t, x, f), n in sorted(counts.items())},
        "repeat_sample": repeat,
        "repeat_runs": 3,
        "rules": {
            "given_min_words": GIVEN_MIN_WORDS, "answer_words": [ANSWER_MIN_WORDS, ANSWER_MAX_WORDS],
            "reference_min_words": REFERENCE_MIN_WORDS, "constitution_max_words": CONSTITUTION_MAX_WORDS,
            "trap_near_miss": TRAP_NEAR_MISS, "lookup_texts": sorted(LOOKUP_TEXTS),
        },
        "sources_sha256": {
            t: hashlib.sha256((PARSED_DIR / f"{t}.jsonl").read_bytes()).hexdigest() for t in TEXTS
        },
        "handwritten_sha256": {
            f: hashlib.sha256((HANDWRITTEN / f).read_bytes()).hexdigest()
            for f in ("famous.csv", "themes.csv", "traps.csv")
        },
    }
    META_PATH.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return {"questions": questions, "problems": problems, "meta": meta, "trap_report": trap_report}


def load_questions() -> list[dict]:
    with QUESTIONS_PATH.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]
