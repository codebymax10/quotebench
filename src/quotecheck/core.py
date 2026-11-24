"""Check the quotations found in a text against one source.

All scoring is the benchmark's own (``quotebench.scoring``): its tokenizer, n-gram index,
aligner, similarity and ``label_for``. This module only prepares text for it, handles the marks
a writer may put inside a quotation ("...", "[the]"), and maps token positions back to
characters of the original text.

One addition: the benchmark drops digits (they are verse numbers there). In a contract "30 days"
and "60 days" are different quotations, so by default digits are kept as words. They are
written with letters of an undeciphered script before tokenizing, which the benchmark's code
then treats like any other word. ``compare_numbers=False`` gives the benchmark's behaviour.
"""

from __future__ import annotations

import copy
import functools
import re
import unicodedata
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

from quotebench.scoring import (
    ALTERED, CONFIG_PATH, EXACT, FABRICATED, MINOR, Aligner, ScoringConfig, SourceIndex,
    clean_quote, label_for, score_free, tokenize,
)

from .extract import ExtractedQuote, extract_quotes

LABELS = (EXACT, MINOR, ALTERED, FABRICATED)

# Flags: what else the reader should know about a checked quote.
ELLIPSIS = "ELLIPSIS"  # exact, with words left out where the quote says "..."
BRACKETS = "BRACKETS"  # something in brackets was not compared: [inserted], [12], [sic], [^1], 【3†source】
OUT_OF_ORDER = "OUT_OF_ORDER"  # parts around "..." come from the source in another order
FAR_APART = "FAR_APART"  # a very short part around "..." is only found far from its neighbours
TOO_FRAGMENTED = "TOO_FRAGMENTED"  # so many "..." or [..] that matching the pieces proves nothing
NUMBERS_DIFFER = "NUMBERS_DIFFER"  # all words match; only numbers were changed, added or dropped
UNCLOSED = "UNCLOSED"  # no closing quotation mark: checked up to the end of the paragraph
ATTRIBUTION_IGNORED = "ATTRIBUTION_IGNORED"  # block quote: a last line "— Author" was not checked
SHORT_QUOTE = "SHORT_QUOTE"  # under the benchmark's partial_min_words (6): a match may be chance

SHORT_PART = 5  # parts with fewer words than this prove little on their own ...
SHORT_PART_GAP = 50  # ... so they must lie within this many source words of their neighbour
BRACKET_GAP = 6  # a [bracketed] insertion may stand for at most this many source words
MAX_PIECES = 100  # more pieces than this around "..." and [..] are not looked up one by one (cost)
LONG_QUOTE, CHUNK = 300, 150  # longer inexact quotes are aligned piece by piece (cost is quadratic)


# --------------------------------------------------------------------------------------
# Text preparation


_DIGIT0 = 0x10600  # Linear A signs: letters to the tokenizer, and never in a real document
_FRACTIONS = "¼½¾⅐⅑⅒⅓⅔⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞"
_FRACTION_MAP = {ord(c): _DIGIT0 + 10 + i for i, c in enumerate(_FRACTIONS)}
_LAST_SIGN = _DIGIT0 + 10 + len(_FRACTIONS)

# Removed before tokenizing: invisible characters, line-end hyphenation, emphasis inside a word.
_DELETE = re.compile(
    r"[­​-‏‪-‮⁠-⁤⁦-⁩﻿]+"
    r"|(?<=[^\W_][-‐])[ \t]*(?:\r\n?|\n)[ \t]*(?=[^\W_])"
    r"|(?<=[^\W\d_])\*+(?=[^\W\d_])"
)
_DIGIT_GROUPING = re.compile(r"(?<=\d)[,   ](?=\d{3}(?!\d))")  # 1,500 = 1500
_DIGIT_HYPHEN = re.compile(r"(?<=\d)[-‐‑](?=\d)")  # 12-15 = 12–15
# Formatting tags, with attributes or without. "<b not>" is not one: its words are compared.
_HTML = re.compile(
    r"</?(?:a|b|i|em|strong|u|s|br|p|div|span|mark|sup|sub|q|blockquote)(?:\s{1,50}[\w:-]{1,50}\s{0,50}=[^<>]{0,500}|\s{0,50}/?)>", re.I
)


def _is_number(token: str) -> bool:
    return any(_DIGIT0 <= ord(c) <= _LAST_SIGN for c in token)


