"""Parse a model's stated location ("John 3:16", "Act III, Scene 1", "Chapter 4") and check it
against the source units a quote actually matched (SPEC §8, location check).

Each parser returns a dict of the fields it could read, or None if it could not read one.
A location is checked at the granularity the model gave: "John 3" is correct for any verse in
John 3; "Act 3" is correct for any scene of Act 3. ``granularity`` records how specific it was.
"""

from __future__ import annotations

import re
from functools import lru_cache

from .sources import BIBLE_BOOKS

ROMAN = re.compile(r"^[ivxlc]+$", re.I)
ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
    "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13,
    "fourteenth": 14, "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20, "twenty-first": 21, "twenty-second": 22,
    "twenty-third": 23, "twenty-fourth": 24, "twenty-fifth": 25, "twenty-sixth": 26,
    "twenty-seventh": 27, "twenty-eighth": 28, "twenty-ninth": 29, "thirtieth": 30,
}
_ONES = ("one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
         "eighteen nineteen").split()
NUMBER_WORDS = {w: n for n, w in enumerate(_ONES, 1)}
for _t, _tens in enumerate("twenty thirty forty fifty sixty".split(), 2):
    NUMBER_WORDS[_tens] = 10 * _t
    NUMBER_WORDS |= {f"{_tens}{sep}{w}": 10 * _t + n for n, w in enumerate(_ONES[:9], 1) for sep in "- "}


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
    return ORDINALS.get(s) or NUMBER_WORDS.get(re.sub(r"\s+", " ", s))


_NUM = r"(\d+|[ivxlcIVXLC]+)"
_WORDS = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
_NUM_OR_WORD = rf"(\d+|[ivxlcIVXLC]+|{_WORDS})"

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

_DASH = r"(?:[-‐‑‒–—−]|\bto\b|\bthrough\b)"
_BIBLE_REF = re.compile(
    r"^(?P<book>(?:[123]\s*)?[A-Za-z][A-Za-z .]*?)\s*(?P<ch>\d+)"
    rf"(?:\s*[:.,]\s*(?P<v1>\d+)(?:\s*{_DASH}\s*(?:(?P<ch2>\d+)\s*[:.]\s*)?(?P<v2>\d+))?"
    rf"|\s*{_DASH}\s*(?P<ch_to>\d+)(?:\s*[:.]\s*(?P<v_to>\d+))?(?!\d))?"
)
# ", 6" / "and 6" / ", 8-9" after a verse: more verses of the same chapter, not another reference
# (", 4:2", ", 2 Corinthians 1:3")
_MORE_VERSES = re.compile(rf"\s*(?:,\s*and\b|[,;&]|\band\b)\s*(\d{{1,3}})\b(?!\s*[:.]\s*\d)(?!\s*[A-Za-z]+\.?\s*\d)"
                          rf"(?:\s*{_DASH}\s*(\d{{1,3}})\b(?!\s*[:.]\s*\d))?")


@lru_cache(maxsize=1)
def _verse_counts() -> dict[tuple[str, int], int]:
    """{(book code, chapter): its number of verses}, from the parsed King James Bible."""
    from .sources import load_units

    out: dict[tuple[str, int], int] = {}
    for u in load_units("bible_kjv"):
        out[u["book_code"], u["chapter"]] = max(u["verse"], out.get((u["book_code"], u["chapter"]), 0))
    return out


ONE_CHAPTER_BOOKS = {"OBA", "PHM", "2JN", "3JN", "JUD"}


