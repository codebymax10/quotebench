"""Download the source texts and parse them into addressable units.

Each text is parsed into JSONL records in ``sources/parsed/<id>.jsonl``, one record per unit:
verse (Bibles), line or prose sentence (plays), clause (Constitution), sentence (prose),
line (verse novel). Every record has ``text_id``, a global order index ``idx`` and ``text``,
plus the structural fields for that text (book/chapter/verse, play/act/scene, ...).

Raw downloads are kept in ``sources/raw/<id>/`` and committed, because Gutenberg and
Wikisource files change over time; ``sources/provenance.json`` records URL, date and SHA-256.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .textutil import clean_ws, html_to_text, split_sentences

ROOT = Path(__file__).resolve().parents[2]
SOURCES_DIR = ROOT / "sources"
RAW_DIR = SOURCES_DIR / "raw"
PARSED_DIR = SOURCES_DIR / "parsed"
PROVENANCE_JSON = SOURCES_DIR / "provenance.json"
PROVENANCE_MD = SOURCES_DIR / "PROVENANCE.md"

USER_AGENT = "QuoteBench/0.1 (research benchmark; public-domain texts)"


@dataclass(frozen=True)
class RawFile:
    name: str
    url: str


@dataclass(frozen=True)
class SourceText:
    id: str
    language: str
    title: str
    edition: str
    structure: str
    licence: str
    files: tuple[RawFile, ...]
    parser: Callable[[Path], list[dict]]
    notes: str = ""

    @property
    def raw_dir(self) -> Path:
        return RAW_DIR / self.id


# --------------------------------------------------------------------------------------
# Shared helpers


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")


def gutenberg_body(text: str) -> str:
    """Return the text between the Project Gutenberg START and END markers."""
    start = re.search(r"(?m)^\*\*\* ?START OF (THE|THIS) PROJECT GUTENBERG.*$", text)
    end = re.search(r"(?m)^\*\*\* ?END OF (THE|THIS) PROJECT GUTENBERG.*$", text)
    if not start or not end:
        raise ValueError("Gutenberg START/END markers not found")
    return text[start.end() : end.start()]


def paragraphs(text: str) -> list[str]:
    return [p for p in (clean_ws(b) for b in re.split(r"\n\s*\n", text)) if p]


ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman_to_int(s: str) -> int:
    total, prev = 0, 0
    for ch in reversed(s.upper()):
        v = ROMAN[ch]
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total


def prose_records(text_id: str, chapters: Iterable[tuple[int, str, str]], language: str) -> list[dict]:
    """Turn (chapter number, chapter title, chapter text) triples into sentence records."""
    records: list[dict] = []
    for chapter, title, body in chapters:
        n = 0
        for p_i, para in enumerate(paragraphs(body), start=1):
            for sent in split_sentences(para, language):
                n += 1
                records.append(
                    {
                        "text_id": text_id,
                        "chapter": chapter,
                        "chapter_title": title,
                        "paragraph": p_i,
                        "sentence": n,
                        "text": sent,
                    }
                )
    return records


# --------------------------------------------------------------------------------------
# King James Bible (Project Gutenberg #10)

BIBLE_BOOKS = [
    # (USFM code, KJV short name)
    ("GEN", "Genesis"), ("EXO", "Exodus"), ("LEV", "Leviticus"), ("NUM", "Numbers"),
    ("DEU", "Deuteronomy"), ("JOS", "Joshua"), ("JDG", "Judges"), ("RUT", "Ruth"),
    ("1SA", "1 Samuel"), ("2SA", "2 Samuel"), ("1KI", "1 Kings"), ("2KI", "2 Kings"),
    ("1CH", "1 Chronicles"), ("2CH", "2 Chronicles"), ("EZR", "Ezra"), ("NEH", "Nehemiah"),
    ("EST", "Esther"), ("JOB", "Job"), ("PSA", "Psalms"), ("PRO", "Proverbs"),
    ("ECC", "Ecclesiastes"), ("SNG", "Song of Solomon"), ("ISA", "Isaiah"), ("JER", "Jeremiah"),
    ("LAM", "Lamentations"), ("EZK", "Ezekiel"), ("DAN", "Daniel"), ("HOS", "Hosea"),
    ("JOL", "Joel"), ("AMO", "Amos"), ("OBA", "Obadiah"), ("JON", "Jonah"), ("MIC", "Micah"),
    ("NAM", "Nahum"), ("HAB", "Habakkuk"), ("ZEP", "Zephaniah"), ("HAG", "Haggai"),
    ("ZEC", "Zechariah"), ("MAL", "Malachi"), ("MAT", "Matthew"), ("MRK", "Mark"),
    ("LUK", "Luke"), ("JHN", "John"), ("ACT", "Acts"), ("ROM", "Romans"),
    ("1CO", "1 Corinthians"), ("2CO", "2 Corinthians"), ("GAL", "Galatians"),
    ("EPH", "Ephesians"), ("PHP", "Philippians"), ("COL", "Colossians"),
    ("1TH", "1 Thessalonians"), ("2TH", "2 Thessalonians"), ("1TI", "1 Timothy"),
    ("2TI", "2 Timothy"), ("TIT", "Titus"), ("PHM", "Philemon"), ("HEB", "Hebrews"),
    ("JAS", "James"), ("1PE", "1 Peter"), ("2PE", "2 Peter"), ("1JN", "1 John"),
    ("2JN", "2 John"), ("3JN", "3 John"), ("JUD", "Jude"), ("REV", "Revelation"),
]

_TESTAMENT_HEADINGS = re.compile(
    r"(?m)^The (Old|New) Testament of the King James (Version of the )?Bible\s*$"
)
_VERSE_MARK = re.compile(r"(?<![\d:])(\d+):(\d+)\s")


def parse_kjv(raw_dir: Path) -> list[dict]:
    body = gutenberg_body(read_text(raw_dir / "pg10.txt"))
    # 1-2 Samuel headings carry an alternate title ("Otherwise Called: The First Book of the
    # Kings") that would be mistaken for the 1-2 Kings headings.
    body = re.sub(r"\n(?:Otherwise|Commonly) Called:\s*\n\s*\n[^\n]+\n", "\n", body)
    lines = body.split("\n")
    # The body opens with a table of contents listing the 66 book titles in order;
    # each title then appears again as the heading of its book.
    toc = [l.strip() for l in lines if l.strip() and not _TESTAMENT_HEADINGS.match(l.strip())][:66]
    pos, starts = 0, []
    first_heading = body.index("\n" + toc[0], body.index(toc[-1]))
    pos = first_heading
    for title in toc:
        m = re.compile(r"(?m)^" + re.escape(title) + r"\s*$").search(body, pos)
        if not m:
            raise ValueError(f"KJV heading not found: {title}")
        starts.append((m.start(), m.end()))
        pos = m.end()
    records = []
    for b, (code, name) in enumerate(BIBLE_BOOKS):
        seg = body[starts[b][1] : starts[b + 1][0] if b + 1 < len(starts) else len(body)]
        seg = _TESTAMENT_HEADINGS.sub("", seg)
        parts = _VERSE_MARK.split(seg)
        # Anything before 1:1 is heading material ("or The Preacher", "Commonly Called: ...").
        if len(clean_ws(parts[0])) > 60:
            raise ValueError(f"unexpected text before first verse of {name}: {parts[0][:80]!r}")
        for i in range(1, len(parts), 3):
            records.append(
                {
                    "text_id": "bible_kjv",
                    "book": name,
                    "book_code": code,
                    "chapter": int(parts[i]),
                    "verse": int(parts[i + 1]),
                    "text": clean_ws(parts[i + 2]),
                }
            )
    return records


# --------------------------------------------------------------------------------------
# Shakespeare (Project Gutenberg #100)

PLAYS = [
    ("Hamlet", "THE TRAGEDY OF HAMLET, PRINCE OF DENMARK"),
    ("Macbeth", "THE TRAGEDY OF MACBETH"),
    ("Romeo and Juliet", "THE TRAGEDY OF ROMEO AND JULIET"),
]

_SPEAKER = re.compile(r"^([A-Z][A-Z’'\-]+(?:(?: | and | & )[A-Z’'\-]+)*|Both|All)\.?\s*$")
_SPEAKER_INLINE = re.compile(r"^([A-Z][A-Z’'\- ]{2,}[A-Z])\. (\S.*)$")
_ACT = re.compile(r"^\s*ACT ([IVX]+)\.?\s*$")
_SCENE = re.compile(r"^\s*SCENE ([IVX]+)\.")
_DIRECTION_WORDS = re.compile(
    r"(^|[.;] )(Enter|Re-enter|Exit|Exeunt|Trumpets?|Flourish|Hautboys|Alarums?|Sennet|Thunder|Knocking|Retreat)\b"
)
_BRACKETED = re.compile(r"\[[^\]]*\]")


def _is_prose_speech(lines: list[str]) -> bool:
    """Prose in #100 is hard-wrapped at ~70 chars, so a wrapped line continues in lowercase.
    Verse lines in this edition always start with a capital."""
    return any(len(a) >= 55 and b[:1].islower() for a, b in zip(lines, lines[1:]))


def parse_shakespeare(raw_dir: Path) -> list[dict]:
    body = gutenberg_body(read_text(raw_dir / "pg100.txt"))
    # The master contents list at the top is indented; every work then starts with its title
    # in capitals at column 0, so column-0 matches of those titles are the real starts.
    toc_block = body[body.index("Contents") : re.search(r"(?m)^THE SONNETS\s*$", body).start()]
    toc_titles = [l.strip() for l in toc_block.split("\n")[1:] if l.strip()]
    title_re = re.compile(r"(?m)^(" + "|".join(re.escape(t) for t in toc_titles) + r")\s*$")
    records: list[dict] = []
    for play, title in PLAYS:
        m = re.search(r"(?m)^" + re.escape(title) + r"\s*$", body)
        nxt = title_re.search(body, m.end())
        segment = body[m.end() : nxt.start() if nxt else len(body)]
        records.extend(_parse_play(play, segment)[0])
    return records


def _parse_play(play: str, segment: str) -> tuple[list[dict], list[str]]:
    """Parse one play. Returns (records, dropped blocks) — the dropped blocks are stage
    directions and front matter, returned so tests and reviewers can inspect them.

    Layout of #100: blocks are separated by blank lines. A speech block starts with the
    speaker in capitals ("HAMLET."). Stage directions are either bracketed ("[_Exit._]",
    removed wherever they occur) or stand-alone blocks indented by one space
    (" Thunder. Enter three Witches."). Songs, letters and verse-within-verse are indented by
    two or more spaces and are kept as speech.
    """
    # Skip the play's own contents list and Dramatis Personae.
    front = segment.find("Dramatis Person")
    start = re.compile(r"(?m)^(THE PROLOGUE|ACT I)\s*$").search(segment, max(front, 0))
    act = scene = 0
    speaker: str | None = None
    out: list[dict] = []
    dropped: list[str] = []
    line_no: dict[tuple[int, int], int] = {}

    def emit(lines: list[str]) -> None:
        lines = [clean_ws(l.replace("_", "")) for l in lines]
        lines = [l for l in lines if l]
        if not lines:
            return
        if _is_prose_speech(lines):
            units = [("prose", s) for s in split_sentences(" ".join(lines), "en")]
        else:
            units = [("verse", l) for l in lines]
        for form, text in units:
            key = (act, scene)
            line_no[key] = line_no.get(key, 0) + 1
            out.append(
                {
                    "text_id": "shakespeare",
                    "play": play,
                    "act": act,
                    "scene": scene,
                    "line": line_no[key],
                    "speaker": speaker.title() if speaker else None,
                    "form": form,
                    "text": text,
                }
            )

    for block in re.split(r"\n[ \t]*\n", segment[start.start() :]):
        raw_lines = [l.rstrip() for l in block.split("\n") if l.strip()]
        if not raw_lines:
            continue
        first = raw_lines[0]
        if m := _ACT.match(first):
            act, scene, speaker = roman_to_int(m.group(1)), 0, None
            raw_lines = raw_lines[1:]
            if not raw_lines:
                continue
            first = raw_lines[0]
        if first.strip() == "THE PROLOGUE":
            act, scene, speaker = 1, 0, None
            continue
        if m := _SCENE.match(first):
            scene, speaker = roman_to_int(m.group(1)), None
            continue
        speech: list[str] = []
        if (m := _SPEAKER.match(first)) and not first.startswith(" "):
            speaker = m.group(1)
            body_lines = raw_lines[1:]
        elif (m := _SPEAKER_INLINE.match(first)) and not first.startswith(" "):
            speaker = m.group(1)
            body_lines = [m.group(2)] + raw_lines[1:]
        else:
            # A block without a speaker heading continues the current speech (e.g. after an
            # interrupting stage direction) unless it is itself a stage direction.
            plain = _BRACKETED.sub("", block).strip()
            is_direction = (
                not plain
                or (first.startswith(" ") and not first.startswith("  ") and not first.lstrip().startswith("["))
                or _DIRECTION_WORDS.search(clean_ws(plain.replace("_", "")))
            )
            if is_direction or speaker is None:
                dropped.append(clean_ws(block))
                continue
            body_lines = raw_lines
        for l in body_lines:
            text = _BRACKETED.sub("", l)
            if not text.strip():
                continue
            # one-space-indented line that was not an inline direction = stage direction line
            if l.startswith(" ") and not l.startswith("  ") and not l.lstrip().startswith("["):
                dropped.append(l.strip())
                continue
            speech.append(text)
        emit(speech)
    return out, dropped


# --------------------------------------------------------------------------------------
# US Constitution (National Archives transcriptions)

_BLOCK = re.compile(r"<(h[1-4]|p)\b[^>]*>(.*?)</\1>", re.S | re.I)


def _blocks(page: str) -> list[tuple[str, str, str]]:
    """(tag, raw opening tag, plain text) for every heading and paragraph, in order."""
    out = []
    for m in _BLOCK.finditer(page):
        out.append((m.group(1).lower(), m.group(0)[: m.group(0).find(">") + 1], html_to_text(m.group(2))))
    return out


def parse_constitution(raw_dir: Path) -> list[dict]:
    records: list[dict] = []

    def add(part, article, amendment, section, text):
        key = (part, article, amendment, section)
        clause = sum(1 for r in records if (r["part"], r["article"], r["amendment"], r["section"]) == key) + 1
        records.append(
            {
                "text_id": "us_constitution",
                "part": part,
                "article": article,
                "amendment": amendment,
                "section": section,
                "clause": clause,
                "text": text.replace("*", "").strip(),
            }
        )

    # Main text: Preamble, Articles I-VII. Stop before the scribe's note on interlineations,
    # the attestation and the signatures, which are not operative text.
    blocks = _blocks(read_text(raw_dir / "constitution-transcript.html"))
    started = False
    article = section = None
    for tag, opening, text in blocks:
        if not started:
            if text.startswith("We the People"):
                started = True
                add("preamble", None, None, None, text)
            continue
        if text.startswith("The Word, \"the,\" being interlined"):
            break
        if m := re.match(r"^Article\.? ([IVX]+)\.?$", text):
            article, section = roman_to_int(m.group(1)), None
        elif m := re.match(r"^Section\.? (\d+)\.?$", text):
            section = int(m.group(1))
        elif tag == "p" and text:
            add("article", article, None, section, text)

    # Bill of Rights: the "U.S. Bill of Rights" section (Amendments I-X).
    blocks = _blocks(read_text(raw_dir / "bill-of-rights-transcript.html"))
    amendment = None
    started = False
    for tag, opening, text in blocks:
        if text == "The U.S. Bill of Rights":
            started = True
            continue
        if not started:
            continue
        if tag.startswith("h") and not text.startswith("Amendment"):
            break
        if m := re.match(r"^Amendment ([IVX]+)$", text):
            amendment = roman_to_int(m.group(1))
        elif tag == "p" and text and amendment:
            # each of Amendments I-X is one paragraph; what follows X is NARA's page footer
            add("amendment", None, amendment, None, text)
            if amendment == 10:
                break
            amendment = None

    # Amendments XI-XXVII. Skip the "Passed by Congress..." dates and editorial notes.
    blocks = _blocks(read_text(raw_dir / "amendments-11-27.html"))
    amendment = section = None
    for tag, opening, text in blocks:
        if m := re.match(r"^AMENDMENT ([IVX]+)$", text):
            amendment, section = roman_to_int(m.group(1)), None
            continue
        if amendment is None:
            continue
        if text.startswith("Back to Constitution") or (tag.startswith("h") and not text.startswith("Section")):
            break
        if m := re.match(r"^Section (\d+)\.?$", text):
            section = int(m.group(1))
        elif tag == "p" and text:
            if 'class="smaller"' in opening or text.startswith(("Note:", "*")):
                continue
            add("amendment", None, amendment, section, text)
    return records


# --------------------------------------------------------------------------------------
# Pride and Prejudice (Project Gutenberg #1342)

_ILLUSTRATION = re.compile(r"\[Illustration(?:[^\[\]]|\[[^\[\]]*\])*\]", re.S)


def parse_pride_prejudice(raw_dir: Path) -> list[dict]:
    body = gutenberg_body(read_text(raw_dir / "pg1342.txt"))
    heads = list(re.finditer(r"(?m)^(?:CHAPTER|Chapter) ([IVXLC]+)\.?\]?\s*$", body))
    first = max(i for i, h in enumerate(heads) if h.group(1) == "I")
    heads = heads[first:]
    numbers = [roman_to_int(h.group(1)) for h in heads]
    if numbers != list(range(1, 62)):
        raise ValueError(f"unexpected chapter sequence: {numbers}")
    end = body.rindex("CHISWICK PRESS")  # printer's imprint after "THE END" (also on the title page)
    chapters = []
    for i, h in enumerate(heads):
        stop = heads[i + 1].start() if i + 1 < len(heads) else end
        text = body[h.end() : stop]
        if i + 1 < len(heads):
            # the next heading may sit inside an "[Illustration: ... Chapter N.]" block
            text = re.sub(r"\[Illustration[^\]]*$", "", text, flags=re.S)
        text = _ILLUSTRATION.sub("", text).replace("_", "")
        chapters.append((numbers[i], "", text))
    return prose_records("pride_prejudice", chapters, "en")


# --------------------------------------------------------------------------------------
# On the Origin of Species, 1st edition 1859 (Project Gutenberg #1228)


def parse_origin(raw_dir: Path) -> list[dict]:
    body = gutenberg_body(read_text(raw_dir / "pg1228.txt"))
    body = body[: re.search(r"(?m)^INDEX\.\s*$", body).start()]
    # "INTRODUCTION." appears twice: in the detailed contents and as the real heading.
    intro = list(re.finditer(r"(?m)^INTRODUCTION\.\s*$", body))[-1]
    body = body[intro.start() :]
    heads = list(re.finditer(r"(?m)^(INTRODUCTION|CHAPTER ([IVX]+))\.\s*$", body))
    chapters = []
    for i, h in enumerate(heads):
        stop = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        text = body[h.end() : stop]
        if h.group(2):
            number = roman_to_int(h.group(2))
            blocks = re.split(r"\n\s*\n", text.strip("\n"), maxsplit=2)
            # blocks[0] = chapter title in capitals, blocks[1] = Darwin's list of the chapter's
            # topics (a contents-style summary, not running prose): both are dropped.
            title = clean_ws(blocks[0]).replace("_", "").rstrip(".")
            text = blocks[2] if len(blocks) > 2 else ""
        else:
            number, title = 0, "Introduction"
        chapters.append((number, title.title() if title.isupper() else title, text.replace("_", "")))
    return prose_records("origin_species", chapters, "en")


# --------------------------------------------------------------------------------------
# Registry

GUTENBERG_LICENCE = (
    "Public domain in the USA. Project Gutenberg licence text stripped; "
    "no Gutenberg trademark used."
)

REGISTRY: dict[str, SourceText] = {
    s.id: s
    for s in [
        SourceText(
            id="bible_kjv",
            language="en",
            title="The Holy Bible",
            edition="King James Version",
            structure="book / chapter / verse",
            licence=GUTENBERG_LICENCE + " (The KJV is under Crown patent in the UK only.)",
            files=(RawFile("pg10.txt", "https://www.gutenberg.org/cache/epub/10/pg10.txt"),),
            parser=parse_kjv,
            notes="Project Gutenberg eBook #10. Psalm superscriptions are not in this file. "
            "Words like 'Selah' printed as separate paragraphs are kept with the preceding verse.",
        ),
        SourceText(
            id="shakespeare",
            language="en",
            title="Hamlet; Macbeth; Romeo and Juliet",
            edition="Project Gutenberg Complete Works of William Shakespeare (eBook #100)",
            structure="play / act / scene / line",
            licence=GUTENBERG_LICENCE,
            files=(RawFile("pg100.txt", "https://www.gutenberg.org/cache/epub/100/pg100.txt"),),
            parser=parse_shakespeare,
            notes="Stage directions removed. Verse speeches: one unit per printed line. Prose "
            "speeches (hard-wrapped in the file): one unit per sentence. Line numbers are our "
            "own running count within each scene, not Folger/Arden numbering. Prologues are scene 0.",
        ),
        SourceText(
            id="us_constitution",
            language="en",
            title="The Constitution of the United States",
            edition="National Archives transcription (original spelling and punctuation)",
            structure="article / section / clause; amendment / section / clause",
            licence="U.S. government work, public domain.",
            files=(
                RawFile("constitution-transcript.html", "https://www.archives.gov/founding-docs/constitution-transcript"),
                RawFile("bill-of-rights-transcript.html", "https://www.archives.gov/founding-docs/bill-of-rights-transcript"),
                RawFile("amendments-11-27.html", "https://www.archives.gov/founding-docs/amendments-11-27"),
            ),
            parser=parse_constitution,
            notes="Clause = paragraph within a section (standard 'Article I, Section 2, Clause 3' "
            "numbering). Signatures, attestation, the scribe's interlineation note and NARA's "
            "'Passed by Congress'/'Note:' annotations are excluded. Superseded text is kept.",
        ),
        SourceText(
            id="pride_prejudice",
            language="en",
            title="Pride and Prejudice",
            edition="Project Gutenberg eBook #1342 (George Allen 1894 illustrated edition)",
            structure="chapter / sentence",
            licence=GUTENBERG_LICENCE,
            files=(RawFile("pg1342.txt", "https://www.gutenberg.org/cache/epub/1342/pg1342.txt"),),
            parser=parse_pride_prejudice,
            notes="Saintsbury preface, list of illustrations and illustration captions removed. "
            "Chapters numbered 1-61 continuously as in this edition.",
        ),
        SourceText(
            id="origin_species",
            language="en",
            title="On the Origin of Species",
            edition="First edition, 1859 (Project Gutenberg eBook #1228)",
            structure="chapter / sentence",
            licence=GUTENBERG_LICENCE,
            files=(RawFile("pg1228.txt", "https://www.gutenberg.org/cache/epub/1228/pg1228.txt"),),
            parser=parse_origin,
            notes="Introduction = chapter 0. Chapter-head topic lists (the contents-style "
            "summaries under each chapter title) and the index are removed.",
        ),
    ]
}


# --------------------------------------------------------------------------------------
# Download / parse / provenance


def _load_provenance() -> dict:
    if PROVENANCE_JSON.exists():
        return json.loads(PROVENANCE_JSON.read_text(encoding="utf-8"))
    return {}


def download(src: SourceText, refresh: bool = False) -> list[str]:
    """Fetch any missing raw files for ``src``; return messages about what happened."""
    import httpx

    prov = _load_provenance()
    entry = prov.setdefault(src.id, {"files": {}})
    msgs = []
    src.raw_dir.mkdir(parents=True, exist_ok=True)
    for f in src.files:
        path = src.raw_dir / f.name
        if path.exists() and not refresh:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            recorded = entry["files"].get(f.name, {}).get("sha256")
            if recorded and recorded != digest:
                msgs.append(f"WARNING {src.id}/{f.name}: file differs from recorded SHA-256")
            continue
        resp = httpx.get(f.url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=60)
        resp.raise_for_status()
        path.write_bytes(resp.content)
        entry["files"][f.name] = {
            "url": f.url,
            "retrieved": dt.date.today().isoformat(),
            "sha256": hashlib.sha256(resp.content).hexdigest(),
            "bytes": len(resp.content),
        }
        msgs.append(f"downloaded {src.id}/{f.name} ({len(resp.content):,} bytes)")
    PROVENANCE_JSON.write_text(json.dumps(prov, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return msgs


def parse(src: SourceText) -> list[dict]:
    records = src.parser(src.raw_dir)
    for i, r in enumerate(records):
        r["idx"] = i
    return records


def write_parsed(src: SourceText, records: list[dict]) -> Path:
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PARSED_DIR / f"{src.id}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


def load_units(text_id: str) -> list[dict]:
    path = PARSED_DIR / f"{text_id}.jsonl"
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def write_provenance_md() -> None:
    prov = _load_provenance()
    out = [
        "# Source provenance",
        "",
        "Generated by `quotebench sources` from `sources/provenance.json`. Raw files are kept in "
        "`sources/raw/<id>/` exactly as downloaded; parsing never modifies them.",
        "",
    ]
    for src in REGISTRY.values():
        out += [
            f"## `{src.id}` — {src.title}",
            "",
            f"- **Language:** {src.language}",
            f"- **Edition:** {src.edition}",
            f"- **Structure:** {src.structure}",
            f"- **Licence:** {src.licence}",
        ]
        if src.notes:
            out.append(f"- **Parsing notes:** {src.notes}")
        for f in src.files:
            info = prov.get(src.id, {}).get("files", {}).get(f.name, {})
            out.append(
                f"- `raw/{src.id}/{f.name}` — <{f.url}> — retrieved {info.get('retrieved', '?')}, "
                f"{info.get('bytes', 0):,} bytes, SHA-256 `{info.get('sha256', '?')}`"
            )
        out.append("")
    PROVENANCE_MD.write_text("\n".join(out), encoding="utf-8")
