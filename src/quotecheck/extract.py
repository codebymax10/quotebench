"""Find the quotations in a text (an AI answer). Knows nothing about sources or scoring.

Recognised: straight quotes "..." and '...', curly quotes “...” and ‘...’, low-high quotes
„...“, guillemets «...» (and reversed »...«), and Markdown block quotes (lines starting with >).
Only the outermost pair of marks counts: a quote inside a quote is part of the outer one.

The scanner is a single left-to-right pass with a stack, so its cost is linear in the text.
"""

from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedQuote:
    text: str  # the quoted words, without the outer marks (block quotes: without the ">")
    start: int  # position in the scanned text; text[start:end] == .text except in block quotes
    end: int
    kind: str  # straight | curly | guillemet | single | block
    closed: bool = True  # False: the closing mark is missing, the quote runs to the paragraph end
    without_attribution: str | None = None  # block quotes: the text minus a final "— Author" line


# How far a quote may run over paragraph breaks before its opening mark counts as a stray one.
MAX_SPAN = 20_000
MAX_DEPTH = 32  # nesting deeper than this is unbalanced text, not quotation

_STRAIGHT = '"＂'
_KIND = {'"': "straight", "＂": "straight", "“": "curly", "”": "curly", "„": "curly", "«": "guillemet", "»": "guillemet"}
_FAMILY_MARKS = {"straight": _STRAIGHT, "curly": "“”„", "guillemet": "«»"}
_MARK = re.compile(r'\\?"|[＂“”„«»]')
_HTML_TAG = re.compile(r"</?[A-Za-z][^<>]{0,500}>")
_OPEN_BRACKETS = "([{"
_CLOSE_PUNCT = ".,;:!?…)]}"

_BLANK = re.compile(r"[ \t]*$")
_FENCE = re.compile(r"[ \t]*(?:```|~~~)")
_BLOCK_LINE = re.compile(r"[ \t]*(?:(?:[-*+]|\d{1,3}[.)])[ \t]+)?(?:>[ \t]?)+")
_NEW_ITEM = re.compile(r"[ \t]*(?:[-*+][ \t]|\d{1,3}[.)][ \t]|#{1,6}[ \t]|\|)")
_ADMONITION = re.compile(r"\s*\[!\w+\]")

# What may follow or end a block quote without being part of it: "— Jane Austen", "(Section 4)".
_ATTRIBUTION_TAIL = re.compile(r"[\s*_.,;]*(?:(?:[—–]|--?)\s*[^\n]{1,120}|\([^()\n]{1,120}\)\.?|\[[^\[\]\n]{1,120}\]\.?)?[\s*_]*")
_ATTRIBUTION_LINE = re.compile(r"\n\s*[*_]*(?:—|–|--?)\s*(?=\S)([^\n]{1,120})$")

# Words that start with an apostrophe, not with an opening quote.
_ELISION = re.compile(r"(?:t(?:is|was|were|will|would|ween|il|ill)|em|cause|bout|round|n|gainst|neath|d|\d\ds?)(?!\w)", re.I)


@dataclass
class _Open:
    pos: int
    mark: str
    para_end: int

    @property
    def kind(self) -> str:
        return _KIND[self.mark]


def extract_quotes(text: str) -> tuple[list[ExtractedQuote], int]:
    """(quotes in order of appearance, number of stray closing marks that were ignored)."""
    blocks, paragraphs = _layout(text)
    inline, stray = _inline_quotes(text, paragraphs)
    quotes = inline + blocks
    quotes.sort(key=lambda q: q.start)
    return quotes, stray


# --------------------------------------------------------------------------------------
# Layout: Markdown block quotes, and the paragraphs of everything else


@dataclass
class _Para:
    start: int
    end: int
    after_blank: bool  # separated from the previous paragraph by blank lines only


