import pytest

from quotebench.locations import (
    bible_place_exists, check_constitution, check_play, location_correct, parse_bible, parse_chapter,
    parse_constitution, parse_play, resolve, says_not_there, says_other_source,
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


@pytest.mark.parametrize("play, location", [
    ("Hamlet", "words from Polonius, not from Hamlet"),
    ("Hamlet", "not a line of Hamlet"),
    ("Hamlet", "Act 1, Scene 3; not a line of Hamlet"),
    ("Macbeth", "not from Macbeth himself"),
    ("Macbeth", "Not from Macbeth himself but from the witches, Act 1"),
    ("Hamlet", "Polonius to Laertes (not from Hamlet)"),
    ("Hamlet", "Act 1, spoken by the Ghost, not by Hamlet"),
    ("Hamlet", "The line is from the Ghost, not Hamlet"),
    ("Hamlet", "not in Hamlet himself but in his mother"),
    ("Hamlet", "not from Hamlet, the prince"),
])
def test_a_character_of_the_same_name_is_not_the_play(play, location):
    assert not says_other_source("shakespeare", play, location)


@pytest.mark.parametrize("play, location", [
    ("Hamlet", "Not from Hamlet."), ("Hamlet", "This line is not from Hamlet"),
    ("Hamlet", "not from the play Hamlet"), ("Hamlet", "Not a line of Hamlet; it is from Macbeth, Act 5"),
    ("Hamlet", 'From "Macbeth", not "Hamlet"'), ("Macbeth", "It isn't in Macbeth"),
    ("Romeo and Juliet", "not a line of Romeo and Juliet"),  # no character has this name
])
def test_the_play_itself_is_denied(play, location):
    assert says_other_source("shakespeare", play, location)


# --- trick questions: answers that say the passage is not there ----------------------------


@pytest.mark.parametrize("text_id, play, reference, remark", [
    ("us_constitution", None, "Article V, Section 2", 'Note: There is no "Article V, Section 2" in the U.S. Constitution.'),
    ("us_constitution", None, "Amendment XXX", "There is actually no Amendment 30."),
    ("us_constitution", None, "Amendment XXX", "The text is hypothetical; in reality no such text exists."),
    ("us_constitution", None, "Amendment XXX", "A thirtieth Amendment does not exist"),
    ("us_constitution", None, "Article VIII", "*The Constitution has only **seven** Articles.*"),
    ("us_constitution", None, "Article II, Section 5", "Article II does not have a Section 5; it has four sections."),
    ("us_constitution", None, "Article V, Section 2", "Article V (the amendment process) has no sections."),
    ("us_constitution", None, "Article I, Section 11", "Article I, Section 11 of the Constitution does not exist."),
    ("bible_kjv", None, "Jude 1:26", "Jude only has 25 verses, so Jude 1:26 does not exist in the Bible."),
    ("bible_kjv", None, "Jude 1:26", "Jude has only 25 verses."),
    ("bible_kjv", None, "Psalms 151:1", "Psalm 151 is not part of the King James Version."),
    ("bible_kjv", None, "Hezekiah 3:5", "There is no Book of Hezekiah."),
    ("pride_prejudice", None, "the first sentence of Chapter 62", "Pride and Prejudice has 61 chapters, not 62."),
    ("pride_prejudice", None, "the first sentence of Chapter 62", "The novel does not have 62 chapters."),
    ("origin_species", None, "the first sentence of the Historical Sketch", "The first edition did not contain a Historical Sketch."),
    ("shakespeare", "Macbeth", "the first line of Act 6, Scene 1", "Macbeth doesn't have an Act 6."),
    ("shakespeare", "Romeo and Juliet", "the first line of Act 3, Scene 7", "No Act 3, Scene 7 exists in the play."),
    ("shakespeare", "Hamlet", "", "Note: The line appears in Macbeth. It does not appear in *Hamlet*."),
    ("shakespeare", "Hamlet", "", 'The line "Out, damned spot!" is from **Macbeth**, not Hamlet.'),
    ("pride_prejudice", None, "", "The line is from Anna Karenina, not from Pride and Prejudice."),
    ("us_constitution", None, "", 'The phrase "Give me liberty!" does not appear in the original text of the U.S. Constitution.'),
    ("us_constitution", None, "", "This phrase appears in the Declaration of Independence (1776), not the Constitution."),
    ("bible_kjv", None, "", "There is no verse about gambling in the King James Version."),
])
def test_remark_says_that_the_passage_is_not_there(text_id, play, reference, remark):
    assert says_not_there(text_id, play, reference, remark)


@pytest.mark.parametrize("text_id, play, reference, remark", [
    ("us_constitution", None, "Article V, Section 2", "If Article V, Section 2 does not exist, please tell me."),
    ("us_constitution", None, "Article V, Section 2", "I cannot verify whether the passage does not exist."),
    ("us_constitution", None, "Article V, Section 2", "Article IV does not have a Section 5."),  # another place
    ("us_constitution", None, "Article V, Section 2", "The semicolon is not in the Constitution."),
    ("us_constitution", None, "Article V, Section 2", "Article V, Section 2 of the Constitution."),
    ("us_constitution", None, "Article VIII", "The first of only nine articles."),  # more than eight
    ("bible_kjv", None, "Jude 1:26", "Jude 1:26 (KJV)"),
    ("bible_kjv", None, "Jude 1:26", "Verse numbers are not in the King James Version of 1611."),
    ("pride_prejudice", None, "the first sentence of Chapter 62", "There is no line in Pride and Prejudice more famous than this."),
    ("shakespeare", "Hamlet", "", "The words are from Polonius, not from Hamlet."),
    ("shakespeare", "Hamlet", "", "These words are spoken by Horatio, not Hamlet."),
    ("shakespeare", "Macbeth", "", "This is not a line of Macbeth himself; the witches say it."),
    ("shakespeare", "Hamlet", "", "This is the exact line from Hamlet."),
    ("shakespeare", "Hamlet", "the first line of Act 2, Scene 4", ""),
])
def test_remark_does_not_say_that_the_passage_is_missing(text_id, play, reference, remark):
    assert not says_not_there(text_id, play, reference, remark)


def test_nonexistence_is_also_read_in_the_location_and_in_brackets_but_not_in_the_quote():
    ask = ("us_constitution", None, "Article VIII", "")
    assert says_not_there(*ask, location="Article VIII does not exist")
    assert says_not_there(*ask, quote="[There is no Article VIII] The judicial Power")
    assert not says_not_there(*ask, quote="There is no Article VIII")
    # that the line is from elsewhere is SOURCE_CORRECTED there, not a second flag
    assert not says_not_there("shakespeare", "Hamlet", "", "", location="This line does not appear in Hamlet.")


# --- Bible references ------------------------------------------------------------------------


def verses(location):
    _, units, _ = load_index("bible_kjv")
    loc = parse_bible(location)
    return loc and [f"{units[i]['book_code']} {units[i]['chapter']}:{units[i]['verse']}" for i in resolve("bible_kjv", loc, units)]


@pytest.mark.parametrize("location, expected", [
    ("Jude 3", ["JUD 1:3"]), ("Jude 3-4", ["JUD 1:3", "JUD 1:4"]), ("Jude verse 3", ["JUD 1:3"]),
    ("Jude 1:3", ["JUD 1:3"]), ("3 John 4", ["3JN 1:4"]), ("Jude 3:5", []), ("Jude 26", []),
    ("Proverbs 3:5—6", ["PRO 3:5", "PRO 3:6"]), ("Proverbs 3:5–6", ["PRO 3:5", "PRO 3:6"]),
    ("Proverbs 3:5, 6", ["PRO 3:5", "PRO 3:6"]), ("Proverbs 3:5 and 6", ["PRO 3:5", "PRO 3:6"]),
    ("Proverbs 3:5, 7-8", ["PRO 3:5", "PRO 3:7", "PRO 3:8"]),
    ("John 3:35-4:2", ["JHN 3:35", "JHN 3:36", "JHN 4:1", "JHN 4:2"]),
    ("John 3:16, 4:2", ["JHN 3:16"]), ("John 3:16; 2 Corinthians 1:3", ["JHN 3:16"]), ("Psalm 23:1, 1611 edition", ["PSA 23:1"]),
])
def test_bible_references(location, expected):
    assert verses(location) == expected


def test_whole_chapters_of_the_bible():
    assert len(verses("Jude 1")) == 25 and len(verses("John 3")) == 36 and verses("Proverbs 32") == []
    assert len(verses("John 3-4")) == 36 + 54 and verses("John 3-99") == []


def test_a_range_must_exist_however_long_it_is():
    assert len(verses("John 3:1-36")) == 36  # real, so allowed
    for location in ("John 3:1-999", "John 3:30-40", "John 3:0-16", "John 3:17-16", "John 3:16, 99", "John 3:16-22:1",
                     "Genesis 1:1-99:1"):
        assert not bible_place_exists(parse_bible(location)) and verses(location) == [], location
        assert location_correct("bible_kjv", location, [{"book_code": "JHN", "chapter": 3, "verse": 16}]) is False
    assert location_correct("bible_kjv", "John 3:1-36", [{"book_code": "JHN", "chapter": 3, "verse": 16}]) is True


# --- other references -----------------------------------------------------------------------


def test_amendments_headed_article():
    for location in ("Article XIV of the Amendments, Section 1", "Article XIV, Section 1 of the Amendments"):
        assert parse_constitution(location) == {"part": "amendment", "amendment": 14, "section": 1}
    assert parse_constitution("Article V, on the amendment process") == {"part": "article", "article": 5}


@pytest.mark.parametrize("location, chapter", [
    ("Volume Two, Chapter 11", 34), ("Chapter 11 of the second volume", 34), ("Volume the Second, Chapter 11", 34),
    ("Volume Two, Chapter Eleven", 34), ("Chapter Twenty-two", 22), ("Chapter 34 of the second volume", 34),
])
def test_numbers_in_words(location, chapter):
    assert parse_chapter(location, "pride_prejudice") == {"chapter": chapter}


def test_a_fourth_volume_does_not_exist():
    assert parse_chapter("Chapter 11 of the fourth volume", "pride_prejudice") == {"chapter": -1}


def test_a_prologue_that_is_denied_is_no_prologue():
    assert parse_play("Act 3, Scene 1 (not the prologue)") == {"act": 3, "scene": 1}
    assert parse_play("Act 3, Scene 1, not in the Chorus") == {"act": 3, "scene": 1}
    assert parse_play("Act 2, Prologue") == {"act": 2, "scene": 0}


def test_every_matched_unit_must_be_in_the_stated_place():
    units = [{"act": 3, "scene": 1}, {"act": 3, "scene": 2}]
    assert [check_play({"act": 3, "scene": 1}, u) for u in units] == [True, False]
    assert location_correct("shakespeare", "Act 3, Scene 1", units) is False
    assert location_correct("shakespeare", "Act 3", units) is True
    assert location_correct("shakespeare", "Act 3, Scene 1", units[:1]) is True
    assert location_correct("shakespeare", "Act 3, Scene 1", []) is None
    assert location_correct("shakespeare", "somewhere", units) is None