def parse_bible(loc: str) -> dict | None:
    """``book_code`` and ``chapter``, with ``verse_start`` and ``verse_end`` if verses are given.

    ``chapter_end`` is set when a range ends in another chapter ("John 3:16-4:2", "John 3-4");
    ``more`` holds further verses of the chapter ("3:5, 7-8"). A lone number after a book that has
    one chapter is a verse ("Jude 3"), except 1, which is read as the chapter ("Jude 1").
    """
    s = loc.strip()
    s = re.sub(r"\b(KJV|King James Version|The Gospel According to|Saint|St\.|The Book of|Book of|"
               r"The Epistle of Paul the Apostle to the|Epistle to the|Epistle of|The)\b", " ", s, flags=re.I)
    s = re.sub(r"\b(First|1st|I)\s+(?=[A-Z])", "1 ", s)
    s = re.sub(r"\b(Second|2nd|II)\s+(?=[A-Z])", "2 ", s)
    s = re.sub(r"\b(Third|3rd|III)\s+(?=[A-Z])", "3 ", s)
    # "Genesis chapter 1, verse 3" -> "Genesis 1:3"
    s = re.sub(r"\bchapter\s+(\d+)\s*,?\s*verses?\s+(\d+)", r"\1:\2", s, flags=re.I)
    s = re.sub(r"\bchapter\s+(\d+)", r"\1", s, flags=re.I)
    s = re.sub(r"(?<=[A-Za-z]),?\s+(?:verses?|vv?\.)\s*(?=\d)", " ", s, flags=re.I)  # "Jude verse 3"
    s = re.sub(r"\s+", " ", s).strip(" ,;()")
    m = _BIBLE_REF.match(s)
    if not m:
        return None
    key = re.sub(r"[^a-z0-9]", "", m.group("book").lower())
    code = _BOOK_ALIASES.get(key)
    if code is None:
        return None
    ch, v1 = int(m.group("ch")), m.group("v1")
    out = {"book_code": code, "chapter": ch}
    if code in ONE_CHAPTER_BOOKS and v1 is None and (ch != 1 or m.group("ch_to")) and not m.group("v_to"):
        out = {"book_code": code, "chapter": 1, "verse_start": ch, "verse_end": int(m.group("ch_to") or ch)}
        v1 = str(ch)
    elif v1:
        out |= {"verse_start": int(v1), "verse_end": int(m.group("v2") or v1)}
        if m.group("ch2"):
            out["chapter_end"] = int(m.group("ch2"))
    elif m.group("ch_to"):
        out["chapter_end"] = int(m.group("ch_to"))
        if m.group("v_to"):
            out |= {"verse_start": 1, "verse_end": int(m.group("v_to"))}
    at, more = m.end(), []
    while v1 and (x := _MORE_VERSES.match(s, at)):
        more.append((int(x[1]), int(x[2] or x[1])))
        at = x.end()
    return out | ({"more": more} if more else {})


def _bible_ranges(loc: dict) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """The stated place as [(first (chapter, verse), last (chapter, verse)), ...]."""
    ch, ch_end = loc["chapter"], loc.get("chapter_end", loc["chapter"])
    last_verse = loc["verse_end"] if "verse_end" in loc else _verse_counts().get((loc["book_code"], ch_end), 0)
    ranges = [((ch, loc.get("verse_start", 1)), (ch_end, last_verse))]
    return ranges + [((ch, a), (ch, b)) for a, b in loc.get("more", [])]


def bible_place_exists(loc: dict) -> bool:
    """Do all the stated verses exist, in order? "John 3:1-36" does, however long; "John 3:1-999"
    and "John 3:30-40" do not (the chapter has 36 verses), and neither does "John 3:17-16"."""
    counts = _verse_counts()
    return all(start <= end and all(1 <= v <= counts.get((loc["book_code"], c), 0) for c, v in (start, end))
               for start, end in _bible_ranges(loc))


def check_bible(loc: dict, unit: dict) -> bool:
    """Is the verse inside the stated place? Never, if a part of that place does not exist."""
    if unit["book_code"] != loc["book_code"] or not bible_place_exists(loc):
        return False
    return any(start <= (unit["chapter"], unit["verse"]) <= end for start, end in _bible_ranges(loc))


# ---------------------------------------------------------------------------------------
# Shakespeare


