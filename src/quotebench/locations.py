"""Parse a model's stated location ("John 3:16", "Act III, Scene 1", "Chapter 4") and check it
against the source units a quote actually matched (SPEC §8, location check).

Each parser returns a dict of the fields it could read, or None if it could not read one.
A location is checked at the granularity the model gave: "John 3" is correct for any verse in
John 3; "Act 3" is correct for any scene of Act 3. ``granularity`` records how specific it was.
"""

from __future__ import annotations

import re

from .sources import BIBLE_BOOKS

ROMAN = re.compile(r"^[ivxlc]+$", re.I)
ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
    "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13,
    "fourteenth": 14, "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20, "twenty-first": 21, "twenty-second": 22,
    "twenty-third": 23, "twenty-fourth": 24, "twenty-fifth": 25, "twenty-sixth": 26,
    "twenty-seventh": 27,
}


def to_int(s: str) -> int | None:
    s = s.strip().rstrip(".").lower()
    if s.isdigit():
        return int(s)
    if ROMAN.match(s):
        vals = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}
        total, prev = 0, 0
        for ch in reversed(s):
            v = vals[ch]
            total = total - v if v < prev else total + v
            prev = max(prev, v)
        return total
    m = re.match(r"^(\d+)(st|nd|rd|th)$", s)
    if m:
        return int(m.group(1))
    return ORDINALS.get(s)


_NUM = r"(\d+|[ivxlcIVXLC]+)"

# ---------------------------------------------------------------------------------------
# Bible

_BOOK_ALIASES: dict[str, str] = {}


def _alias(code: str, *names: str) -> None:
    for n in names:
        _BOOK_ALIASES[re.sub(r"[^a-z0-9]", "", n.lower())] = code


for _code, _name in BIBLE_BOOKS:
    _alias(_code, _name, _code)
_alias("PSA", "Psalm", "Ps", "Psa", "Pss")
_alias("SNG", "Song of Songs", "Song", "Canticles", "Song of Sol")
_alias("REV", "Revelations", "Revelation of John", "Rev", "Apocalypse")
_alias("GEN", "Gen"); _alias("EXO", "Exod", "Ex"); _alias("LEV", "Lev"); _alias("NUM", "Num")
_alias("DEU", "Deut", "Dt"); _alias("JOS", "Josh"); _alias("JDG", "Judg", "Jdg")
_alias("PRO", "Prov", "Pr", "Prv"); _alias("ECC", "Eccl", "Eccles", "Qoheleth")
_alias("ISA", "Isa"); _alias("JER", "Jer"); _alias("LAM", "Lam"); _alias("EZK", "Ezek", "Eze")
_alias("DAN", "Dan"); _alias("HOS", "Hos"); _alias("OBA", "Obad"); _alias("MIC", "Mic")
_alias("HAB", "Hab"); _alias("ZEP", "Zeph"); _alias("ZEC", "Zech"); _alias("MAL", "Mal")
_alias("MAT", "Matt", "Mt"); _alias("MRK", "Mk", "Mar"); _alias("LUK", "Lk", "Luk")
_alias("JHN", "Jn", "Joh"); _alias("ACT", "Acts of the Apostles"); _alias("ROM", "Rom")
_alias("GAL", "Gal"); _alias("EPH", "Eph"); _alias("PHP", "Phil", "Php"); _alias("COL", "Col")
_alias("TIT", "Tit"); _alias("PHM", "Philem", "Phlm"); _alias("HEB", "Heb"); _alias("JAS", "Jas", "Jam")
for _n, _base in [("1", "Samuel"), ("2", "Samuel"), ("1", "Kings"), ("2", "Kings"), ("1", "Chronicles"),
                  ("2", "Chronicles"), ("1", "Corinthians"), ("2", "Corinthians"), ("1", "Thessalonians"),
                  ("2", "Thessalonians"), ("1", "Timothy"), ("2", "Timothy"), ("1", "Peter"), ("2", "Peter"),
                  ("1", "John"), ("2", "John"), ("3", "John")]:
    _c = dict((v, k) for k, v in BIBLE_BOOKS)[f"{_n} {_base}"]
    for _short in {_base, _base[:3], _base[:4], {"Corinthians": "Cor", "Thessalonians": "Thess", "Timothy": "Tim",
                                                   "Peter": "Pet", "Chronicles": "Chron", "Samuel": "Sam",
                                                   "Kings": "Kgs", "John": "Jn"}.get(_base, _base)}:
        _alias(_c, f"{_n} {_short}")