def _layout(text: str) -> tuple[list[ExtractedQuote], list[list[_Para]]]:
    """Block quotes, and the rest of the text as runs of paragraphs between block quotes."""
    blocks: list[ExtractedQuote] = []
    runs: list[list[_Para]] = [[]]
    block: list[tuple[int, int]] = []  # (content start, content end) of the lines of one block quote
    para: _Para | None = None
    blank_before, in_fence = False, False

    def end_block() -> None:
        nonlocal block
        if block:
            first_line = text[block[0][0] : block[0][1]]
            if _ADMONITION.match(first_line):  # "> [!NOTE]": a call-out box, not a quotation
                runs.append([_Para(s, e, i > 0) for i, (s, e) in enumerate(block)])
                runs.append([])
            else:
                blocks.extend(_block_quotes(text, block))
                runs.append([])
        block = []

    def end_para() -> None:
        nonlocal para
        if para is not None:
            runs[-1].append(para)
        para = None

    pos = 0
    for line in text.splitlines(keepends=True):
        start, pos = pos, pos + len(line)
        end = start + len(line.rstrip("\r\n\v\f\x1c\x1d\x1e\x85  "))
        body = text[start:end]
        if _FENCE.match(body):
            in_fence = not in_fence
            end_block()
            end_para()
            blank_before = False
            continue
        m = None if in_fence else _BLOCK_LINE.match(body)
        if m:
            end_para()
            # A list marker in front of ">" starts a new block quote.
            if block and not body.lstrip().startswith(">"):
                end_block()
            block.append((start + m.end(), end))
            blank_before = False
            continue
        end_block()
        if _BLANK.match(body):
            end_para()
            blank_before = True
            continue
        if para is not None and _NEW_ITEM.match(body):
            end_para()
            blank_before = False
        if para is None:
            para = _Para(start, end, blank_before)
        else:
            para.end = end
        blank_before = False
    end_block()
    end_para()
    return blocks, [r for r in runs if r]


def _block_quotes(text: str, lines: list[tuple[int, int]]) -> list[ExtractedQuote]:
    """One block quote as one quotation, or as several if every paragraph has its own marks."""
    paras: list[list[tuple[int, int]]] = [[]]
    for s, e in lines:
        if text[s:e].strip():
            paras[-1].append((s, e))
        elif paras[-1]:
            paras.append([])
    paras = [p for p in paras if p]
    if not paras:
        return []
    if len(paras) > 1:
        wrapped = [_block_quote(text, p) for p in paras]
        if all(q.kind != "block" for q in wrapped):
            return wrapped
        # "> quote" + empty ">" + "> — Author": the last paragraph may be only the attribution.
        last = " ".join(text[s:e] for s, e in paras[-1])
        if all(q.kind != "block" for q in wrapped[:-1]) and _ATTRIBUTION_LINE.fullmatch("\n" + last):
            return wrapped[:-1]
    return [_block_quote(text, [ln for p in paras for ln in p])]


def _block_quote(text: str, lines: list[tuple[int, int]]) -> ExtractedQuote:
    start, end = lines[0][0], lines[-1][1]
    body = "\n".join(text[s:e] for s, e in lines).strip()
    inner, _ = _inline_quotes(body, [[_Para(0, len(body), False)]])
    # Entirely inside quotation marks (perhaps followed by an attribution): those are the quote.
    if inner and not body[: inner[0].start - 1].strip(" \t*_") and inner[0].closed:
        q = inner[0]
        if _ATTRIBUTION_TAIL.fullmatch(body, q.end + 1):
            return ExtractedQuote(q.text, start, end, q.kind)
    m = _ATTRIBUTION_LINE.search(body)
    without = None
    if m and not re.search(r"[.!?…][\"'”’»*_]*\s*$", m.group(1)) and len(m.group(1).split()) <= 12:
        without = body[: m.start()].strip() or None
    return ExtractedQuote(body, start, end, "block", True, without)


# --------------------------------------------------------------------------------------
# Inline quotation marks


def _context(text: str, start: int, end: int) -> tuple[bool, bool]:
    """(can only be an opening mark, can only be a closing mark) judged by its neighbours."""
    prev = text[start - 1] if start > 0 else " "
    nxt = text[end] if end < len(text) else " "
    before = prev.isspace() or prev in _OPEN_BRACKETS
    after = nxt.isspace() or nxt in _CLOSE_PUNCT
    return before and not after, after and not before


