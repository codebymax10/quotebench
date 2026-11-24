"""Normalisation, matching and labelling of quotations.

This module is source-agnostic: it knows nothing about Bibles or plays. The benchmark wraps it
with question-specific logic (``score_answer``), and ``quotecheck`` reuses it unchanged.

Pipeline for one quote:

1. ``clean_quote`` strips things a model adds around a quote (verse numbers, "John 3:16",
   speaker names given by the caller).
2. ``tokenize`` turns text into normalised word tokens (SPEC §8): Unicode NFKC, case-folded,
   ё→е, apostrophes and in-word hyphens removed ("to-morrow" = "tomorrow", "’tis" = "tis"),
   dashes, quotes and all other punctuation treated as spaces, digits dropped.
3. ``align`` computes a token-level edit distance. A changed, added or dropped word costs 1;
   a *spelling variant* (honour/honor, shew/show) costs less (config ``variants.cost``).
   Similarity = 1 − cost / max(len(quote), len(matched span)).
4. ``SourceIndex.search`` finds the best-matching span anywhere in a source using an n-gram
   index to pick candidate positions, then aligns the quote against each candidate.
5. ``label`` maps similarity to EXACT / MINOR / ALTERED / FABRICATED with two thresholds.

A quote is verbatim when its letters, run together, are the letters of the text run together
(D15: letter for letter, whitespace and hyphens ignored), so "any thing" quotes "anything". The
passage must still start and end at a word boundary (``letter_spans``). Where only the division
into words differs, the answer carries the flag WORD_DIVISION.
"""

from __future__ import annotations

import json
import re
import unicodedata
from array import array
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import yaml
from rapidfuzz.distance import Indel

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "scoring.yaml"

EXACT, MINOR, ALTERED, FABRICATED = "EXACT", "MINOR", "ALTERED", "FABRICATED"
WRONG_PLACE, ABSTAINED = "WRONG_PLACE", "ABSTAINED"
CORRECT_REFUSAL, TRAP_FABRICATED = "CORRECT_REFUSAL", "TRAP_FABRICATED"
UNPARSEABLE, ERROR = "UNPARSEABLE", "ERROR"


# --------------------------------------------------------------------------------------
# Configuration


@dataclass(frozen=True)
class ScoringConfig:
    upper: float = 0.97
    lower: float = 0.80
    minor_rule: str = "variants_only"  # or "similarity" (SPEC §8 literal: sim >= upper)
    partial_min_words: int = 6
    fragment_min_words: int = 4
    variant_char_similarity: float = 0.80
    variant_min_length: int = 4
    variant_cost: float = 0.25
    variant_pairs: frozenset[tuple[str, str]] = frozenset()
    ngram: int = 2
    max_postings: int = 4000
    candidates: int = 8
    window_slack: int = 12

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "ScoringConfig":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        pairs = set()
        for a, b in raw["variants"].get("pairs", []):
            a, b = norm_token(a), norm_token(b)
            pairs |= {(a, b), (b, a)}
        return cls(
            upper=raw["thresholds"]["upper"],
            lower=raw["thresholds"]["lower"],
            minor_rule=raw["thresholds"].get("minor_rule", "variants_only"),
            partial_min_words=raw["partial_min_words"],
            fragment_min_words=raw.get("fragment_min_words", cls.fragment_min_words),
            variant_char_similarity=raw["variants"]["char_similarity"],
            variant_min_length=raw["variants"]["min_length"],
            variant_cost=raw["variants"]["cost"],
            variant_pairs=frozenset(pairs),
            ngram=raw["search"]["ngram"],
            max_postings=raw["search"]["max_postings"],
            candidates=raw["search"]["candidates"],
            window_slack=raw["search"]["window_slack"],
        )


# --------------------------------------------------------------------------------------
# Normalisation


@dataclass(frozen=True)
class Token:
    norm: str
    start: int  # character offsets in the original text
    end: int


# A word: letters/digits (plus combining marks), optionally joined by apostrophes or hyphens.
_WORD = re.compile(r"[\ẁ-ͯ]+(?:['’ʼ‘\-‐‑][\ẁ-ͯ]+)*")
_NON_LETTER = re.compile(r"[\W\d_]")


def norm_token(raw: str) -> str:
    t = unicodedata.normalize("NFKC", raw).casefold().replace("ё", "е")
    return _NON_LETTER.sub("", t)


def tokenize(text: str) -> list[Token]:
    out = []
    for m in _WORD.finditer(text):
        n = norm_token(m.group())
        if n:
            out.append(Token(n, m.start(), m.end()))
    return out