_BIBLE_REF = re.compile(
    r"^(?P<book>(?:[123]\s*)?[A-Za-z][A-Za-z .]*?)\s*(?P<ch>\d+)"
    r"(?:\s*[:.,]\s*(?P<v1>\d+)(?:\s*[-–]\s*(?P<v2>\d+))?)?"
)


def parse_bible(loc: str) -> dict | None:
    s = loc.strip()
    s = re.sub(r"\b(KJV|King James Version|The Gospel According to|Saint|St\.|The Book of|Book of|"
               r"The Epistle of Paul the Apostle to the|Epistle to the|Epistle of|The)\b", " ", s, flags=re.I)
    s = re.sub(r"\b(First|1st|I)\s+(?=[A-Z])", "1 ", s)
    s = re.sub(r"\b(Second|2nd|II)\s+(?=[A-Z])", "2 ", s)
    s = re.sub(r"\b(Third|3rd|III)\s+(?=[A-Z])", "3 ", s)
    # "Genesis chapter 1, verse 3" -> "Genesis 1:3"
    s = re.sub(r"\bchapter\s+(\d+)\s*,?\s*verses?\s+(\d+)", r"\1:\2", s, flags=re.I)
    s = re.sub(r"\bchapter\s+(\d+)", r"\1", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" ,;()")
    m = _BIBLE_REF.match(s)
    if not m:
        return None
    key = re.sub(r"[^a-z0-9]", "", m.group("book").lower())
    code = _BOOK_ALIASES.get(key)
    if code is None:
        return None
    out = {"book_code": code, "chapter": int(m.group("ch"))}
    if m.group("v1"):
        out["verse_start"] = int(m.group("v1"))
        out["verse_end"] = int(m.group("v2") or m.group("v1"))
    return out


def check_bible(loc: dict, unit: dict) -> bool:
    if unit["book_code"] != loc["book_code"] or unit["chapter"] != loc["chapter"]:
        return False
    if "verse_start" in loc:
        return loc["verse_start"] <= unit["verse"] <= loc["verse_end"]
    return True


# ---------------------------------------------------------------------------------------
# Shakespeare


def parse_play(loc: str) -> dict | None:
    s = loc.strip()
    out: dict = {}
    if re.search(r"\bprologue\b|\bchorus\b", s, re.I):
        act = re.search(r"\bact\s+" + _NUM, s, re.I)
        out = {"act": to_int(act.group(1)) if act else 1, "scene": 0}
        return out
    m = re.search(r"\bact\s*" + _NUM + r"\b", s, re.I)
    if m:
        out["act"] = to_int(m.group(1))
        sc = re.search(r"\b(?:scene|sc)\.?\s*" + _NUM + r"\b", s, re.I)
        if sc:
            out["scene"] = to_int(sc.group(1))
        return out if out["act"] else None
    m = re.search(r"\b" + _NUM + r"\s*[.,]\s*" + _NUM + r"\b", s)  # "3.1", "III.i", "3.1.56"
    if m and to_int(m.group(1)) and to_int(m.group(2)):
        return {"act": to_int(m.group(1)), "scene": to_int(m.group(2))}
    return None


def check_play(loc: dict, unit: dict) -> bool:
    if unit["act"] != loc["act"]:
        return False
    return "scene" not in loc or unit["scene"] == loc["scene"]


# ---------------------------------------------------------------------------------------
# US Constitution