def _encode_digits(text: str) -> str:
    table = dict(_FRACTION_MAP)
    for ch in set(text):
        if unicodedata.category(ch) == "Nd":
            table[ord(ch)] = _DIGIT0 + unicodedata.digit(ch)
    return text.translate(table)


class _Words:
    """The normalised words of a text, with their character positions in that text."""

    def __init__(self, text: str, numbers: bool):
        self.text = text
        prepared = _HTML.sub(lambda m: " " * len(m.group()), text)
        # Deletions shift positions; remember where each one happened to map back.
        cuts = [m.span() for m in _DELETE.finditer(prepared)]
        if numbers:
            cuts = sorted(cuts + [m.span() for m in _DIGIT_GROUPING.finditer(prepared)])
        self._cut_at: list[int] = []  # position in the prepared text
        self._removed: list[int] = []  # characters removed up to and including this cut
        if cuts:
            pieces, pos, removed = [], 0, 0
            for s, e in cuts:
                pieces.append(prepared[pos:s])
                self._cut_at.append(s - removed)
                removed += e - s
                self._removed.append(removed)
                pos = e
            prepared = "".join(pieces) + prepared[pos:]
        if numbers:
            prepared = _encode_digits(_DIGIT_HYPHEN.sub(" ", prepared))
        self.prepared = prepared
        self._tokens = None

    @property
    def tokens(self):
        if self._tokens is None:
            self._tokens = tokenize(self.prepared)
        return self._tokens

    @property
    def norms(self) -> list[str]:
        return [t.norm for t in self.tokens]

    def original(self, pos: int, end: bool = False) -> int:
        """Position in the original text of a character position in the prepared text."""
        # A word that ends exactly at a cut ends before it; one that starts there starts after.
        k = bisect_right(self._cut_at, pos - 1 if end else pos) - 1
        return pos + (self._removed[k] if k >= 0 else 0)


# --------------------------------------------------------------------------------------
# Source


class _Aligner(Aligner):
    """The benchmark's aligner, except that some words never count as spelling variants:
    numbers, and (the spelling patterns are English) words of other languages."""

    def __init__(self, cfg: ScoringConfig, vocab: set[str], language: str):
        super().__init__(cfg, vocab)
        self.english = language.lower().split("-")[0].split("_")[0] == "en"

    def is_variant(self, a: str, b: str) -> bool:
        return self.english and not _is_number(a) and not _is_number(b) and super().is_variant(a, b)


@functools.cache
def default_config() -> ScoringConfig:
    """The benchmark's frozen scoring settings (bundled in the wheel, config/ in a checkout)."""
    bundled = Path(__file__).with_name("scoring.yaml")
    return ScoringConfig.load(bundled if bundled.exists() else CONFIG_PATH)


class Source:
    """A source text to check quotations against. Build it once and reuse it: the index is kept."""

    def __init__(self, text: str, language: str = "en"):
        if not isinstance(text, str):
            raise TypeError(f"source text must be str, not {type(text).__name__}")
        _check_language(language)
        self.text = text
        self.language = language
        self._indexed: dict[bool, tuple[_Words, SourceIndex]] = {}

    @classmethod
    def from_text(cls, text: str, language: str = "en") -> "Source":
        return cls(text, language)

    @classmethod
    def from_file(cls, path, language: str = "en", encoding: str = "utf-8-sig") -> "Source":
        """The file's text as it is: positions refer to the decoded text without a byte order
        mark, and line ends are not translated ("\r\n" counts as two characters)."""
        return cls(Path(path).read_bytes().decode(encoding), language)

    def __repr__(self) -> str:
        return f"Source({len(self.text):,} characters, language={self.language!r})"

    def _index(self, numbers: bool, language: str, cfg: ScoringConfig) -> tuple[_Words, SourceIndex]:
        if numbers not in self._indexed:
            words = _Words(self.text, numbers)
            self._indexed[numbers] = (words, SourceIndex([words.prepared], cfg))
        words, base = self._indexed[numbers]
        view = copy.copy(base)  # shares the tokens and the n-gram index
        view.cfg, view.aligner = cfg, _Aligner(cfg, base.aligner.vocab, language)
        return words, view

    def line_of(self, position: int) -> int:
        """1-based line number of a character position."""
        return _line_of(self.text, position)