def normalize(text: str) -> str:
    """The normalised form of ``text`` as a single string (SPEC §8 steps 1–6)."""
    return " ".join(t.norm for t in tokenize(text))


# Bible-style references a model may put inside or around a quote: "John 3:16", "1 Cor. 13:4-7",
# bare "3:16", "[16]", "(KJV)". Digits are dropped by the tokenizer anyway; this removes the
# book names that would otherwise remain as stray words.
_REFERENCE = re.compile(
    r"(?:\b(?:[1-3]|I{1,3})\s?)?\b[A-Z][a-z]+\.?\s+\d+:\d+(?:\s*[-–]\s*\d+)?"
    r"|\b\d+:\d+(?:\s*[-–]\s*\d+)?"
    r"|\[\d+\]"
    r"|\((?:KJV|King James Version)\)"
)


def clean_quote(quote: str, speakers: Iterable[str] = ()) -> str:
    """Remove references and (optionally) leading speaker names from a model's quote.

    ``speakers`` (e.g. play character names) are stripped only at the start of a line and
    only when followed by a colon or period, as in "HAMLET: To be, or not to be".
    """
    text = _REFERENCE.sub(" ", quote)
    names = sorted({s for s in speakers if s}, key=len, reverse=True)
    if names:
        pat = re.compile(r"(?im)^\s*(?:" + "|".join(re.escape(n) for n in names) + r")\s*[:.]\s+")
        text = pat.sub("", text)
    return text


# --------------------------------------------------------------------------------------
# Alignment


# Systematic English spelling patterns: two words that map to the same canonical form are
# variants (British/American spelling, elisions such as wash'd/washed and know'st/knowest).
_CANON_RULES = [
    (re.compile(r"(?<=\w{3})our(s|ed|ing|able|ite|ites)?$"), r"or\1"),  # honour → honor
    (re.compile(r"(?<=\w{3})ence(s)?$"), r"ense\1"),  # defence → defense
    (re.compile(r"(?<=\w{3})is(e|ed|es|ing|ation|ations)$"), r"iz\1"),  # realise → realize
    (re.compile(r"(?<=\w{2})yse(d|s)?$"), r"yze\1"),  # analyse → analyze
    (re.compile(r"(?<=\w{3})tre(s)?$"), r"ter\1"),  # centre → center
    (re.compile(r"(?<=\w{3})ll(ed|ing|er|ers)$"), r"l\1"),  # travelled → traveled
    (re.compile(r"(?<=\w{2}[bcdfghjklmnpqrstvwxz])ed$"), "d"),  # washed → washd (wash'd)
    (re.compile(r"(?<=\w{2}[bcdfghjklmnpqrstvwxz])est$"), "st"),  # knowest → knowst (know'st)
]


def _canonical_spelling(w: str) -> str:
    for pat, rep in _CANON_RULES:
        w = pat.sub(rep, w)
    return w


def _archaic_ending(a: str, b: str) -> bool:
    """believeth/believes, goeth/goes, loveth/loves (archaic third-person -eth)."""
    for x, y in ((a, b), (b, a)):
        if len(x) >= 5 and x.endswith("eth") and y in (x[:-3] + "s", x[:-3] + "es"):
            return True
    return False