def _inline_quotes(text: str, runs: list[list[_Para]]) -> tuple[list[ExtractedQuote], int]:
    tags = [(m.start(), m.end()) for m in _HTML_TAG.finditer(text)]
    tag_starts = [s for s, _ in tags]

    def in_tag(i: int) -> bool:
        k = bisect_right(tag_starts, i) - 1
        return k >= 0 and i < tags[k][1]

    marks = [m for m in _MARK.finditer(text) if not in_tag(m.start())]
    mark_pos = [m.start() for m in marks]
    family_pos = {
        fam: [m.start() for m in marks if len(m.group()) == 1 and m.group() in chars]
        for fam, chars in _FAMILY_MARKS.items()
    }
    spans: list[tuple[int, int, str, bool]] = []  # (start, end, kind, closed), marks excluded
    stray = 0
    for run in runs:
        pairs, unclosed, n = _scan_run(text, run, marks, mark_pos, family_pos)
        stray += n
        top = _outermost(pairs)
        singles = [s for p in run for s in _single_quotes(text, p, top)]
        top = _outermost(top + singles)
        starts = [s for s, _, _ in top]
        spans += [(s, e, kind, True) for s, e, kind in top]
        for o in unclosed:
            k = bisect_right(starts, o.pos) - 1
            if k >= 0 and o.pos < top[k][1]:
                continue  # inside a complete quote
            end = o.para_end
            if k + 1 < len(top):
                end = min(end, top[k + 1][0] - 1)  # stop before the next quote's opening mark
            body = text[o.pos + 1 : end].rstrip()
            spans.append((o.pos + 1, o.pos + 1 + len(body), o.kind, False))
    # Two unclosed marks in one paragraph: the first one stops at the second.
    spans.sort()
    out = []
    for i, (s, e, kind, closed) in enumerate(spans):
        if not closed and i + 1 < len(spans):
            e = max(s, min(e, spans[i + 1][0] - 1))
        out.append(ExtractedQuote(text[s:e], s, e, kind, closed))
    return out, stray