def _line_of(text: str, position: int) -> int:
    """1-based line number; a line ends with "\n", "\r\n" or (old Mac files) "\r"."""
    return 1 + sum(text.count(end, 0, position) * n for end, n in (("\n", 1), ("\r", 1), ("\r\n", -1)))


# --------------------------------------------------------------------------------------
# Report


@dataclass
class QuotePart:
    """One piece of a quotation that contains an ellipsis (or is very long)."""

    text: str
    label: str
    similarity: float
    best_match: str = ""
    source_start: int | None = None
    source_end: int | None = None


@dataclass
class QuoteResult:
    text: str  # as written, without the quotation marks
    label: str  # EXACT | MINOR | ALTERED | FABRICATED
    similarity: float  # 0..1; 1 only if EXACT
    best_match: str  # closest passage, as printed in the source ("" if none)
    source_start: int | None  # its position: source.text[source_start:source_end]
    source_end: int | None
    start: int  # position of the quote in the checked text
    end: int
    kind: str  # straight | curly | guillemet | single | block
    words: int
    flags: list[str] = field(default_factory=list)
    parts: list[QuotePart] = field(default_factory=list)  # only if checked in several parts

    @property
    def exact(self) -> bool:
        return self.label == EXACT


@dataclass
class Report:
    quotes: list[QuoteResult]
    skipped: list[ExtractedQuote]  # quotes shorter than min_words: not checked
    stray_marks: int  # closing quotation marks without an opening one
    warnings: list[str]
    min_words: int

    @property
    def counts(self) -> dict[str, int]:
        have = Counter(q.label for q in self.quotes)
        return {label: have[label] for label in LABELS}

    @property
    def all_exact(self) -> bool:
        return all(q.exact for q in self.quotes)

    def to_dict(self) -> dict:
        return {
            "all_exact": self.all_exact,
            "counts": self.counts,
            "skipped_short": len(self.skipped),
            "min_words": self.min_words,
            "stray_marks": self.stray_marks,
            "warnings": list(self.warnings),
            "quotes": [
                {**vars(q), "similarity": _floor(q.similarity), "flags": list(q.flags),
                 "parts": [{**vars(p), "similarity": _floor(p.similarity)} for p in q.parts]}
                for q in self.quotes
            ],
            "skipped": [{"text": s.text, "start": s.start, "end": s.end, "kind": s.kind} for s in self.skipped],
        }


def _floor(x: float) -> float:
    """Four decimals, rounded down: only a perfect match may show as 1."""
    return int(x * 10000 + 1e-9) / 10000


# --------------------------------------------------------------------------------------
# Inside one quotation: ellipses and bracketed insertions


_DOTS = r"(?:\.(?:[  ]?\.)+|…+)"
_INSIDE = re.compile(
    rf"(?P<ellipsis>\[\s*{_DOTS}\s*\]|\(\s*{_DOTS}\s*\)|{_DOTS}|\*[ ]\*[ ]\*)"
    r"|(?P<link>\[(?P<label>[^\[\]]+)\]\([^()\s]*\))"  # Markdown link: keep its text
    r"|(?P<note>【[^【】]*】|\[\^[^\[\]\s]+\]|\[\d+(?:\s*[,;–-]\s*\d+)*\]|\[(?:sic|emphasis[^\[\]]*)[.!]?\])"
    # [T]he, small[er]. Letters before "[" are only tried from the start of the word: linear cost.
    r"|(?P<inword>(?:(?<![^\W\d_])[^\W\d_]++)?\[[^\W\d_]{1,30}\][^\W\d_]++|(?<![^\W\d_])[^\W\d_]++\[(?!sic\])[^\W\d_]{1,30}\])"
    r"|(?P<bracket>\[[^\[\]]{1,300}\])",
    re.I,
)


_ADDRESS = re.compile(r"[/.:#?@]")  # in the (...) of a Markdown link


@dataclass
class _Piece:
    text: str
    gap: str | None  # what separates it from the piece before: None (first) | ELLIPSIS | BRACKETS


@dataclass
class _Reading:
    plain: str  # the quote with its bracketed words kept
    pieces: list[_Piece]  # the quote split at every ellipsis and bracket, notes ([12], [sic]) left out
    plain_omits: list[str]  # what is in brackets and not compared in the first reading ...
    pieces_omit: bool  # ... and whether there is any in the second