def parse_constitution(loc: str) -> dict | None:
    s = loc.strip()
    if re.search(r"\bpreamble\b", s, re.I):
        return {"part": "preamble"}
    out: dict = {}
    m = re.search(r"\bamendment\s+" + _NUM + r"\b", s, re.I) or re.search(
        r"\b([A-Za-z-]+|\d+(?:st|nd|rd|th))\s+amendment\b", s, re.I
    )
    if m and to_int(m.group(1)):
        out = {"part": "amendment", "amendment": to_int(m.group(1))}
    else:
        m = re.search(r"\b(?:article|art)\.?\s*" + _NUM + r"\b", s, re.I)
        if not m or not to_int(m.group(1)):
            return None
        out = {"part": "article", "article": to_int(m.group(1))}
    sec = re.search(r"(?:\bsection|\bsec\.?|§)\s*" + _NUM + r"\b", s, re.I)
    if sec:
        out["section"] = to_int(sec.group(1))
    cl = re.search(r"\b(?:clause|cl)\.?\s*" + _NUM + r"\b", s, re.I)
    if cl:
        out["clause"] = to_int(cl.group(1))
    return out


def check_constitution(loc: dict, unit: dict) -> bool:
    if unit["part"] != loc["part"]:
        return False
    for key in ("article", "amendment", "section", "clause"):
        if key in loc and unit.get(key) != loc[key]:
            return False
    return True


# ---------------------------------------------------------------------------------------
# Prose (chapter level)

# Pride and Prejudice was first published in three volumes (23, 19 and 19 chapters); many
# editions still number chapters within volumes. Gutenberg #1342 numbers them 1–61.
_PP_VOLUME_OFFSET = {1: 0, 2: 23, 3: 42}


def parse_chapter(loc: str, text_id: str, chapter_titles: dict[int, str] | None = None) -> dict | None:
    s = loc.strip()
    if text_id == "origin_species" and re.search(r"\bintroduction\b", s, re.I):
        return {"chapter": 0}
    ch = re.search(r"\b(?:chapter|chap|ch)\.?\s*" + _NUM + r"\b", s, re.I)
    if ch and to_int(ch.group(1)) is not None:
        n = to_int(ch.group(1))
        vol = re.search(r"\b(?:volume|vol)\.?\s*" + _NUM + r"\b", s, re.I)
        if text_id == "pride_prejudice" and vol:
            v = to_int(vol.group(1))
            if v not in _PP_VOLUME_OFFSET:
                return {"chapter": -1}  # a volume the novel does not have
            n += _PP_VOLUME_OFFSET[v]
        return {"chapter": n}
    if chapter_titles:
        low = s.lower()
        for n, title in chapter_titles.items():
            if title and title.lower() in low:
                return {"chapter": n}
    return None


def check_chapter(loc: dict, unit: dict) -> bool:
    return unit["chapter"] == loc["chapter"]


# ---------------------------------------------------------------------------------------

PARSERS = {
    "bible_kjv": (lambda s, **kw: parse_bible(s), check_bible),
    "shakespeare": (lambda s, **kw: parse_play(s), check_play),
    "us_constitution": (lambda s, **kw: parse_constitution(s), check_constitution),
    "pride_prejudice": (lambda s, **kw: parse_chapter(s, "pride_prejudice", **kw), check_chapter),
    "origin_species": (lambda s, **kw: parse_chapter(s, "origin_species", **kw), check_chapter),
}


def parse_location(text_id: str, location: str, **kw) -> dict | None:
    if not location or not location.strip():
        return None
    return PARSERS[text_id][0](location, **kw)


def location_correct(text_id: str, location: str, matched_units: list[dict], **kw) -> bool | None:
    """True/False if the stated location could be read; None if missing or unreadable.

    Correct when every matched unit lies inside the stated location.
    """
    loc = parse_location(text_id, location, **kw)
    if loc is None or not matched_units:
        return None
    check = PARSERS[text_id][1]
    return all(check(loc, u) for u in matched_units)


def resolve(text_id: str, loc: dict, units: list[dict], play: str | None = None) -> list[int]:
    """Indices of the units a parsed location refers to ([] if it does not exist)."""
    check = PARSERS[text_id][1]
    return [u["idx"] for u in units if (play is None or u.get("play") == play) and check(loc, u)]


def parse_any(text_id: str, location: str) -> dict | None:
    """Parse a location for ``text_id`` with no extra context (used by lookup scoring)."""
    if not location or not location.strip():
        return None
    return PARSERS[text_id][0](location)