def _outermost(pairs: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    for p in sorted(pairs, key=lambda p: (p[0], -p[1])):
        if not out or p[0] >= out[-1][1]:
            out.append(p)
    return out


def _scan_run(text, run, marks, mark_pos, family_pos):
    """Match double quotation marks and guillemets in one run of paragraphs."""
    pairs: list[tuple[int, int, str]] = []
    unclosed: list[_Open] = []
    stray = 0
    stack: list[_Open] = []
    escaped: int | None = None  # position of an open \" pair

    def find(chars: str) -> int | None:
        for k in range(len(stack) - 1, -1, -1):
            if stack[k].mark in chars:
                return k
        return None

    def push(i: int, mark: str) -> None:
        stack.append(_Open(i, mark, para.end))
        if len(stack) > MAX_DEPTH:
            unclosed.append(stack.pop(0))

    def close(k: int, i: int) -> None:
        o = stack[k]
        pairs.append((o.pos + 1, i, o.kind))
        del stack[k:]

    for pi, para in enumerate(run):
        escaped = None
        skip_at = -1
        if stack:  # a quote carried over from the previous paragraph
            first = _first_mark(text, para)
            if first is not None and text[first] in _FAMILY_MARKS[stack[0].kind]:
                skip_at = first if _context(text, first, first + 1)[0] else -1
        lo, hi = bisect_left(mark_pos, para.start), bisect_left(mark_pos, para.end)
        later_close = _last_index(marks, lo, hi, "”")
        for m in marks[lo:hi]:
            i, tok = m.start(), m.group()
            if i == skip_at:
                continue  # repeated opening mark of a multi-paragraph quote
            if len(tok) == 2:  # \" : a pair of its own, but plain text inside a "..." quote
                if find(_STRAIGHT) is not None:
                    continue
                if escaped is None:
                    escaped = i + 1
                else:
                    pairs.append((escaped + 1, i, "straight"))
                    escaped = None
                continue
            open_only, close_only = _context(text, i, i + 1)
            if tok in _STRAIGHT:
                k = find(_STRAIGHT)
                if open_only or (k is None and not close_only):
                    push(i, tok)
                elif k is not None:
                    close(k, i)
                else:
                    k = find("“„”")
                    inch = i > 0 and text[i - 1].isdigit()
                    if k is not None and later_close < i:
                        close(k, i)  # “mixed marks"
                    elif not inch:
                        stray += 1
            elif tok == "“":
                k = find("„")
                if k is None and close_only:
                    k = find("“")  # “both marks alike“
                if k is not None and not open_only:
                    close(k, i)
                else:
                    push(i, tok)
            elif tok == "”":
                k = find("“„")
                if k is None and not open_only:
                    k = find("”")
                if k is None and not open_only and close_only:
                    k = find(_STRAIGHT)
                if k is not None:
                    close(k, i)
                elif open_only:
                    push(i, tok)  # ”both marks alike”
                else:
                    stray += 1
            elif tok == "„":
                push(i, tok)
            elif tok == "«":
                k = find("»")
                if k is not None and not open_only:
                    close(k, i)
                else:
                    push(i, tok)
            else:  # »
                k = find("«")
                if k is not None:
                    close(k, i)
                elif open_only:
                    push(i, tok)
                else:
                    stray += 1
        # Which open quote, if any, goes on in the next paragraph?
        while stack:
            if pi + 1 < len(run) and _carries(text, stack[0], run[pi + 1], para.end, run[-1].end, family_pos):
                del stack[1:]
                break
            unclosed.append(stack.pop(0))
    return pairs, unclosed, stray


def _last_index(marks, lo: int, hi: int, ch: str) -> int:
    for k in range(hi - 1, lo - 1, -1):
        if marks[k].group() == ch:
            return marks[k].start()
    return -1


def _first_mark(text: str, para: _Para) -> int | None:
    i = para.start
    while i < para.end and (text[i].isspace() or text[i] in "*_"):
        i += 1
    return i if i < para.end else None


def _carries(text: str, o: _Open, nxt: _Para, here: int, limit: int, family_pos) -> bool:
    """Does the open quote ``o`` continue in the next paragraph?

    Yes if that paragraph repeats the opening mark (the usual typography), or if the next mark
    of the same kind can only be a closing one.
    """
    if nxt.start - o.pos > MAX_SPAN:
        return False
    first = _first_mark(text, nxt)
    if nxt.after_blank and first is not None and text[first] == o.mark and _context(text, first, first + 1)[0]:
        return True
    pos = family_pos[o.kind]
    k = bisect_left(pos, here)
    limit = min(limit, o.pos + MAX_SPAN)
    while k < len(pos) and pos[k] < limit:
        i = pos[k]
        open_only, close_only = _context(text, i, i + 1)
        if close_only and o.kind == "straight" and text[i - 1].isdigit():
            k += 1  # probably inches (6")
            continue
        if o.kind == "straight":
            return close_only
        closers = {"“": "”", "„": "“”", "”": "”", "«": "»", "»": "«"}[o.mark]
        return text[i] in closers and not open_only
    return False


# --- single quotation marks: much weaker evidence, because the same characters are apostrophes


_SINGLE = re.compile(r"['‘’]")


def _single_quotes(text: str, para: _Para, doubles: list[tuple[int, int, str]]):
    """'...' and ‘...’ pairs inside one paragraph, outside double quotation marks."""
    starts = [s for s, _, _ in doubles]

    def inside(i: int) -> bool:
        k = bisect_right(starts, i) - 1
        return k >= 0 and i < doubles[k][1]

    events = []  # (position, "open" | "close" | "maybe")
    for m in _SINGLE.finditer(text, para.start, para.end):
        i, ch = m.start(), m.group()
        if inside(i):
            continue
        prev = text[i - 1] if i > 0 else " "
        nxt = text[i + 1] if i + 1 < len(text) else " "
        if ch != "’" and not prev.isalnum() and not nxt.isspace() and not _ELISION.match(text, i + 1):
            if prev.isspace() or prev in _OPEN_BRACKETS or prev in "*_—–-:" or ch == "‘":
                events.append((i, "open", ch))
                continue
        if ch != "‘" and not prev.isspace() and not nxt.isalnum():
            # "the tenants' rights": may be a possessive rather than the end of the quote
            possessive = prev in "sSzZxX" and nxt == " " and text[i + 2 : i + 3].islower()
            events.append((i, "maybe" if possessive else "close", ch))
    out = []
    k = 0
    while k < len(events):
        i, what, ch = events[k]
        k += 1
        if what != "open":
            continue
        end, j = None, k
        while j < len(events) and events[j][1] != "open":
            if ch == "'" and events[j][2] == "’":
                j += 1  # a curly apostrophe does not close a straight quote
                continue
            end = j
            if events[j][1] == "close":
                break
            j += 1
        if end is not None:
            out.append((i + 1, events[end][0], "single"))
            k = end + 1
    return out