def _read(text: str) -> _Reading:
    plain: list[str] = []
    pieces = [_Piece("", None)]
    plain_omits: list[str] = []
    pieces_omit = False
    pos = 0
    for m in _INSIDE.finditer(text):
        before = text[pos : m.start()]
        pos = m.end()
        plain.append(before)
        pieces[-1].text += before
        if m["link"]:
            plain.append(m["label"])
            pieces[-1].text += m["label"]
            target = m["link"][len(m["label"]) + 2 :]
            if any(c.isalnum() for c in target) and not _ADDRESS.search(target):  # [shall](not)
                plain_omits.append(m["link"])
                pieces_omit = True
        elif m["note"]:
            pieces_omit = True
            if m["note"].startswith("【"):
                plain_omits.append(m["note"])
            plain.append(" " if m["note"].startswith("【") else m["note"])
            pieces[-1].text += " "
        elif m["ellipsis"]:
            plain.append(m["ellipsis"])
            pieces.append(_Piece("", ELLIPSIS))
        elif m["inword"] and re.match(r"\[.\]", m["inword"]):  # [T]he: only the case was changed
            plain.append(re.sub(r"[\[\]]", "", m["inword"]))
            pieces[-1].text += re.sub(r"[\[\]]", "", m["inword"])
        else:
            whole = m["inword"] or m["bracket"]
            pieces_omit = True
            if not any(c.isalnum() for c in whole) and whole[1:-1].strip():  # [,]
                plain_omits.append(whole)
            plain.append(re.sub(r"[\[\]]", "", whole) if m["inword"] else whole)
            pieces.append(_Piece("", BRACKETS))
    plain.append(text[pos:])
    pieces[-1].text += text[pos:]
    return _Reading("".join(plain), pieces, plain_omits, pieces_omit)


@dataclass
class _Segment:
    words: _Words
    norms: list[str]
    gap: str | None


def _segments(pieces: list[_Piece], numbers: bool) -> list[_Segment]:
    """The pieces that contain words; an ellipsis next to a bracket counts as an ellipsis."""
    out: list[_Segment] = []
    gap: str | None = None
    for p in pieces:
        if p.gap == ELLIPSIS or gap is None:
            gap = p.gap or gap
        words = _Words(p.text, numbers)
        norms = words.norms
        if norms:
            out.append(_Segment(words, norms, gap if out else None))
            gap = None
    return out


# --------------------------------------------------------------------------------------
# Matching


def _occurrences(q: list[str], index: SourceIndex) -> list[int]:
    """Every source position where exactly the words ``q`` stand."""
    n, toks = len(q), index.tokens
    if n == 0 or n > len(toks):
        return []
    k = min(index.cfg.ngram, n)
    post = index.postings(k)
    rarest, at = None, 0
    for i in range(n - k + 1):
        hits = post.get(tuple(q[i : i + k]))
        if not hits:
            return []
        if rarest is None or len(hits) < len(rarest):
            rarest, at = hits, i
    return [p - at for p in rarest if p >= at and toks[p - at : p - at + n] == q]


def _place(segments: list[_Segment], index: SourceIndex) -> list[tuple[int, int]] | None:
    """Positions of the segments, each word for word, in order, within the allowed gaps.

    Of all possible placements, one that spans few words (exact: the shortest chain of nearest
    predecessors). None if there is none.
    """
    levels = []  # per segment: (positions, index of predecessor, start of the chain)
    for si, seg in enumerate(segments):
        occ = _occurrences(seg.norms, index)
        if si == 0:
            level = ([*occ], [-1] * len(occ), [*occ])
        else:
            prev = segments[si - 1]
            limit = None
            if seg.gap == BRACKETS:
                limit = BRACKET_GAP
            elif min(len(seg.norms), len(prev.norms)) < SHORT_PART:
                limit = SHORT_PART_GAP
            pos, _, chain = levels[-1]
            level = ([], [], [])
            for p in occ:
                j = bisect_right(pos, p - len(prev.norms)) - 1
                if j < 0 or (limit is not None and p - (pos[j] + len(prev.norms)) > limit):
                    continue
                level[0].append(p)
                level[1].append(j)
                level[2].append(chain[j])
        if not level[0]:
            return None
        levels.append(level)
    k = min(range(len(levels[-1][0])), key=lambda i: levels[-1][0][i] - levels[-1][2][i])
    spans = []
    for si in range(len(segments) - 1, -1, -1):
        pos, back, _ = levels[si]
        spans.append((pos[k], pos[k] + len(segments[si].norms)))
        k = back[k]
    return spans[::-1]