def parse_play(loc: str) -> dict | None:
    s = re.sub(r"\bnot\s+(?:(?:in|from|of)\s+)?(?:the\s+)?(?:prologue|chorus)\b", " ", loc.strip(), flags=re.I)
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
    # the amendments are themselves headed "Article": "Article XIV of the Amendments"
    m = re.search(r"\barticle\s+" + _NUM + r"(?:,?\s+(?:section|sec\.)\s*\w+)?\s*,?\s+(?:of|in)\s+(?:the\s+)?amendments\b", s, re.I) or re.search(
        r"\bamendment\s+" + _NUM + r"\b", s, re.I) or re.search(
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
_CHAPTER = re.compile(r"\b(?:chapter|chap|ch)\.?\s*" + _NUM_OR_WORD + r"\b", re.I)
_VOLUME = re.compile(r"\b(?:volume|vol)\.?\s*(?:the\s+)?(?:" + _NUM_OR_WORD + r"|(first|second|third))\b"
                     r"|\b(first|second|third|fourth|1st|2nd|3rd|4th)\s+volume\b", re.I)
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
        volumes = {to_int(m[1] or m[2] or m[3]) for m in _VOLUME.finditer(s)}
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
# Trick questions: does the answer itself say that the line is not from the named text, or that the
# passage asked for does not exist? Word rules; they never change whether an answer is right.

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
_DENIED = (r"(?:\bnot|n't)\s+(?:(?:actually|a|line|quote|quotation|passage|verse|phrase|part|found|appear|appears|occur|"
           r"occurs|present|contained|included|anywhere|verbatim|word-for-word|exactly)\s+)*")
_THE = (r"(?:the\s+(?:(?:original\s+)?(?:text|(?:\d{4}\s+)?first\s+edition(?:\s+\(\d{4}\))?|Project\s+Gutenberg\s+(?:edition|text))"
        r"\s+of\s+(?:the\s+)?|original\s+)?)?")
_PLAY = r"(?:the\s+(?:play|tragedy)\s+(?:of\s+)?)"  # makes it plain that the play is meant, not the character


def _named(text_id: str, play: str | None) -> str:
    """Regex: the text or play asked about. "Hamlet's" and "Macbeth himself" are the character."""
    name = re.escape(play) if play else _NAMED_TEXT[text_id]
    return rf"(?:{name})\b(?!'s|\s+(?:him|her)self|,?\s+the\s+(?:character|man|prince|king)\b)"


def _other(text_id: str, play: str | None) -> str:
    return rf"\b(?!{_named(text_id, play)})(?:{_OTHER_WORKS})(?!\w|'s)"


def _plain(text: str) -> str:
    """One line, straight quotes, no Markdown marks, "U.S." without its points."""
    text = re.sub(r"[*_`]", "", text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"'))
    return re.sub(r"\s+", " ", re.sub(r"\bU\.\s?S\.", "US", text)).strip()


def _brackets(quote: str) -> list[str]:
    return re.findall(r"[\[(]([^\])]*)[\])]", quote)


def _denies_named_text(text_id: str, play: str | None, text: str) -> bool:
    """Forms 1 and 2 of ``says_other_source``, in one remark."""
    named, other = _named(text_id, play), _other(text_id, play)
    text = text.replace('"', "")
    if re.search(rf"(?i:{_DENIED}in\s+(?:{_PLAY}|{_THE})){_AUTHOR}{named}", text) or re.search(
            rf"(?i:{_DENIED}(?:from|of)\s+{_PLAY}){_AUTHOR}{named}", text):
        return True
    denied_from = rf"(?i:{_DENIED}(?:from|of)\s+{_THE}){_AUTHOR}{named}"
    elsewhere = bool(re.search(other, text))
    if play and " " not in play:  # the title is also a character: "words from Polonius, not from Hamlet"
        if re.fullmatch(rf"(?i:(?:(?:this|the) (?:line|quote|quotation|passage|text) is )?not from ){_AUTHOR}{named}\W*", text):
            return True
        if elsewhere and re.search(denied_from, text):
            return True
    elif re.search(denied_from, text):
        return True
    return elsewhere and bool(re.search(rf"(?i:\bnot (?:the )?){_AUTHOR}{named}", text))


def says_other_source(text_id: str, play: str | None, location: str, quote: str = "") -> bool:
    """True if an answer to a trick question says itself that its quote is not from the named text.

    Read from the stated location, and from remarks in brackets inside the quote. Three forms:

    1. it denies the named text: "Not in Macbeth", "does not appear in Hamlet", "this line is from
       Anna Karenina, not from Pride and Prejudice";
    2. it names another work and says "not <named text>": "Hamlet, Act 3 (not Macbeth)";
    3. it begins with the title of another work and does not mention the named text at all:
       "Twelfth Night, Act 1, Scene 1".

    Anything less plain does not count. A different place in the named text does not count ("Article
    IV, Section 2" for Article V, Section 2), and neither does "spoken by Horatio, not Hamlet". Where
    the play is named after a character, "not from Hamlet" and "not a line of Hamlet" may mean the
    character, so they count only if another work is named too, the play is called a play, or the
    location says nothing else.
    """
    location = _plain(location)
    if any(_denies_named_text(text_id, play, x) or _says_not_in_text(text_id, play, x)
           for x in (location, *map(_plain, _brackets(quote)))):
        return True
    title = rf"(?:From )?{_AUTHOR}(?:The |the |A )?(?:King )?{_other(text_id, play)}(?=\s*(?:[,.;:(—–-]|$))"
    return bool(re.match(title, location)) and not re.search(rf"\b{_named(text_id, play)}", location)


_KINDS = "article|amendment|section|clause|chapter|volume|book|verse|act|scene|epilogue|glossary|historical sketch"
_THING = (r"(?:passage|verse|line|text|quote|quotation|phrase|sentence|section|article|amendment|clause|chapter|volume|"
          r"scene|act|reference|epilogue|glossary|historical sketch)")
_NOT_HAVE = r"(?:does|do|did)(?:\s+not|n't)\s+(?:actually\s+)?(?:have|contain|include)\s+(?:an?\s+|any\s+|the\s+)?"
_NOT_EXIST = (r"(?:(?:does|do|did)(?:\s+not|n't)\s+(?:actually\s+)?exist\b|(?:is|are)\s+(?:a\s+)?non-?existent\b)")
_UNSURE = re.compile(r"\b(?:if|whether|unless|may|might|could|perhaps|possibly|unsure|uncertain|assum\w+|not\s+(?:sure|certain)|"
                     r"(?:cannot|can't|unable to)\s+(?:verify|confirm|check))\b", re.I)


def _roman(n: int) -> str:
    out = ""
    for v, r in ((100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        out, n = out + r * (n // v), n % v
    return out


def _places_asked(reference: str) -> tuple[str, dict[str, int]]:
    """(regex for the ways to name a place in the reference asked for, {kind: its number})."""
    ways, numbers = [re.escape(reference)] if reference else [], {}
    for m in re.finditer(rf"\b({_KINDS})\s+(\d+|[IVXLC]+)\b", reference, re.I):
        kind, n = m[1].lower(), to_int(m[2])
        numbers[kind] = n
        spelled = [w for w, k in (NUMBER_WORDS | ORDINALS).items() if k == n]
        ways.append(rf"{kind}\s+(?:{n}|{_roman(n)}|{'|'.join(spelled) or n})")
        ways.append(rf"(?:{n}(?:st|nd|rd|th)|{'|'.join(spelled) or n})\s+{kind}")
    ways += [m[1] for m in re.finditer(r"\b(Epilogue|Glossary|Historical Sketch)\b", reference)]
    m = re.fullmatch(r"(.+?) (\d+):(\d+)", reference)  # a Bible verse
    if m:
        book, ch, v = re.escape(m[1].removesuffix("s") if m[1] == "Psalms" else m[1]), m[2], m[3]
        numbers |= {"chapter": int(ch), "verse": int(v)}
        ways += [rf"(?:{book}s?\s+)?{ch}:{v}", rf"{book}s?\s+(?:chapter\s+)?{ch}(?!:)", rf"chapter\s+{ch}", rf"verse\s+{v}",
                 rf"(?:book\s+(?:of\s+|called\s+|named\s+)?)?{book}"]
    one = "(?:" + "|".join(f"(?:{w})" for w in ways) + r")(?!\w|:\d)"
    return rf"{one}(?:,?\s+{one})*" if ways else "(?!)", numbers


def _says_nonexistent(reference: str, sentence: str) -> bool:
    place, numbers = _places_asked(reference)
    q = '[\\"\'(]*'
    forms = [
        rf"\bthere(?:\s+(?:is|are|was|were)|'s)\s+(?:\w+\s+)?no\s+(?:such\s+)?{q}{place}",
        rf"{place}[\"')]*(?:\s*\([^)]*\)|\s+(?:of|in)\s+[^,.;]{{1,60}}?)?,?\s+(?:which\s+|that\s+|itself\s+|simply\s+)?{_NOT_EXIST}",
        rf"{place}[\"')]*\s+(?:is|are|was)(?:\s+not|n't)\s+(?:(?:included|found|present|a|part)\s+)*(?:in|of)\b",
        rf"{_NOT_HAVE}{q}{place}",
        rf"\b(?:has|have|had|contains?)\s+no\s+{q}{place}",
        rf"\bno\s+such\s+{_THING}\b|\bno\s+{_THING}\s+(?:actually\s+)?exists\b",
        rf"\b(?:requested|this|that|the|such|a)\s+{_THING}\s+{_NOT_EXIST}",
        rf"\bno\s+{q}{place}\s+(?:actually\s+)?(?:exists|appears)\b",
    ]
    for kind, asked in numbers.items():
        forms.append(rf"\b(?:has|have|contains?)\s+no\s+(?:\w+\s+)?{kind}s\b|{_NOT_HAVE}{asked}\s+(?:\w+\s+)?{kind}s\b")
    if any(not _UNSURE.search(sentence[:m.start()]) for f in forms for m in re.finditer(f, sentence, re.I)):
        return True
    # "has only 25 verses", "has 61 chapters, not 62": fewer than the number asked for
    for kind, asked in numbers.items():
        for m in re.finditer(rf"\bonly\s+(?:(?:has|have|had|contains?)\s+)?(?:\w+\s+)??{_NUM_OR_WORD}\s+(?:\w+\s+)?{kind}s\b"
                             rf"|\b(?:has|have|contains?)\s+{_NUM_OR_WORD}\s+(?:\w+\s+)?{kind}s\b,?\s+not\b", sentence, re.I):
            n = to_int(m[1] or m[2])
            if n is not None and n < asked and not _UNSURE.search(sentence[:m.start()]):
                return True
    return False


def _says_not_in_text(text_id: str, play: str | None, sentence: str) -> bool:
    named = _named(text_id, play)
    bare = re.sub(r'"', "", sentence)  # titles may stand in quotation marks
    # "This line is not from Hamlet": about the line, not about its spelling or its speaker
    subject = (r"(?i:(?:\b(?:line|passage|quote|quotation|phrase|verse|text|words|sentence|speech)s?"
               r"(?:\s+(?:above|below|quoted|given)|,?\s*\"[^\"]*\",?)?|\b(?:it|this|that|these|they|which)|\"[^\"]{8,}\")\s+"
               r"(?:is|are|was|were|does|do|did))")
    if re.search(rf"{subject}\s*(?i:{_DENIED}(?:in|from|of)\s+(?:{_PLAY}|{_THE})){_AUTHOR}\"?{named}", sentence) and \
            _denies_named_text(text_id, play, bare):
        return True
    if re.search(rf"{subject}(?i:(?:\s+not|n't)\s+(?:actually\s+)?(?:appear|occur|found|present)\s+(?:\w+\s+)?in\s+the\s+"
                 r"(?:novel|play|text|(?:\d{4}\s+)?first\s+edition|Project\s+Gutenberg\s+(?:edition|text))\b)", sentence):
        return True
    # "is from Macbeth, not Hamlet"; the title of a play that is also a character needs another title beside it
    if (not play or " " in play or re.search(_other(text_id, play), bare)) and re.search(
            r"(?i:\b(?:is|are|was|were|comes?|appears?|found)\s+(?:\w+\s+){0,4}?(?:from|in|of)\s+)"
            rf".*(?i:\bnot\s+(?:(?:from|in|of)\s+)?{_THE}){_AUTHOR}{named}", bare):
        return True
    missing = r"(?:passage|phrase|verse|sentence|line|quotation)\b(?!\s+(?:break|number))"
    return bool(re.search(
        rf"(?i:\bthere (?:is|are) no (?:\w+ )?{_THING}s?\b(?!.*\b(?:more|better|finer|so|as|like)\b)[^,]*? in (?:{_PLAY}|{_THE})){_AUTHOR}{named}"
        rf"|(?i:\bno {_THING} in (?:{_PLAY}|{_THE})){_AUTHOR}{named}(?i:[^.;]*\b(?:says|reads|contains|has)\b)"
        rf"|{named}[^.;]*(?i:\b(?:{_NOT_HAVE}|contains?\s+no\s+){missing})", sentence))


def says_not_there(text_id: str, play: str | None, reference: str, remarks: str, location: str = "",
                   quote: str = "") -> bool:
    """True if an answer to a trick question says that the passage asked for does not exist, or, in
    its ``remarks`` (outside its first JSON answer), that the line is not in the named text.

    Read sentence by sentence; in the location and in brackets inside the quote only the first kind
    counts, because the second is ``says_other_source``. The sentence must be about the place asked
    for ("There is no Section 5", "Jude has only 25 verses"), about the passage, line or text ("the
    requested text does not exist", "this line does not appear in Hamlet"), or name another work
    ("is from Macbeth, not Hamlet"). Conditions and doubts do not count ("if it does not exist").
    """
    def sentences(text: str) -> list[str]:
        return re.split(r"(?<=[.!?])[\"')]*\s+(?=[\"'(]*[A-Z0-9])|\n+", "\n".join(map(_plain, text.splitlines())))

    def sure(sentence: str) -> bool:  # the words of a quotation are not the model's doubts
        return not _UNSURE.search(re.sub(r'"[^"]{15,}"', " ", sentence))

    return any(_says_nonexistent(reference, x) for text in (remarks, location, *_brackets(quote)) for x in sentences(text)) or any(
        sure(x) and _says_not_in_text(text_id, play, x) for x in sentences(remarks))
