"""Parser anchor tests: known passages must come out of each source exactly as printed.

These parse the committed raw files in sources/raw/, so they need no network access.
"""

import collections
import re

import pytest

from quotebench import sources as S


@pytest.fixture(scope="module")
def units():
    cache = {}

    def get(text_id):
        if text_id not in cache:
            cache[text_id] = S.parse(S.REGISTRY[text_id])
        return cache[text_id]

    return get


def find(records, **where):
    hits = [r for r in records if all(r.get(k) == v for k, v in where.items())]
    assert len(hits) == 1, f"expected one record for {where}, got {len(hits)}"
    return hits[0]


# --- King James Bible ------------------------------------------------------------------


def test_kjv_counts(units):
    kjv = units("bible_kjv")
    assert len(kjv) == 31102  # the standard KJV verse count
    assert len({r["book_code"] for r in kjv}) == 66


def test_kjv_anchors(units):
    kjv = units("bible_kjv")
    assert find(kjv, book="Genesis", chapter=1, verse=1)["text"] == (
        "In the beginning God created the heaven and the earth."
    )
    assert find(kjv, book="John", chapter=3, verse=16)["text"] == (
        "For God so loved the world, that he gave his only begotten Son, that whosoever "
        "believeth in him should not perish, but have everlasting life."
    )
    assert find(kjv, book="Revelation", chapter=22, verse=21)["text"] == (
        "The grace of our Lord Jesus Christ be with you all. Amen."
    )
    # "Selah" printed as its own paragraph belongs to the verse before it
    assert find(kjv, book="Psalms", chapter=3, verse=2)["text"].endswith("God. Selah.")
    # last verse of Malachi must not swallow the New Testament heading
    assert "Testament" not in find(kjv, book="Malachi", chapter=4, verse=6)["text"]
    # 1 Samuel's "Otherwise Called: The First Book of the Kings" must not split books
    assert find(kjv, book="1 Kings", chapter=1, verse=1)["text"].startswith("Now king David was old")


def test_kjv_no_heading_leftovers(units):
    for r in units("bible_kjv"):
        assert "Called:" not in r["text"]
        assert not re.search(r"\d+:\d+", r["text"]), r


# --- Shakespeare ---------------------------------------------------------------------


def test_shakespeare_scene_structure(units):
    sh = units("shakespeare")
    scenes = collections.Counter(r["play"] for r in {(r["play"], r["act"], r["scene"]): r for r in sh}.values())
    assert scenes["Hamlet"] == 20
    assert scenes["Macbeth"] == 28
    assert scenes["Romeo and Juliet"] == 24 + 2  # 5+6+5+5+3 scenes, plus two Chorus prologues (scene 0)


def test_shakespeare_anchors(units):
    sh = units("shakespeare")
    r = find(sh, play="Hamlet", text="To be, or not to be, that is the question:")
    assert (r["act"], r["scene"], r["speaker"], r["form"]) == (3, 1, "Hamlet", "verse")
    r = find(sh, play="Macbeth", text="Tomorrow, and tomorrow, and tomorrow,")
    assert (r["act"], r["scene"], r["speaker"]) == (5, 5, "Macbeth")
    r = find(sh, play="Romeo and Juliet", text="O Romeo, Romeo, wherefore art thou Romeo?")
    assert (r["act"], r["scene"], r["speaker"]) == (2, 2, "Juliet")
    r = find(sh, play="Romeo and Juliet", text="Two households, both alike in dignity,")
    assert (r["act"], r["scene"], r["speaker"]) == (1, 0, "Chorus")
    # prose speech split into sentences
    r = find(sh, play="Macbeth", text="Out, damned spot! out, I say!")
    assert (r["act"], r["scene"], r["form"]) == (5, 1, "prose")


def test_shakespeare_no_stage_directions(units):
    for r in units("shakespeare"):
        assert not re.search(r"[\[\]_]", r["text"]), r
        assert not re.match(r"(Enter|Exit|Exeunt|Re-enter)\b(?!, sir)", r["text"]), r
        assert r["speaker"], r


# --- US Constitution ------------------------------------------------------------------


def test_constitution_structure(units):
    con = units("us_constitution")
    assert sum(r["part"] == "preamble" for r in con) == 1
    assert {r["article"] for r in con if r["part"] == "article"} == set(range(1, 8))
    assert {r["amendment"] for r in con if r["part"] == "amendment"} == set(range(1, 28))
    # Article I: 1+5+7+2+4+2+3+18+8+3 clauses across its ten sections
    assert sum(r["article"] == 1 for r in con) == 53
    assert sum(r["amendment"] == 10 for r in con) == 1


def test_constitution_anchors(units):
    con = units("us_constitution")
    assert find(con, part="preamble")["text"].startswith(
        "We the People of the United States, in Order to form a more perfect Union,"
    )
    assert "three fifths of all other Persons" in find(con, article=1, section=2, clause=3)["text"]
    assert find(con, amendment=1)["text"].startswith("Congress shall make no law respecting an establishment")
    assert find(con, amendment=27)["text"] == (
        "No law, varying the compensation for the services of the Senators and Representatives, "
        "shall take effect, until an election of Representatives shall have intervened."
    )
    assert find(con, amendment=14, section=1)["text"].startswith("All persons born or naturalized")


def test_constitution_no_annotations(units):
    for r in units("us_constitution"):
        assert not r["text"].startswith(("Note:", "Passed by", "Amendments 11-27", "Back to")), r
        assert "Attest" not in r["text"] and "interlined" not in r["text"]


# --- Pride and Prejudice ----------------------------------------------------------------


def test_pride_prejudice(units):
    pp = units("pride_prejudice")
    assert {r["chapter"] for r in pp} == set(range(1, 62))
    assert pp[0]["text"] == (
        "It is a truth universally acknowledged, that a single man in possession of a good "
        "fortune must be in want of a wife."
    )
    assert pp[-1]["text"].endswith("had been the means of uniting them.")
    assert pp[-1]["chapter"] == 61
    for r in pp:
        assert not re.search(r"Illustration|Saintsbury|CHISWICK|[\[\]_]", r["text"]), r


# --- On the Origin of Species ----------------------------------------------------------------


def test_origin(units):
    og = units("origin_species")
    assert {r["chapter"] for r in og} == set(range(0, 15))
    assert og[0]["chapter"] == 0
    assert og[0]["text"].startswith("When on board H.M.S. ‘Beagle,’ as naturalist, I was much struck")
    assert og[-1]["text"].endswith(
        "endless forms most beautiful and most wonderful have been, and are being, evolved."
    )
    for r in og:
        assert not re.search(r"CHAPTER|INDEX|[\[\]_]", r["text"]), r
