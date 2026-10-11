"""Small text helpers shared by the parsers: whitespace cleanup and sentence splitting."""

from __future__ import annotations

import html
import re

_WS = re.compile(r"\s+")


def clean_ws(text: str) -> str:
    """Collapse all whitespace (incl. non-breaking spaces and line breaks) to single spaces."""
    return _WS.sub(" ", text.replace("­", "")).strip()


def html_to_text(fragment: str) -> str:
    """Strip tags from a small HTML fragment and unescape entities."""
    fragment = re.sub(r"<br\s*/?>", " ", fragment, flags=re.I)
    return clean_ws(html.unescape(re.sub(r"<[^>]+>", "", fragment)))


# Abbreviations that end with a period but do not end a sentence (lowercased, without the period).
ABBREVIATIONS = {
    "en": {
        "mr", "mrs", "messrs", "dr", "st", "esq", "capt", "col", "gen", "lieut", "rev",
        "viz", "vol", "vols", "no", "ch", "chap", "fig", "p", "pp", "etc", "ibid", "cf", "sq",
        "alph", "aug", "mm", "sept", "edw",
    },
    "ru": {
        "т", "д", "п", "г", "гг", "др", "пр", "см", "ср", "им", "ул", "стр", "тт", "руб", "коп",
        "кн", "св", "ст", "проч", "напр", "тыс", "ч", "о",
    },
}

# Abbreviations that are also ordinary words, so only count when capitalised exactly so
# ("M. Is. Geoffroy St. Hilaire" in Darwin).
CASED_ABBREVIATIONS = {"en": {"Is"}, "ru": set()}

_CLOSERS = "\"'”’»)]"
_OPENERS = "\"'“‘«(["
_DASHES = "—–-"
_END = re.compile(r"[.!?…]+")


def split_sentences(paragraph: str, language: str) -> list[str]:
    """Split one paragraph into sentences.

    Rule-based: a sentence ends at . ! ? or … (plus any closing quotes/brackets) when the next
    word starts with a capital letter, an opening quote, or a dash followed by a capital
    (Russian dialogue: «— Пойдём», but not «— сказал он»). A period after a known
    abbreviation or a single capital letter (an initial) does not end a sentence.
    Paragraph boundaries always end a sentence, so callers split paragraphs first.
    """
    text = clean_ws(paragraph)
    if not text:
        return []
    abbrevs = ABBREVIATIONS[language]
    sentences: list[str] = []
    start = 0
    for m in _END.finditer(text):
        end = m.end()
        while end < len(text) and text[end] in _CLOSERS:
            end += 1
        if end >= len(text):
            break
        if not text[end].isspace():
            continue
        if not _starts_new_sentence(text[end:].lstrip()):
            continue
        if m.group().endswith(".") and len(m.group()) == 1:
            word = re.search(r"(\w+)$", text[start:m.start()])
            if word:
                w = word.group(1)
                is_initial = len(w) == 1 and w.isupper() and not (language == "en" and w == "I")
                if w.lower() in abbrevs or w in CASED_ABBREVIATIONS[language] or is_initial:
                    continue
        sentences.append(text[start:end].strip())
        start = end
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def _starts_new_sentence(rest: str) -> bool:
    i = 0
    while i < len(rest) and (rest[i] in _OPENERS or rest[i] in _DASHES or rest[i] == " "):
        i += 1
    if i >= len(rest):
        return False
    ch = rest[i]
    return ch.isupper() or ch.isdigit()