class Aligner:
    """Weighted token edit distance with spelling-variant substitutions.

    Two different words count as spelling variants (cost ``variant_cost`` instead of 1) if
    (a) they are listed in ``variants.pairs``, (b) they match a systematic spelling pattern
    (``_CANON_RULES``, archaic -eth), or (c) they are character-similar AND one of them never
    occurs in the source (``vocab``) — so "world" for "word" is a real change, because both
    are words of the text, while "Ninevah" for "Nineveh" is a variant.
    """

    def __init__(self, cfg: ScoringConfig, vocab: set[str] | None = None):
        self.cfg = cfg
        self.vocab = vocab if vocab is not None else set()
        self._cache: dict[tuple[str, str], float] = {}

    def is_variant(self, a: str, b: str) -> bool:
        cfg = self.cfg
        if (a, b) in cfg.variant_pairs:
            return True
        if _canonical_spelling(a) == _canonical_spelling(b) or _archaic_ending(a, b):
            return True
        return (
            not (a in self.vocab and b in self.vocab)
            and min(len(a), len(b)) >= cfg.variant_min_length
            and Indel.normalized_similarity(a, b) >= cfg.variant_char_similarity
        )

    def sub_cost(self, a: str, b: str) -> float:
        if a == b:
            return 0.0
        key = (a, b)
        cost = self._cache.get(key)
        if cost is None:
            cost = self.cfg.variant_cost if self.is_variant(a, b) else 1.0
            self._cache[key] = cost
        return cost

    def align(self, q: Sequence[str], s: Sequence[str], free_ends: bool = False) -> tuple[float, int, int, int]:
        """Cost of editing ``s`` (or, with ``free_ends``, its best substring) into ``q``.

        Returns (cost, start, end, hard_edits): s[start:end] is the aligned span of ``s``, and
        ``hard_edits`` counts word changes, additions and omissions (spelling variants excluded).
        """
        n, m = len(q), len(s)
        sub = self.sub_cost
        if free_ends:
            prev = [0.0] * (m + 1)
            prev_start = list(range(m + 1))
        else:
            prev = [float(j) for j in range(m + 1)]
            prev_start = [0] * (m + 1)
        prev_hard = [0] * (m + 1) if free_ends else list(range(m + 1))
        for i in range(1, n + 1):
            qi = q[i - 1]
            cur = [float(i)] + [0.0] * m
            cur_start = [prev_start[0] if free_ends else 0] + [0] * m
            cur_hard = [i] + [0] * m
            for j in range(1, m + 1):
                c_sub = sub(qi, s[j - 1])
                best = prev[j - 1] + c_sub
                start, hard = prev_start[j - 1], prev_hard[j - 1] + (c_sub == 1.0)
                c = prev[j] + 1.0  # extra word in q
                if c < best:
                    best, start, hard = c, prev_start[j], prev_hard[j] + 1
                c = cur[j - 1] + 1.0  # word of s missing from q
                if c < best:
                    best, start, hard = c, cur_start[j - 1], cur_hard[j - 1] + 1
                cur[j], cur_start[j], cur_hard[j] = best, start, hard
            prev, prev_start, prev_hard = cur, cur_start, cur_hard
        if free_ends:
            end = min(range(m + 1), key=lambda j: (prev[j], j - prev_start[j]))
            return prev[end], prev_start[end], end, prev_hard[end]
        return prev[m], 0, m, prev_hard[m]

    @staticmethod
    def similarity(cost: float, q_len: int, span_len: int) -> float:
        denom = max(q_len, span_len)
        return max(0.0, 1.0 - cost / denom) if denom else 0.0


# --------------------------------------------------------------------------------------
# Source index and search


class _Letters:
    """The letters of a run of words without the spaces, and where each word starts."""

    def __init__(self, words: Sequence[str]):
        self.text = "".join(words)
        self.bounds = array("l", [0])
        for w in words:
            self.bounds.append(self.bounds[-1] + len(w))

    def _word_at(self, offset: int) -> int | None:
        """The number of the word boundary at a letter offset; None inside a word."""
        i = bisect_left(self.bounds, offset)
        return i if i < len(self.bounds) and self.bounds[i] == offset else None

    def spans(self, needle: str) -> list[tuple[int, int]]:
        """Every run of whole words whose letters are exactly ``needle``."""
        out = []
        at = self.text.find(needle) if needle else -1
        while at != -1:
            start, end = self._word_at(at), self._word_at(at + len(needle))
            if start is not None and end is not None:
                out.append((start, end))
            at = self.text.find(needle, at + 1)
        return out


def letter_spans(needle: Sequence[str], haystack: Sequence[str]) -> list[tuple[int, int]]:
    """Every span of whole words of ``haystack`` with the same letters, in order, as ``needle``.

    Where the words are divided is ignored ("any thing" = "anything", "in ’t" = "in't"), but a
    span never starts or ends inside a word ("thing" is not found in "anything").
    """
    return _Letters(haystack).spans("".join(needle))


@dataclass
class Match:
    similarity: float
    cost: float
    start: int  # token positions in the source stream
    end: int
    units: list[int]  # indices of the source units the span touches
    text: str  # the span as printed in the source
    hard_edits: int = 0  # changed / added / dropped words (spelling variants not counted)

    @property
    def exact(self) -> bool:
        return self.cost == 0