def _fragmented(segments: list[_Segment], spans: list[tuple[int, int]]) -> bool:
    """Are the verbatim pieces too short, next to what was left out, to count as a quotation?"""
    if len(segments) == 1:
        return False
    kept = sum(len(s.norms) for s in segments)
    replaced = [b[0] - a[1] for a, b, s in zip(spans, spans[1:], segments[1:]) if s.gap == BRACKETS]
    return max(len(s.norms) for s in segments) < 3 or len(replaced) * 2 > kept or sum(replaced) > kept


@dataclass
class _Outcome:
    label: str
    similarity: float
    spans: list[tuple[int, int]]  # source token spans, in quote order
    flags: list[str] = field(default_factory=list)
    parts: list[tuple[str, str, float, tuple[int, int] | None]] = field(default_factory=list)

    @property
    def rank(self):
        return (-LABELS.index(self.label), self.similarity)


def _check_tokens(q: list[str], index: SourceIndex) -> _Outcome:
    """One run of words, no ellipses: the benchmark's free search."""
    score = score_free(q, index)
    m = score.match
    flags = []
    if m and score.label != EXACT:
        span = index.tokens[m.start : m.end]
        if [t for t in q if not _is_number(t)] == [t for t in span if not _is_number(t)]:
            flags.append(NUMBERS_DIFFER)
    return _Outcome(score.label, score.similarity or 0.0, [(m.start, m.end)] if m and m.end > m.start else [], flags)


def _check_in_parts(parts: list[_Segment], index: SourceIndex) -> _Outcome:
    """Inexact quote in several parts: score each, add up the costs, require the right order
    (a part out of order costs one word)."""
    cost, q_total, span_total, hard = 0.0, 0, 0, 0
    flags: list[str] = []
    results: list[tuple[str, str, float, tuple[int, int] | None]] = []
    n_long = [len(p.norms) >= SHORT_PART for p in parts]
    search = functools.cache(lambda words: index.search(words))  # the same words: the same match
    matches = [search(tuple(p.norms)) if is_long else None for p, is_long in zip(parts, n_long)]
    last_end: int | None = None
    for i, p in enumerate(parts):
        n, m = len(p.norms), matches[i]
        q_total += n
        if not n_long[i]:  # only counts if found close to its neighbours
            after = next((x.start for x in matches[i + 1 :] if x), None)
            everywhere = _occurrences(p.norms, index)
            near = [
                o for o in everywhere
                if (last_end is not None and 0 <= o - last_end <= SHORT_PART_GAP)
                or (after is not None and 0 <= after - (o + n) <= SHORT_PART_GAP)
            ]
            if near:
                start = next((o for o in near if last_end is None or o >= last_end), near[0])
                span = (start, start + n)
                span_total += n
                if last_end is not None and start < last_end:
                    cost, hard = cost + 1, hard + 1
                    flags.append(OUT_OF_ORDER)
                last_end = max(last_end or 0, span[1])
                results.append((p.words.text.strip(), EXACT, 1.0, span))
            else:
                cost, hard = cost + n, hard + n
                if everywhere:
                    flags.append(FAR_APART)
                results.append((p.words.text.strip(), FABRICATED, 0.0, None))
            continue
        if m is None:
            cost, hard = cost + n, hard + n
            results.append((p.words.text.strip(), FABRICATED, 0.0, None))
            continue
        label = label_for(m.similarity, m.exact, index.cfg, m.hard_edits)
        cost, span_total, hard = cost + m.cost, span_total + (m.end - m.start), hard + m.hard_edits
        if label != FABRICATED:  # the place of a made-up part means nothing
            if last_end is not None and m.start < last_end - (BRACKET_GAP if p.gap is None else 0):
                cost, hard = cost + 1, hard + 1
                flags.append(OUT_OF_ORDER)
            elif p.gap is None and last_end is not None and m.start > last_end:
                # Pieces of one long run: words of the source between them are missing.
                missing = min(m.start - last_end, n)
                cost, span_total = cost + missing, span_total + missing
            elif p.gap is None and last_end is not None:
                cost += last_end - m.start  # the same words of the source twice
            last_end = m.end
        results.append((p.words.text.strip(), label, m.similarity, (m.start, m.end)))
    sim = Aligner.similarity(cost or 1.0, q_total, span_total)  # an exact quote never gets here
    label = label_for(sim, False, index.cfg, max(hard, 1))
    flags = list(dict.fromkeys(flags))
    return _Outcome(label, sim, [r[3] for r in results if r[3]], flags, results)


