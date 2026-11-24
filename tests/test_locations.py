import pytest

from quotebench.locations import (
    check_constitution, location_correct, parse_bible, parse_chapter, parse_constitution, parse_play,
    resolve, says_other_source,
)
from quotebench.scoring import load_index


def test_parse_bible():
    assert parse_bible("John 3:16") == {"book_code": "JHN", "chapter": 3, "verse_start": 16, "verse_end": 16}
    assert parse_bible("1 Corinthians 13:4-7")["verse_end"] == 7
    assert parse_bible("I Cor. 13:4")["book_code"] == "1CO"
    assert parse_bible("First John 4:8")["book_code"] == "1JN"
    assert parse_bible("Psalm 23")["book_code"] == "PSA"
    assert parse_bible("The Gospel According to Saint Matthew 5:9")["book_code"] == "MAT"
    assert parse_bible("Song of Songs 2:1 (KJV)")["book_code"] == "SNG"
    assert parse_bible("Revelations 22:21")["book_code"] == "REV"
    assert parse_bible("Hezekiah 3:5") is None


def test_parse_play():
    assert parse_play("Act 3, Scene 1") == {"act": 3, "scene": 1}
    assert parse_play("Hamlet, Act III, Scene i, lines 56-60") == {"act": 3, "scene": 1}
    assert parse_play("III.i.56") == {"act": 3, "scene": 1}
    assert parse_play("Act 5") == {"act": 5}
    assert parse_play("Prologue") == {"act": 1, "scene": 0}
    assert parse_play("Act 2, Prologue (Chorus)") == {"act": 2, "scene": 0}
    assert parse_play("near the end") is None


def test_parse_constitution():
    assert parse_constitution("Preamble") == {"part": "preamble"}
    assert parse_constitution("Article I, Section 8, Clause 3") == {"part": "article", "article": 1, "section": 8, "clause": 3}
    assert parse_constitution("Art. 2 § 1") == {"part": "article", "article": 2, "section": 1}
    assert parse_constitution("Fourteenth Amendment, Section 1") == {"part": "amendment", "amendment": 14, "section": 1}
    assert parse_constitution("Amendment XIX") == {"part": "amendment", "amendment": 19}
    assert parse_constitution("the 1st Amendment") == {"part": "amendment", "amendment": 1}


def test_parse_chapter():
    assert parse_chapter("Chapter 34", "pride_prejudice") == {"chapter": 34}
    assert parse_chapter("Volume II, Chapter 11", "pride_prejudice") == {"chapter": 34}
    assert parse_chapter("Chapter IV", "origin_species") == {"chapter": 4}
    assert parse_chapter("Introduction", "origin_species") == {"chapter": 0}
    assert parse_chapter("in the chapter on Natural Selection", "origin_species", chapter_titles={4: "Natural Selection"}) == {"chapter": 4}


def test_location_correct_granularity():
    unit = {"book_code": "JHN", "chapter": 3, "verse": 16}
    assert location_correct("bible_kjv", "John 3:16", [unit]) is True
    assert location_correct("bible_kjv", "John 3", [unit]) is True  # less specific but true
    assert location_correct("bible_kjv", "John 3:17", [unit]) is False
    assert location_correct("bible_kjv", "", [unit]) is None


# --- continuous and volume numbering (Pride and Prejudice) --------------------------------


@pytest.mark.parametrize("location, chapter", [
    ("Chapter 56 (Volume III, Chapter 14)", 56),  # used to become 98
    ("Chapter 31 (Volume II, Chapter 8), spoken by Lady Catherine", 31),  # used to become 54
    ("Chapter 34 (the first proposal, Volume II, Chapter XI in the original division)", 34),
    ("Volume III, Chapter 14 (Chapter LVI)", 56),
    ("Chapter 11 (Volume I, Chapter XI)", 11),
    ("Chapter 56 (Volume III)", 56),
    ("Volume III, Chapter 14", 56),
    ("Chapter 14 (Volume III)", 56),
    ("Vol. 2, Ch. 11", 34),
    ("Chapter 43 (Chapter XLIII)", 43),  # no volume: as before
])
def test_chapter_with_volume(location, chapter):
    assert parse_chapter(location, "pride_prejudice") == {"chapter": chapter}


@pytest.mark.parametrize("location", [
    "Chapter 50 (Volume III, Chapter 14)",  # the two numbers are different chapters
    "Chapter 56 (Volume III, Chapter 14, not Chapter 57)",
    "Chapter 31 (Volume III, Chapter 8)",  # 31 is in volume II
    "Chapter 30 (Volume I)",  # volume I has 23 chapters
    "Volume II, Chapter 23",
    "Volume IV, Chapter 1",
    "Volume II or Volume III, Chapter 8",
])
def test_contradictory_or_impossible_volumes_are_no_chapter(location):
    loc = parse_chapter(location, "pride_prejudice")
    assert not any(location_correct("pride_prejudice", location, [{"chapter": n}]) for n in range(1, 62)), loc


def test_volume_rule_covers_every_chapter_once():
    seen = [parse_chapter(f"Volume {v}, Chapter {n}", "pride_prejudice")["chapter"]
            for v, length in ((1, 23), (2, 19), (3, 19)) for n in range(1, length + 1)]
    assert seen == list(range(1, 62))


# --- sections of articles and amendments printed without section numbers -------------------


def constitution(location):
    _, units, _ = load_index("us_constitution")
    return [(units[i]["part"], units[i]["article"] or units[i]["amendment"], units[i]["section"], units[i]["clause"])
            for i in resolve("us_constitution", parse_constitution(location), units)]


