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
    """Is ``unit`` inside the stated place?

    Articles V–VII and Amendments I–XII, XVI, XVII, XIX and XXVII are printed without section
    numbers; editions that number sections there number the paragraphs. "Section N" of such a
    text is therefore its Nth paragraph and nothing else: "Amendment XIX, Section 1" is its first
    paragraph, "Section 2" its second, and "Section 3" does not exist. Where the edition prints
    section numbers, the number must match.
    """
    if unit["part"] != loc["part"]:
        return False
    if "section" in loc and unit.get("section") is None:
        paragraph, inside = loc["section"], loc.get("clause", 1)
        loc = {k: v for k, v in loc.items() if k != "section"} | {"clause": paragraph if inside == 1 else None}
    return all(unit.get(key) == loc[key] for key in ("article", "amendment", "section", "clause") if key in loc)


# ---------------------------------------------------------------------------------------
# Prose (chapter level)

# Pride and Prejudice was first published in three volumes (23, 19 and 19 chapters); many
# editions still number chapters within volumes. Gutenberg #1342 numbers them 1–61.
_PP_VOLUMES = {1: (0, 23), 2: (23, 19), 3: (42, 19)}  # volume: (chapters before it, its chapters)
_CHAPTER = re.compile(r"\b(?:chapter|chap|ch)\.?\s*" + _NUM + r"\b", re.I)
_VOLUME = re.compile(r"\b(?:volume|vol)\.?\s*" + _NUM + r"\b", re.I)
NO_SUCH_CHAPTER = -1  # a chapter the novel does not have, or numbers that contradict each other


def _volume_chapter(volumes: set, chapters: set[int]) -> int:
    """The continuous chapter number (1–61) meant by a location that also names a volume.

    "Volume III, Chapter 14", "Chapter 14 (Volume III)", "Chapter 56 (Volume III)" and
    "Chapter 56 (Volume III, Chapter 14)" all mean chapter 56. If the numbers cannot all be
    true of one chapter ("Chapter 50 (Volume III, Chapter 14)"), they mean no chapter.
    """
    if len(volumes) != 1 or not volumes <= _PP_VOLUMES.keys():
        return NO_SUCH_CHAPTER
    before, length = _PP_VOLUMES[min(volumes)]
    meant = [n for n in range(before + 1, before + length + 1) if chapters <= {n, n - before}]
    return meant[0] if meant else NO_SUCH_CHAPTER  # never more than one


def parse_chapter(loc: str, text_id: str, chapter_titles: dict[int, str] | None = None) -> dict | None:
    s = loc.strip()
    if text_id == "origin_species" and re.search(r"\bintroduction\b", s, re.I):
        return {"chapter": 0}
    chapters = [n for m in _CHAPTER.finditer(s) if (n := to_int(m.group(1))) is not None]
    if chapters:
        volumes = {to_int(m.group(1)) for m in _VOLUME.finditer(s)}
        if text_id == "pride_prejudice" and volumes:
            return {"chapter": _volume_chapter(volumes, set(chapters))}
        return {"chapter": chapters[0]}
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


# ---------------------------------------------------------------------------------------
# Trick questions: does the answer itself say that the line is not from the named text?

# How a model may name the text (or play) the question asked about.
_NAMED_TEXT = {
    "bible_kjv": r"(?:King James(?: Version| Bible)?|KJV|Holy Bible|Bible)",
    "us_constitution": r"(?:(?:U\.\s?S\.|US|United States) )?Constitution",
    "pride_prejudice": r"Pride (?:and|&) Prejudice",
    "origin_species": r"(?:On )?(?:T|t)he Origin of Species|Origin of Species",
}
# Other works a line may really come from: all plays of Shakespeare, the novels of Jane Austen, the
# best-known American documents and the other books of Darwin. Matched with their capitals.
_OTHER_WORKS = r"""
All's Well That Ends Well|Antony and Cleopatra|As You Like It|Comedy of Errors|Coriolanus|Cymbeline|Hamlet|
(?:1|2) Henry IV|Henry (?:VIII|VI|V|IV)|Julius Caesar|King John|King Lear|Love's Labou?r's Lost|Macbeth|
Measure for Measure|Merchant of Venice|Merry Wives of Windsor|Midsummer Night's Dream|Much Ado About Nothing|
Othello|Pericles|Richard (?:III|II)|Romeo and Juliet|Taming of the Shrew|Tempest|Timon of Athens|
Titus Andronicus|Troilus and Cressida|Twelfth Night|Two Gentlemen of Verona|Two Noble Kinsmen|Winter's Tale|
Emma|Lady Susan|Mansfield Park|Northanger Abbey|Persuasion|Pride and Prejudice|Sanditon|Sense and Sensibility|
Articles of Confederation|Common Sense|Declaration of Independence|Declaration of the Rights of Man|
Emancipation Proclamation|Federalist Papers|Federalist No\.|Gettysburg Address|Mayflower Compact|
Northwest Ordinance|Pledge of Allegiance|Star-Spangled Banner|Constitution|
Descent of Man|Expression of the Emotions|Variation of Animals and Plants|Voyage of the Beagle|
Origin of Species|Principles of Biology"""
_OTHER_WORKS = _OTHER_WORKS.replace("\n", "")
_AUTHOR = r"(?:(?:William |Jane |Charles )?(?:Shakespeare|Austen|Darwin|Lincoln|Jefferson|Spencer)'s )?"
# "not in", "not from", "does not appear in", "isn't found in" … the named text
_DENIED_IN = (r"(?:\bnot|n't)\s+(?:(?:actually|a|line|quote|quotation|passage|part|found|appear|appears|occur|"
              r"occurs|present|contained)\s+)*(?:in|from|of)\s+(?:the\s+(?:text\s+of\s+)?)?")


def says_other_source(text_id: str, play: str | None, location: str, quote: str = "") -> bool:
    """True if an answer to a trick question says itself that its quote is not from the named text.

    Read from the stated location, and from remarks in brackets inside the quote. Three forms:

    1. it denies the named text: "Not in Macbeth", "does not appear in Hamlet";
    2. it names another work and says "not <named text>": "Hamlet, Act 3 (not Macbeth)";
    3. it begins with the title of another work and does not mention the named text at all:
       "Twelfth Night, Act 1, Scene 1".

    Anything less plain does not count. A different place in the named text does not count ("Article
    IV, Section 2" for Article V, Section 2), and neither does "spoken by Horatio, not Hamlet".
    """
    named = rf"(?:{re.escape(play) if play else _NAMED_TEXT[text_id]})\b(?!'s)"
    other = rf"\b(?!{named})(?:{_OTHER_WORKS})(?!\w|'s)"
    location, quote = (re.sub(r"\s+", " ", x.replace("’", "'")).strip() for x in (location, quote))
    for text in (location, *re.findall(r"[\[(]([^\])]*)[\])]", quote)):
        if re.search(rf"(?i:{_DENIED_IN}){_AUTHOR}{named}", text):
            return True
        if re.search(rf"(?i:\bnot (?:the )?){_AUTHOR}{named}", text) and re.search(other, text):
            return True
    title = rf"(?:From )?{_AUTHOR}(?:The |the |A )?(?:King )?{other}(?=\s*(?:[,.;:(—–-]|$))"
    return bool(re.match(title, location)) and not re.search(rf"\b{named}", location)
