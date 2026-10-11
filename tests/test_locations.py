from quotebench.locations import (
    location_correct, parse_bible, parse_chapter, parse_constitution, parse_play,
)


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