def _chunks(seg: _Segment) -> list[_Segment]:
    """A very long run of words as consecutive pieces (gap None = must follow directly)."""
    n = len(seg.norms)
    if n <= LONG_QUOTE:
        return [seg]
    out = []
    tokens, w = seg.words.tokens, seg.words
    for a in range(0, n, CHUNK):
        b = min(n, a + CHUNK)
        piece = copy.copy(w)
        piece.text = w.text[w.original(tokens[a].start) : w.original(tokens[b - 1].end, end=True)]
        out.append(_Segment(piece, seg.norms[a:b], seg.gap if a == 0 else None))
    if len(out) > 1 and len(out[-1].norms) < SHORT_PART:
        last = out.pop()
        out[-1].norms += last.norms
    return out


def _check_quote(text: str, index: SourceIndex, numbers: bool) -> tuple[_Outcome, int]:
    """(outcome, number of words the quote claims to take from the source)."""
    if not numbers:
        text = clean_quote(text)
    reading = _read(text)
    segments = _segments(reading.pieces, numbers)
    n_words = sum(len(s.norms) for s in segments)
    if n_words == 0:
        return _Outcome(FABRICATED, 0.0, []), 0

    plain = _Segment(_Words(reading.plain, numbers), [], None)
    plain.norms = plain.words.norms
    occ = _occurrences(plain.norms, index)
    if occ:
        span = (occ[0], occ[0] + len(plain.norms))
        printed = index.span_text(*span)  # brackets that the source has too are not left out
        flags = [BRACKETS] if any(o not in printed for o in reading.plain_omits) else []
        return _Outcome(EXACT, 1.0, [span], flags), n_words
    too_many = len(segments) > MAX_PIECES
    spans = None if too_many else _place(segments, index)
    fragmented = too_many or (spans is not None and _fragmented(segments, spans))
    if spans is not None and not fragmented:
        flags = [ELLIPSIS] if any(p.gap == ELLIPSIS for p in reading.pieces) else []
        flags += [BRACKETS] if reading.pieces_omit else []
        parts = [(s.words.text.strip(), EXACT, 1.0, sp) for s, sp in zip(segments, spans)]
        return _Outcome(EXACT, 1.0, spans, flags, parts if len(parts) > 1 else []), n_words

    # Not exact. Score it as one run of words (bracketed words kept, or left out) and, if it
    # has ellipses, part by part; report the reading that fits best. If the pieces prove nothing,
    # only as one run with every word counted.
    runs: list[list[_Segment]] = [[plain]]
    groups: list[list[_Segment]] = []
    for s in segments:
        if s.gap == BRACKETS:
            groups[-1].append(s)
        else:
            groups.append([s])
    no_brackets = []
    for g in groups:
        joined = _Words(" ".join(s.words.text for s in g), numbers)
        no_brackets.append(_Segment(joined, joined.norms, g[0].gap))
    if not fragmented and (no_brackets[0].norms != plain.norms or len(no_brackets) > 1):
        runs.append(no_brackets)
    outcomes = []
    for run in runs:
        parts = [c for s in run for c in _chunks(s)]
        if len(parts) == 1:
            outcome = _check_tokens(parts[0].norms, index)
        elif any(len(p.norms) >= SHORT_PART for p in parts):
            outcome = _check_in_parts(parts, index)
        else:
            continue
        if reading.plain_omits or (run is not runs[0] and reading.pieces_omit):
            outcome.flags.append(BRACKETS)
        if outcome.similarity < 1:  # an exact quote is returned above; no other reading makes one
            outcomes.append(outcome)
    # On a tie the reading that respects the quote's own marks wins (it is the later one).
    best = max(reversed(outcomes), key=lambda o: o.rank) if outcomes else _check_tokens(plain.norms, index)
    if fragmented:
        best.flags.append(TOO_FRAGMENTED)
    return best, n_words