class SourceIndex:
    """A source text as one stream of normalised tokens, with an n-gram index for search.

    ``units`` are the addressable pieces of the source (verses, lines, sentences, or simply
    paragraphs for ``quotecheck``); matches report which units they touch.
    """

    def __init__(self, units: Sequence[str], cfg: ScoringConfig | None = None):
        self.cfg = cfg or ScoringConfig.load()
        self.aligner = Aligner(self.cfg)
        self.units = list(units)
        self.tokens: list[str] = []
        self.token_unit = array("i")
        self.token_start = array("i")
        self.token_end = array("i")
        self.unit_span: list[tuple[int, int]] = []
        for u, text in enumerate(self.units):
            first = len(self.tokens)
            for t in tokenize(text):
                self.tokens.append(t.norm)
                self.token_unit.append(u)
                self.token_start.append(t.start)
                self.token_end.append(t.end)
            self.unit_span.append((first, len(self.tokens)))
        self.aligner.vocab = set(self.tokens)
        self._postings: dict[int, dict[tuple[str, ...], list[int]]] = {}
        self._letters: _Letters | None = None

    def postings(self, k: int) -> dict[tuple[str, ...], list[int]]:
        if k not in self._postings:
            idx: dict[tuple[str, ...], list[int]] = defaultdict(list)
            toks = self.tokens
            for p in range(len(toks) - k + 1):
                idx[tuple(toks[p : p + k])].append(p)
            self._postings[k] = dict(idx)
        return self._postings[k]

    def span_text(self, start: int, end: int) -> str:
        if start >= end:
            return ""
        pieces = []
        p = start
        while p < end:
            u = self.token_unit[p]
            last = min(end, self.unit_span[u][1]) - 1
            pieces.append(self.units[u][self.token_start[p] : self.token_end[last]])
            p = last + 1
        return " ".join(pieces)

    def make_match(self, cost: float, q_len: int, start: int, end: int, hard_edits: int = 0) -> Match:
        sim = Aligner.similarity(cost, q_len, end - start)
        units = sorted({self.token_unit[p] for p in range(start, end)}) if end > start else []
        return Match(sim, cost, start, end, units, self.span_text(start, end), hard_edits)

    def substantial(self, m: Match) -> bool:
        """A match long enough to identify a passage: >= partial_min_words words, or exactly
        whole units (a short verse or line matched from its first word to its last)."""
        if m.end - m.start >= self.cfg.partial_min_words:
            return True
        return bool(m.units) and m.start == self.unit_span[m.units[0]][0] and m.end == self.unit_span[m.units[-1]][1]

    def compare(self, q: Sequence[str], start: int, end: int) -> Match:
        """Align ``q`` against exactly the source span [start, end)."""
        cost, _, _, hard = self.aligner.align(q, self.tokens[start:end])
        return self.make_match(cost, len(q), start, end, hard)

    def occurrences(self, q: Sequence[str]) -> list[Match]:
        """Every place where the source has ``q`` word for word (see ``letter_spans``)."""
        if self._letters is None:
            self._letters = _Letters(self.tokens)
        return [self.make_match(0.0, e - s, s, e) for s, e in self._letters.spans("".join(q))]

    def search(self, q: Sequence[str]) -> Match | None:
        """Best-matching span for ``q`` anywhere in the source (None if no shared words)."""
        n = len(q)
        if n == 0 or not self.tokens:
            return None
        cfg = self.cfg
        k = min(cfg.ngram, n)
        post = self.postings(k)
        grams = []
        for i in range(n - k + 1):
            hits = post.get(tuple(q[i : i + k]))
            if hits:
                grams.append((len(hits), i, hits))
        if not grams and k > 1:
            post = self.postings(1)
            grams = [(len(h), i, h) for i in range(n) if (h := post.get((q[i],)))]
        if not grams:
            return None
        grams.sort(key=lambda g: g[0])
        usable = [g for g in grams if g[0] <= cfg.max_postings] or grams[:2]
        votes: Counter[int] = Counter()
        bucket = 4
        for _, i, hits in usable:
            for p in hits[: max(cfg.max_postings, 1)]:
                votes[(p - i) // bucket] += 1
        best: Match | None = None
        seen: list[tuple[int, int]] = []
        for b, _ in votes.most_common(cfg.candidates * 3):
            lo = max(0, b * bucket - cfg.window_slack)
            hi = min(len(self.tokens), b * bucket + bucket + n + cfg.window_slack)
            if any(lo >= s and hi <= e for s, e in seen):
                continue
            seen.append((lo, hi))
            cost, s0, s1, hard = self.aligner.align(q, self.tokens[lo:hi], free_ends=True)
            m = self.make_match(cost, n, lo + s0, lo + s1, hard)
            if best is None or (m.similarity, -m.cost) > (best.similarity, -best.cost):
                best = m
            if len(seen) >= cfg.candidates:
                break
        return best


# --------------------------------------------------------------------------------------
# Labels


@dataclass
class QuoteScore:
    label: str
    similarity: float | None = None
    flags: list[str] = field(default_factory=list)
    match: Match | None = None
    target_similarity: float | None = None  # similarity to the requested passage (Tasks 1–2)

    def to_dict(self) -> dict:
        m = self.match
        return {
            "label": self.label,
            "similarity": None if self.similarity is None else round(self.similarity, 4),
            "target_similarity": None if self.target_similarity is None else round(self.target_similarity, 4),
            "flags": list(self.flags),
            "match_units": m.units if m else [],
            "match_text": m.text if m else "",
        }


def label_for(similarity: float, exact: bool, cfg: ScoringConfig, hard_edits: int = 0) -> str:
    if exact:
        return EXACT
    if similarity >= cfg.upper and (cfg.minor_rule == "similarity" or hard_edits == 0):
        return MINOR
    if similarity >= cfg.lower:
        return ALTERED
    return FABRICATED


def score_free(quote_tokens: Sequence[str], index: SourceIndex) -> QuoteScore:
    """Score a quote with no single right answer: best match anywhere in the source."""
    best = index.search(quote_tokens)
    flags = ["SHORT_QUOTE"] if len(quote_tokens) < index.cfg.partial_min_words else []
    if best is None:
        return QuoteScore(FABRICATED, 0.0, flags)
    return QuoteScore(label_for(best.similarity, best.exact, index.cfg, best.hard_edits), best.similarity, flags, best)


def score_anywhere(quote_tokens: Sequence[str], index: SourceIndex) -> tuple[QuoteScore, list[Match]]:
    """``score_free`` by letters instead of words, with every place the quote occurs verbatim.

    The benchmark's rule for topic quotes and trick questions. It is not in ``score_free`` because
    ``quotecheck`` writes numbers as words there, and "1 2" must not quote "12".
    """
    q = list(quote_tokens)
    score = score_free(q, index)
    places = index.occurrences(q)
    if places and score.label != EXACT:
        score = QuoteScore(EXACT, 1.0, score.flags + _word_division(q, index, places[0]), places[0])
    return score, places


def _word_division(q: Sequence[str], index: SourceIndex, m: Match) -> list[str]:
    return ["WORD_DIVISION"] if list(q) != index.tokens[m.start : m.end] else []


def _verbatim(q: list[str], index: SourceIndex, t0: int, t1: int) -> QuoteScore | None:
    """EXACT if ``q`` is the target, contains it (OVERLONG) or is a part of it (PARTIAL), by letters."""
    cfg, target = index.cfg, index.tokens[t0:t1]

    def exact(part: list[str], start: int, end: int, flags: list[str]) -> QuoteScore:
        m = index.make_match(0.0, end - start, start, end)
        return QuoteScore(EXACT, 1.0, flags + _word_division(part, index, m), m, target_similarity=1.0)

    inside = letter_spans(target, q)  # the whole target, in the quote
    if inside:
        q0, q1 = inside[0]
        if (q0, q1) == (0, len(q)):
            return exact(q, t0, t1, [])
        score = exact(q[q0:q1], t0, t1, ["OVERLONG"])
        for part in (q[:q0], q[q1:]):
            if len(part) >= cfg.partial_min_words:
                m = index.search(part)
                if m is None or m.similarity < cfg.lower:
                    score.flags.append("OVERLONG_EXTRA_UNMATCHED")
                    break
        return score
    part_of = letter_spans(q, target)  # the whole quote, in the target
    if part_of and min(len(q), part_of[0][1] - part_of[0][0]) >= cfg.fragment_min_words:
        return exact(q, t0 + part_of[0][0], t0 + part_of[0][1], ["PARTIAL"])
    return None


def score_targeted(quote_tokens: Sequence[str], index: SourceIndex, target_units: Sequence[int]) -> QuoteScore:
    """Score a quote that should reproduce specific source units (Tasks 1 and 2).

    Compared against the target, allowing for an OVERLONG answer (target embedded in a longer
    quote) or a PARTIAL one (a fragment: ``fragment_min_words`` words if it is verbatim,
    ``partial_min_words`` otherwise). Also searched against the whole source, so a real passage
    from the wrong place is WRONG_PLACE, and nothing that is close to some passage of the source
    is FABRICATED (NEAR_TARGET: a changed part or a changed, longer version of the target;
    OTHER_PASSAGE: a changed passage from elsewhere).
    """
    cfg, al = index.cfg, index.aligner
    q = list(quote_tokens)
    n = len(q)
    t0 = index.unit_span[min(target_units)][0]
    t1 = index.unit_span[max(target_units)][1]
    target = index.tokens[t0:t1]
    flags: list[str] = []

    verbatim = _verbatim(q, index, t0, t1)
    if verbatim is not None:
        return verbatim

    cost, _, _, hard = al.align(q, target)
    sim = al.similarity(cost, n, len(target))
    match = index.make_match(cost, n, t0, t1, hard)
    near: list[tuple[float, Match]] = []  # similarity of a part of the quote or of the target

    if n > len(target):
        # Target inside a longer quote: align the target against the best substring of q.
        c2, q0, q1, h2 = al.align(target, q, free_ends=True)
        s2 = al.similarity(c2, len(target), q1 - q0)
        longer = index.make_match(c2, q1 - q0, t0, t1, h2)
        if s2 > sim and s2 >= cfg.upper:
            sim, hard, match = s2, h2, longer
            flags.append("OVERLONG")
            extra = [part for part in (q[:q0], q[q1:]) if len(part) >= cfg.partial_min_words]
            for part in extra:
                m = index.search(part)
                if m is None or m.similarity < cfg.lower:
                    flags.append("OVERLONG_EXTRA_UNMATCHED")
                    break
        elif min(len(target), q1 - q0) >= cfg.partial_min_words:
            near.append((s2, longer))
    elif n < len(target):
        c3, s0, s1, h3 = al.align(q, target, free_ends=True)
        s3 = al.similarity(c3, n, s1 - s0)
        part = index.make_match(c3, n, t0 + s0, t0 + s1, h3)
        if s3 > sim and s3 >= cfg.upper and n >= cfg.partial_min_words:
            sim, hard, match = s3, h3, part
            flags.append("PARTIAL")
        elif min(n, s1 - s0) >= cfg.fragment_min_words:
            near.append((s3, part))

    result = QuoteScore(label_for(sim, False, cfg, hard), sim, flags, match, target_similarity=sim)

    # Is it a better match for some other place in the source?
    best = index.search(q)
    if best is not None and not (best.end <= t0 or best.start >= t1):
        if min(n, best.end - best.start) >= cfg.fragment_min_words:
            near.append((best.similarity, best))
        best = None  # overlaps the target: not another place
    if best is None or not best.exact:
        # word for word somewhere else, apart from the division into words
        best = next((m for m in index.occurrences(q) if m.end <= t0 or m.start >= t1), best)
    if best is not None and not index.substantial(best):
        best = None  # a few words that happen to occur inside some other passage
    if best is not None and label_for(best.similarity, best.exact, cfg, best.hard_edits) in (EXACT, MINOR) \
            and best.similarity > sim:
        flags += _word_division(q, index, best) if best.exact else []
        return QuoteScore(WRONG_PLACE, best.similarity, flags, best, target_similarity=sim)
    if result.label == FABRICATED and best is not None and best.similarity >= cfg.lower:
        return QuoteScore(ALTERED, best.similarity, flags + ["OTHER_PASSAGE"], best, target_similarity=sim)
    if result.label == FABRICATED and near:
        s, m = max(near, key=lambda x: x[0])
        if s >= cfg.lower:
            return QuoteScore(ALTERED, s, flags + ["NEAR_TARGET"], m, target_similarity=sim)
    if result.label == FABRICATED and target_recall(q, target) >= 0.5:
        # Not verbatim, but built from the target's words: typically another translation or
        # a paraphrase of the right passage rather than invented text. Kept FABRICATED per
        # SPEC §8; the flag lets validation and the report separate the two.
        result.flags.append("RESEMBLES_TARGET")
    return result


def target_recall(q: Sequence[str], target: Sequence[str]) -> float:
    """Share of the target's words (with multiplicity) that also appear in the quote."""
    if not target:
        return 0.0
    have = Counter(q)
    hit = 0
    for w in target:
        if have[w] > 0:
            have[w] -= 1
            hit += 1
    return hit / len(target)


# --------------------------------------------------------------------------------------
# Model responses


@dataclass
class ParsedResponse:
    ok: bool
    quote: str = ""
    location: str = ""
    refused: bool = False
    method: str = "strict"  # strict | extracted | unparseable
    error: str = ""
    n_objects: int = 1  # >1: the answer contained several JSON answers (e.g. a self-correction)
    remarks: str = ""  # everything the answer says outside the quote and location of its first JSON answer
    taken_back: bool = False  # the last of several JSON answers has cannot_quote true


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.S | re.I)