def test_section_of_an_unsectioned_amendment_is_its_paragraph():
    assert constitution("Amendment XIX, Section 1") == [("amendment", 19, None, 1)]
    assert constitution("Nineteenth Amendment, Section 2") == [("amendment", 19, None, 2)]
    assert constitution("Amendment XIX, Section 3") == []
    assert constitution("Article VI, Section 2") == [("article", 6, None, 2)]
    assert constitution("Article VI, Section 2, Clause 1") == [("article", 6, None, 2)]
    assert constitution("Article VI, Section 2, Clause 2") == []  # not a reference anybody prints
    assert constitution("Article VI, Clause 2") == [("article", 6, None, 2)]
    assert constitution("First Amendment, Section 1") == [("amendment", 1, None, 1)]
    assert constitution("First Amendment, Section 2") == []
    assert constitution("Article V, Section 2") == []


def test_printed_section_numbers_must_match():
    assert constitution("Amendment XIV, Section 1") == [("amendment", 14, 1, 1)]
    assert constitution("Amendment XIV, Section 6") == []
    assert constitution("Article II, Section 5") == []
    enforcement = {"part": "amendment", "article": None, "amendment": 19, "section": None, "clause": 2}
    assert not check_constitution(parse_constitution("Amendment XIX, Section 1"), enforcement)
    assert not check_constitution(parse_constitution("Amendment XV, Section 2"), enforcement)


def test_a_section_never_reaches_two_paragraphs():
    """Nothing in the text has two units for one stated section of an unsectioned part."""
    _, units, _ = load_index("us_constitution")
    for part, n in {(u["part"], u["article"] or u["amendment"]) for u in units if u["section"] is None and u["part"] != "preamble"}:
        for section in range(1, 6):
            hits = constitution(f"{part} {n}, Section {section}")
            assert hits in ([], [(part, n, None, section)])


# --- trick questions: answers that say the line is from somewhere else ---------------------


@pytest.mark.parametrize("text_id, play, location", [
    ("shakespeare", "Macbeth", "Not in Macbeth. It is spoken by Antony in Shakespeare's Julius Caesar, Act 3, Scene 2."),
    ("shakespeare", "Macbeth", "Not in Macbeth; Julius Caesar, Act 3"),
    ("shakespeare", "Hamlet", "This line does not appear in Hamlet."),
    ("shakespeare", "Hamlet", "As You Like It, Act II, Scene VII (not Hamlet)"),
    ("shakespeare", "Romeo and Juliet", "A Midsummer Night’s Dream, Act I, Scene I (not Romeo and Juliet)"),
    ("shakespeare", "Romeo and Juliet", "Twelfth Night, Act 1, Scene 1"),
    ("shakespeare", "Hamlet", "Macbeth, Act 5, Scene 1"),
    ("pride_prejudice", None, "Emma, Volume III, Chapter XIII; this line is not from Pride and Prejudice."),
    ("pride_prejudice", None, "Jane Austen's Persuasion, Chapter 23"),
    ("us_constitution", None, "The Declaration of Independence, second paragraph (not the U.S. Constitution)."),
    ("us_constitution", None, "Gettysburg Address, opening sentence (not the Constitution of the United States)"),
    ("origin_species", None, "Not found in On the Origin of Species"),
    ("bible_kjv", None, "This saying isn't in the Bible"),
])
def test_answer_says_it_is_from_another_source(text_id, play, location):
    assert says_other_source(text_id, play, location)


@pytest.mark.parametrize("text_id, play, location", [
    ("shakespeare", "Macbeth", "Macbeth, Act 5, Scene 1"),
    ("shakespeare", "Hamlet", "Act 5, Scene 1"),
    ("shakespeare", "Hamlet", "Hamlet, Act 1, Scene 5, spoken by Horatio, not Hamlet"),
    ("shakespeare", "Macbeth", "Act 1, Scene 3, spoken by Banquo, not Macbeth"),
    ("shakespeare", "Hamlet", "Act 3, Scene 4, not in Hamlet's soliloquy"),
    ("shakespeare", "Hamlet", "Hamlet, not Macbeth"),
    ("shakespeare", "Macbeth", "Julius Caesar, quoted in Macbeth, Act 3"),
    ("pride_prejudice", None, "Chapter 48 (Final chapter)"),
    ("pride_prejudice", None, "Emma Woodhouse, Chapter 5"),
    ("pride_prejudice", None, "Chapter 10, on persuasion"),
    ("us_constitution", None, "Article IV, Section 2, Clause 1, Constitution of the United States"),  # same text
    ("origin_species", None, "Chapter III, “Struggle for Existence” (first edition, 1859)"),
    ("bible_kjv", None, "Jude 1:24"),
    ("bible_kjv", None, ""),
])
def test_answer_presents_the_quote_as_from_the_named_text(text_id, play, location):
    assert not says_other_source(text_id, play, location)


def test_remarks_in_brackets_inside_the_quote_count_but_the_quote_itself_does_not():
    assert says_other_source("shakespeare", "Hamlet", "", "[Not in Hamlet] All the world's a stage")
    assert says_other_source("shakespeare", "Hamlet", "", "All the world's a stage (As You Like It, not Hamlet)")
    assert not says_other_source("shakespeare", "Hamlet", "Act 5", "Was't Hamlet wrong'd Laertes? Not in Hamlet, never Hamlet")