# --------------------------------------------------------------------------------------
# Public entry point


def check(
    text: str,
    source: Source,
    *,
    min_words: int = 5,
    upper: float | None = None,
    lower: float | None = None,
    language: str | None = None,
    compare_numbers: bool = True,
) -> Report:
    """Find every quotation in ``text`` and check it against ``source``.

    min_words        quotes with fewer words are not checked, only counted (``report.skipped``)
    upper, lower     similarity thresholds between MINOR / ALTERED / FABRICATED
                     (default: the benchmark's 0.97 and 0.80). EXACT does not depend on them.
    language         default: the source's language. Spelling variants (label MINOR) are only
                     recognised for English ("en"); in other languages any other word is a change.
    compare_numbers  False: ignore digits and Bible-style references, as the benchmark does
                     (for texts with verse, page or footnote numbers).
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, not {type(text).__name__}")
    if not isinstance(source, Source):
        raise TypeError("source must be a quotecheck.Source, e.g. Source.from_text(...)")
    if isinstance(min_words, bool) or not isinstance(min_words, int) or min_words < 1:
        raise ValueError("min_words must be a whole number of at least 1")
    language = source.language if language is None else language
    _check_language(language)
    cfg = default_config()
    cfg = replace(cfg, upper=cfg.upper if upper is None else upper, lower=cfg.lower if lower is None else lower)
    if not 0 <= cfg.lower <= cfg.upper <= 1:
        raise ValueError(f"thresholds must satisfy 0 <= lower <= upper <= 1 (got lower={cfg.lower}, upper={cfg.upper})")

    words, index = source._index(compare_numbers, language, cfg)
    warnings = [] if index.tokens else ["the source contains no words, so no quote can be found in it"]
    found, stray = extract_quotes(text)
    quotes, skipped = [], []
    cache: dict[tuple, tuple[_Outcome, int]] = {}
    for q in found:
        n_words = _count_words(q.text, compare_numbers)
        if n_words == 0:
            continue
        if n_words < min_words:
            skipped.append(q)
            continue
        key = (q.text, q.without_attribution)
        if key not in cache:
            best, n = _check_quote(q.text, index, compare_numbers)
            if best.label != EXACT and q.without_attribution:
                other, n2 = _check_quote(q.without_attribution, index, compare_numbers)
                if n2 >= min_words and other.rank > best.rank:
                    best, n = other, n2
                    best.flags.append(ATTRIBUTION_IGNORED)
            if n < cfg.partial_min_words:
                best.flags.append(SHORT_QUOTE)
            cache[key] = best, n
        best, n = cache[key]
        quotes.append(_result(q, best, n, words, index, source))
    if any(not q.closed for q in found):
        warnings.append("some quotation marks are never closed (flag UNCLOSED)")
    if stray:
        warnings.append(f"{stray} closing quotation mark(s) without an opening one were ignored")
    return Report(quotes, skipped, stray, warnings, min_words)


def _count_words(text: str, numbers: bool) -> int:
    pieces = _read(text if numbers else clean_quote(text)).pieces
    return sum(len(s.norms) for s in _segments(pieces, numbers))


def _result(q: ExtractedQuote, o: _Outcome, n: int, words: _Words, index: SourceIndex, source: Source) -> QuoteResult:
    def chars(span):
        return (words.original(index.token_start[span[0]]), words.original(index.token_end[span[1] - 1], end=True))

    parts = []
    for text, label, sim, span in o.parts:
        s, e = chars(span) if span else (None, None)
        parts.append(QuotePart(text, label, sim, source.text[s:e] if span else "", s, e))
    located = [chars(s) for s in o.spans]
    start = min((s for s, _ in located), default=None)
    end = max((e for _, e in located), default=None)
    best_match = " … ".join(p.best_match for p in parts if p.best_match) if parts else (
        source.text[start:end] if located else "")
    flags = list(dict.fromkeys(o.flags + ([] if q.closed else [UNCLOSED])))
    return QuoteResult(q.text, o.label, o.similarity, best_match, start, end, q.start, q.end, q.kind, n, flags, parts)


def _check_language(language: str) -> None:
    if not isinstance(language, str) or not re.fullmatch(r"[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]+)*", language):
        raise ValueError(f"language must be a code such as 'en' or 'ru', not {language!r}")