def _balanced(text: str) -> Iterator[tuple[int, int]]:
    """(start, end) of each balanced {...} in ``text``, respecting JSON strings, left to right."""
    start = text.find("{")
    while start != -1:
        depth, in_str, esc, end = 0, False, False, None
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is not None:
            yield start, end
        start = text.find("{", start + 1 if end is None else end)


def _json_objects(text: str) -> list[tuple[int, int, dict]]:
    """(start, end, value) of each valid JSON object in ``text``; invalid ones are passed over."""
    out = []
    for start, end in _balanced(text):
        try:
            out.append((start, end, json.loads(text[start:end])))
        except json.JSONDecodeError:
            pass
    return out


def _truthy(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in {"true", "yes", "1"}
    return bool(v)


def _refuses(obj: dict) -> bool:
    return _truthy(obj.get("cannot_quote", False)) or _truthy(obj.get("cannot_locate", False))


def _strings(obj: dict, leave_out: tuple[str, ...] = ("quote",)) -> list[str]:
    return [v for k, v in obj.items() if isinstance(v, str) and k not in leave_out]


def parse_response(raw: str | None) -> ParsedResponse:
    """Parse a model's JSON answer: strictly first, then the first JSON object in the text.

    SPEC §7: otherwise the first valid JSON object in the text (inside a code fence or not). A model
    that gives a second, "corrected" answer is judged on its first one; what the rest of the answer
    says is kept in ``remarks`` and ``taken_back``, which only describe answers to trick questions.
    """
    if not isinstance(raw, str) or not raw.strip():  # None, or NaN from a dataframe
        return ParsedResponse(False, method="unparseable", error="empty response")
    text = raw.strip()
    obj, method, later, outside = None, "strict", [], ""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        method = "extracted"
        found = _json_objects(text)
        fenced = _FENCE.match(text)
        try:
            obj = json.loads(fenced.group(1) if fenced else "")
        except json.JSONDecodeError:
            obj = found[0][2] if found else None
        later = [value for _, _, value in found[1:]]
        for start, end, _ in reversed(found):
            text = text[:start] + " " + text[end:]
        outside = text
    if not isinstance(obj, dict):
        return ParsedResponse(False, method="unparseable", error="no JSON object found")
    quote = obj.get("quote") or ""
    location = obj.get("location") or ""
    notes = _strings(obj, ("quote", "location"))
    return ParsedResponse(
        True,
        quote=quote if isinstance(quote, str) else json.dumps(quote, ensure_ascii=False),
        location=location if isinstance(location, str) else json.dumps(location, ensure_ascii=False),
        refused=_refuses(obj),
        method=method,
        n_objects=1 + len(later),
        remarks="\n".join([*notes, outside, *(x for o in later for x in _strings(o))]).strip(),
        taken_back=bool(later) and _refuses(later[-1]),
    )


# --------------------------------------------------------------------------------------
# Benchmark answers (question-aware wrapper)

_INDEXES: dict[str, tuple[SourceIndex, list[dict], frozenset[str]]] = {}


def load_index(text_id: str) -> tuple[SourceIndex, list[dict], frozenset[str]]:
    """(index, unit records, speaker names) for a parsed source, cached per process."""
    if text_id not in _INDEXES:
        from .sources import load_units

        units = load_units(text_id)
        index = SourceIndex([u["text"] for u in units])
        speakers = frozenset(u["speaker"] for u in units if u.get("speaker"))
        _INDEXES[text_id] = (index, units, speakers)
    return _INDEXES[text_id]


def score_answer(question: dict, raw_response: str | None, error: str | None = None) -> dict:
    """Label one model answer to one benchmark question (baseline / cautious conditions).

    ``question`` needs ``text_id``, ``task`` and ``should_abstain``; Tasks 1–2 also need
    ``target_units`` (unit idx values of the ground-truth passage).
    """
    from .locations import location_correct, says_not_there, says_other_source

    out = {"label": None, "similarity": None, "target_similarity": None, "flags": [],
           "match_units": [], "match_text": "", "quote_label": None, "location_correct": None,
           "parse_method": None}
    if error:
        return {**out, "label": ERROR, "flags": [error]}
    parsed = parse_response(raw_response)
    out["parse_method"] = parsed.method
    if not parsed.ok:
        return {**out, "label": UNPARSEABLE, "flags": [parsed.error]}

    index, units, speakers = load_index(question["text_id"])
    if parsed.n_objects > 1:
        out["flags"].append("MULTIPLE_ANSWERS")
    tokens = [t.norm for t in tokenize(clean_quote(parsed.quote, speakers))]
    gave_quote = bool(tokens) and not parsed.refused
    if parsed.refused and tokens:
        out["flags"].append("QUOTE_DESPITE_REFUSAL")
    if not parsed.refused and not tokens:
        out["flags"].append("EMPTY_QUOTE")

    if question["should_abstain"]:
        if not gave_quote:
            return {**out, "label": CORRECT_REFUSAL}
        s, _ = score_anywhere(tokens, index)
        flags = out["flags"] + s.flags
        # Both flags leave the answer a failure; they record that it corrects itself.
        # SOURCE_CORRECTED: its location (or a remark inside the quote) says the line is not from the
        # named text. SELF_RETRACTED: it is taken back by a later JSON answer, or the answer says
        # anywhere that the passage does not exist or, outside that location, is not in the text.
        text_id, play = question["text_id"], question.get("play")
        if says_other_source(text_id, play, parsed.location, parsed.quote):
            flags.append("SOURCE_CORRECTED")
        reference = (question.get("prompt_vars") or {}).get("reference", "")
        if parsed.taken_back or says_not_there(text_id, play, reference, parsed.remarks, parsed.location, parsed.quote):
            flags.append("SELF_RETRACTED")
        return {**out, **s.to_dict(), "label": TRAP_FABRICATED, "quote_label": s.label, "flags": flags}

    if not gave_quote:
        return {**out, "label": ABSTAINED}

    if question["task"] in ("reference", "continuation"):
        s = score_targeted(tokens, index, question["target_units"])
        return {**out, **s.to_dict(), "quote_label": s.label, "flags": out["flags"] + s.flags}

    # topic: any real passage of the text, or of the play, asked about counts; then check the stated
    # location, which is right if the passage stands there at all, however many other places have
    # it word for word
    s, places = score_anywhere(tokens, index)
    res = {**out, **s.to_dict(), "quote_label": s.label, "flags": out["flags"] + s.flags}
    if s.match is not None and s.label in (EXACT, MINOR, ALTERED):
        titles = {u["chapter"]: u.get("chapter_title", "") for u in units if "chapter" in u}
        kw = {"chapter_titles": titles} if question["text_id"] in ("pride_prejudice", "origin_species") else {}
        play = question.get("play")

        def in_play(m: Match) -> bool:
            return not play or all(units[i].get("play") == play for i in m.units)

        def stands_there(m: Match) -> bool | None:
            """None if no location could be read; a passage of another play stands in no place of this one."""
            right = location_correct(question["text_id"], parsed.location, [units[i] for i in m.units], **kw)
            return right if right is None else right and in_play(m)

        best = next((m for m in [s.match, *places] if in_play(m) and stands_there(m)),
                    next((m for m in [s.match, *places] if in_play(m)), s.match))
        if best is not s.match:
            res.update(match_units=best.units, match_text=best.text)
        res["location_correct"] = stands_there(best)
        if s.label in (EXACT, MINOR) and (res["location_correct"] is False or not in_play(best)):
            res["label"] = WRONG_PLACE
    return res


def score_lookup(question: dict, raw_response: str | None, error: str | None = None) -> dict:
    """Label a ``lookup`` answer: the model names a passage, the system fetches it (SPEC §7).

    EXACT = the reference resolves to the requested passage (Task 1) or to any existing passage
    (Task 3; whether it fits the theme is not checked — flag THEME_UNCHECKED). WRONG_PLACE =
    an existing passage that is not the one requested. FABRICATED = a reference that does not
    exist. A location our parser cannot read is UNPARSEABLE (flag LOCATION_UNREADABLE), so
    parser gaps are reported rather than counted against the model.
    """
    from .locations import parse_any, resolve

    out = {"label": None, "flags": [], "match_units": [], "match_text": "", "location_correct": None,
           "parse_method": None, "similarity": None, "target_similarity": None, "quote_label": None}
    if error:
        return {**out, "label": ERROR, "flags": [error]}
    parsed = parse_response(raw_response)
    out["parse_method"] = parsed.method
    if not parsed.ok:
        return {**out, "label": UNPARSEABLE, "flags": [parsed.error]}
    _, units, _ = load_index(question["text_id"])
    if parsed.n_objects > 1:
        out["flags"].append("MULTIPLE_ANSWERS")
    location = parsed.location.strip()
    if parsed.refused or not location:
        flags = ["LOCATION_DESPITE_REFUSAL"] if parsed.refused and location else []
        return {**out, "label": CORRECT_REFUSAL if question["should_abstain"] else ABSTAINED, "flags": flags}

    loc = parse_any(question["text_id"], location)
    if loc is None:
        label = TRAP_FABRICATED if question["should_abstain"] else UNPARSEABLE
        return {**out, "label": label, "flags": ["LOCATION_UNREADABLE"]}
    hits = resolve(question["text_id"], loc, units)
    res = {**out, "match_units": hits, "match_text": " ".join(units[i]["text"] for i in hits[:5])}
    if question["should_abstain"]:
        return {**res, "label": TRAP_FABRICATED, "flags": ["REAL_REFERENCE" if hits else "NONEXISTENT_REFERENCE"]}
    if not hits:
        return {**res, "label": FABRICATED, "flags": ["NONEXISTENT_REFERENCE"]}
    if question["task"] == "topic":
        return {**res, "label": EXACT, "flags": ["THEME_UNCHECKED"]}
    target = set(question["target_units"])
    if target <= set(hits):
        return {**res, "label": EXACT, "flags": ["OVERLONG"] if len(hits) > len(target) else []}
    return {**res, "label": WRONG_PLACE}
