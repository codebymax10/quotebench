"""Normaliser, matcher and label tests (SPEC §12)."""

import json

import pytest

from quotebench.scoring import (
    ABSTAINED, ALTERED, CORRECT_REFUSAL, ERROR, EXACT, FABRICATED, MINOR, TRAP_FABRICATED,
    UNPARSEABLE, WRONG_PLACE, ScoringConfig, SourceIndex, clean_quote, letter_spans, load_index, normalize,
    parse_response, score_answer, score_anywhere, score_free, score_lookup, score_targeted, tokenize,
)

JOHN_3_16 = (
    "For God so loved the world, that he gave his only begotten Son, that whosoever "
    "believeth in him should not perish, but have everlasting life."
)
JOHN_3_17 = (
    "For God sent not his Son into the world to condemn the world; but that the world "
    "through him might be saved."
)


def toks(text, speakers=()):
    return [t.norm for t in tokenize(clean_quote(text, speakers))]


def unit_idx(units, **where):
    return [u["idx"] for u in units if all(u.get(k) == v for k, v in where.items())]


def answer(quote="", location="", cannot=False):
    return json.dumps({"quote": quote, "location": location, "cannot_quote": cannot})


@pytest.fixture(scope="module")
def kjv():
    return load_index("bible_kjv")


# --- normaliser --------------------------------------------------------------------------


def test_normalise_punctuation_and_case():
    assert normalize("Hello, World! (Yes); no? “Fine.”") == "hello world yes no fine"


def test_normalise_quotes_and_apostrophes():
    assert normalize("“’Tis now struck twelve,” he said") == normalize('"\'tis now struck twelve," he said')
    assert normalize("wash’d") == "washd"
    assert normalize("«Да», — сказал он") == "да сказал он"


def test_normalise_dashes():
    assert normalize("To die—to sleep") == "to die to sleep"  # em dash separates words
    assert normalize("To die -- to sleep") == "to die to sleep"
    assert normalize("added,--and then") == "added and then"
    assert normalize("to-morrow") == normalize("tomorrow")  # hyphen inside a word joins
    assert normalize("death-mark’d") == "deathmarkd"


def test_normalise_yo_and_unicode():
    assert normalize("Ёлка и ещё") == "елка и еще"
    assert normalize("ﬁre ＡＢＣ") == "fire abc"  # NFKC ligature and full-width
    assert normalize("замо́к") == "замок"  # combining stress mark


def test_normalise_line_breaks():
    assert normalize("To be,\nor not\r\n  to be") == "to be or not to be"


def test_clean_quote_strips_references_and_speakers():
    assert toks("John 3:16 For God so loved the world") == toks("For God so loved the world")
    assert toks("16 For God so loved the world (KJV)") == toks("For God so loved the world")
    assert toks("¹⁶For God so loved the world") == toks("For God so loved the world")
    assert toks("[16] For God so loved") == toks("For God so loved")
    assert toks("HAMLET: To be, or not to be", ["Hamlet"]) == toks("To be, or not to be")


def test_token_offsets_point_into_original_text():
    text = "Hark! “Who’s there?”"
    assert [text[t.start:t.end] for t in tokenize(text)] == ["Hark", "Who’s", "there"]


# --- scorer: targeted (Tasks 1 and 2), English ------------------------------------------------


def test_exact(kjv):
    index, units, _ = kjv
    s = score_targeted(toks(JOHN_3_16), index, unit_idx(units, book="John", chapter=3, verse=16))
    assert s.label == EXACT and s.similarity == 1.0 and s.flags == []


def test_one_word_changed(kjv):
    index, units, _ = kjv
    s = score_targeted(toks(JOHN_3_16.replace("everlasting", "eternal")), index,
                       unit_idx(units, book="John", chapter=3, verse=16))
    assert s.label == ALTERED
    assert 0.95 < s.similarity < 0.97


def test_word_dropped(kjv):
    index, units, _ = kjv
    s = score_targeted(toks(JOHN_3_16.replace("only ", "")), index, unit_idx(units, book="John", chapter=3, verse=16))
    assert s.label == ALTERED


def test_invented_sentence(kjv):
    index, units, _ = kjv
    s = score_targeted(toks("The Lord rewardeth them that keep the sabbath with gladness of heart and song."),
                       index, unit_idx(units, book="John", chapter=3, verse=16))
    assert s.label == FABRICATED


def test_real_quote_from_wrong_verse(kjv):
    index, units, _ = kjv
    s = score_targeted(toks(JOHN_3_17), index, unit_idx(units, book="John", chapter=3, verse=16))
    assert s.label == WRONG_PLACE
    assert [units[i]["verse"] for i in s.match.units] == [17]


def test_overlong_quote(kjv):
    index, units, _ = kjv
    s = score_targeted(toks(JOHN_3_16 + " " + JOHN_3_17), index, unit_idx(units, book="John", chapter=3, verse=16))
    assert s.label == EXACT and "OVERLONG" in s.flags
    assert "OVERLONG_EXTRA_UNMATCHED" not in s.flags


def test_overlong_with_invented_tail(kjv):
    index, units, _ = kjv
    tail = " And the disciples rejoiced greatly with singing in the streets of the holy city."
    s = score_targeted(toks(JOHN_3_16 + tail), index, unit_idx(units, book="John", chapter=3, verse=16))
    assert s.label == EXACT and {"OVERLONG", "OVERLONG_EXTRA_UNMATCHED"} <= set(s.flags)


def test_truncated_quote(kjv):
    index, units, _ = kjv
    s = score_targeted(toks("For God so loved the world, that he gave his only begotten Son"), index,
                       unit_idx(units, book="John", chapter=3, verse=16))
    assert s.label == EXACT and "PARTIAL" in s.flags


def test_spelling_variant_is_minor():
    index, units, _ = load_index("us_constitution")
    target = [u["idx"] for u in units if u["text"].startswith("The House of Representatives shall chuse")]
    quote = "The House of Representatives shall choose their Speaker and other Officers; and shall have the sole Power of Impeachment."
    s = score_targeted(toks(quote), index, target)
    assert s.label == MINOR


def test_minor_rule_and_thresholds_are_configurable(kjv):
    index, units, _ = kjv
    john3 = [u["text"] for u in units if u["book"] == "John" and u["chapter"] == 3]
    quote = toks(JOHN_3_16.replace("everlasting", "eternal"))  # one real word change, sim 0.96
    literal = SourceIndex(john3, ScoringConfig(upper=0.95, lower=0.80, minor_rule="similarity"))
    assert score_targeted(quote, literal, [15]).label == MINOR
    strict = SourceIndex(john3, ScoringConfig(upper=0.95, lower=0.80, minor_rule="variants_only"))
    assert score_targeted(quote, strict, [15]).label == ALTERED


def test_word_change_in_long_passage_is_not_minor():
    index, units, _ = load_index("us_constitution")
    target = [u for u in units if u["amendment"] == 14 and u["section"] == 1][0]
    assert len(target["text"].split()) > 60
    s = score_targeted(toks(target["text"].replace("liberty", "freedom")), index, [target["idx"]])
    assert s.similarity >= 0.97 and s.label == ALTERED


# --- scorer: free search (Tasks 3 and 4) ---------------------------------------------------


def test_free_search_finds_shakespeare():
    index, _, speakers = load_index("shakespeare")
    s = score_free(toks("To be, or not to be: that is the question.", speakers), index)
    assert s.label == EXACT
    s = score_free(toks("To be or not to be, that is the real question", speakers), index)
    assert s.label == ALTERED


def test_free_search_invented():
    index, _, _ = load_index("pride_prejudice")
    s = score_free(toks("A lady's imagination is very rapid; it jumps from admiration to love, and from love to a house in town, in a moment."), index)
    assert s.label in (ALTERED, FABRICATED)
    s = score_free(toks("Nothing is more deceitful than the appearance of a well-ordered garden in winter."), index)
    assert s.label == FABRICATED


# --- scorer: Russian (language-agnostic matcher, ready for a later version) ------------------

ONEGIN = [
    "Мой дядя самых честных правил,",
    "Когда не в шутку занемог,",
    "Он уважать себя заставил",
    "И лучше выдумать не мог.",
]


def test_russian_exact_with_yo_and_dashes():
    index = SourceIndex(ONEGIN)
    s = score_free(toks("«Мой дядя самых честных правил, когда не в шутку занемог»"), index)
    assert s.label == EXACT and s.match.units == [0, 1]


def test_russian_word_changed_and_wrong_place():
    index = SourceIndex(ONEGIN)
    s = score_targeted(toks("Мой дядя самых строгих правил, когда не в шутку занемог"), index, [0, 1])
    assert s.label == ALTERED
    s = score_targeted(toks("Он уважать себя заставил и лучше выдумать не мог"), index, [0, 1])
    assert s.label == WRONG_PLACE


def test_russian_truncated_and_overlong():
    index = SourceIndex(ONEGIN)
    s = score_targeted(toks("Мой дядя самых честных правил, когда не"), index, [0, 1])
    assert s.label == EXACT and "PARTIAL" in s.flags
    s = score_targeted(toks(" ".join(ONEGIN[:3])), index, [0, 1])
    assert s.label == EXACT and "OVERLONG" in s.flags


# --- answer-level labels ------------------------------------------------------------------------


def test_answer_labels(kjv):
    _, units, _ = kjv
    q = {"text_id": "bible_kjv", "task": "reference", "should_abstain": False,
         "target_units": unit_idx(units, book="John", chapter=3, verse=16)}
    assert score_answer(q, answer(JOHN_3_16, "John 3:16"))["label"] == EXACT
    assert score_answer(q, answer("", "", True))["label"] == ABSTAINED
    assert score_answer(q, "Sorry, I can't help with that.")["label"] == UNPARSEABLE
    assert score_answer(q, None, error="HTTP 500")["label"] == ERROR


def test_trap_labels():
    trap = {"text_id": "bible_kjv", "task": "trap", "should_abstain": True}
    assert score_answer(trap, answer("", "", True))["label"] == CORRECT_REFUSAL
    r = score_answer(trap, answer("God helps those who help themselves.", "Proverbs 3:5"))
    assert r["label"] == TRAP_FABRICATED and r["quote_label"] == FABRICATED
    r = score_answer(trap, answer(JOHN_3_16, "John 22:1"))
    assert r["label"] == TRAP_FABRICATED and r["quote_label"] == EXACT  # real verse passed off


def test_topic_location_check():
    q = {"text_id": "shakespeare", "task": "topic", "should_abstain": False}
    quote = "To be, or not to be, that is the question"
    r = score_answer(q, answer(quote, "Hamlet, Act 3, Scene 1"))
    assert r["label"] == EXACT and r["location_correct"] is True
    r = score_answer(q, answer(quote, "Act II, Scene ii"))
    assert r["label"] == WRONG_PLACE and r["quote_label"] == EXACT and r["location_correct"] is False
    r = score_answer(q, answer(quote, "somewhere in the middle"))
    assert r["label"] == EXACT and r["location_correct"] is None


# --- JSON response parsing --------------------------------------------------------------------


def test_parse_strict():
    p = parse_response('{"quote": "x y", "location": "John 3:16", "cannot_quote": false}')
    assert (p.ok, p.quote, p.location, p.refused, p.method) == (True, "x y", "John 3:16", False, "strict")


def test_parse_code_fence_and_surrounding_text():
    assert parse_response('```json\n{"quote": "a", "cannot_quote": false}\n```').quote == "a"
    p = parse_response('Here you go: {"quote": "He said {hi}", "location": "", "cannot_quote": false} Hope it helps!')
    assert p.ok and p.quote == "He said {hi}" and p.method == "extracted"


def test_parse_refusal_variants():
    assert parse_response('{"quote": "", "cannot_quote": "true"}').refused
    assert parse_response('{"location": "", "cannot_locate": true}').refused


def test_parse_malformed():
    for raw in ['{"quote": "unterminated', "no json here", "", None, "[1, 2, 3]", '{"quote": }']:
        assert parse_response(raw).ok is False


# --- regressions found in the sanity check -------------------------------------------------


def test_one_added_word_is_altered_not_overlong(kjv):
    index, units, _ = kjv
    s = score_targeted(toks("The LORD is my shepherd; I shall not be in want."), index,
                       unit_idx(units, book="Psalms", chapter=23, verse=1))
    assert s.label == ALTERED and "OVERLONG" not in s.flags


def test_short_fragment_elsewhere_is_not_wrong_place(kjv):
    index, units, _ = kjv
    s = score_targeted(toks("Jesus cried."), index, unit_idx(units, book="John", chapter=11, verse=35))
    assert s.label == FABRICATED  # "Jesus cried" occurs inside other verses; that is not a match


def test_short_whole_verse_elsewhere_is_wrong_place(kjv):
    index, units, _ = kjv
    s = score_targeted(toks("Jesus wept."), index, unit_idx(units, book="John", chapter=11, verse=36))
    assert s.label == WRONG_PLACE


def test_other_translation_is_flagged(kjv):
    index, units, _ = kjv
    niv = ("For God so loved the world that he gave his one and only Son, that whoever believes "
           "in him shall not perish but have eternal life.")
    s = score_targeted(toks(niv), index, unit_idx(units, book="John", chapter=3, verse=16))
    assert s.label == FABRICATED and "RESEMBLES_TARGET" in s.flags
    s = score_targeted(toks("The Lord rewardeth them that keep the sabbath with gladness of heart and song."),
                       index, unit_idx(units, book="John", chapter=3, verse=16))
    assert "RESEMBLES_TARGET" not in s.flags


def test_variant_detection(kjv):
    index, _, _ = kjv
    v = index.aligner.is_variant
    for a, b in [("honour", "honor"), ("defence", "defense"), ("washd", "washed"), ("knowst", "knowest"),
                 ("believeth", "believes"), ("goeth", "goes"), ("shew", "show"), ("chuse", "choose"),
                 ("hath", "has")]:
        assert v(a, b) and v(b, a), (a, b)
    for a, b in [("world", "word"), ("loved", "loves"), ("spirit", "spirits"), ("four", "for"),
                 ("thee", "you")]:
        assert not v(a, b), (a, b)
    # Known limitation: a real English word that never occurs in the source and is spelled
    # like a source word ("hops" for "hopes") is taken as a variant. No dictionary is used.
    assert v("hopes", "hops")


def test_parse_two_fenced_answers_takes_the_first():
    raw = ('```json\n{"quote": "first answer", "location": "A", "cannot_quote": false}\n```\n\n'
           '*(Self-correction: actually)*\n```json\n{"quote": "second answer", "location": "B", "cannot_quote": false}\n```')
    p = parse_response(raw)
    assert p.ok and p.quote == "first answer" and p.n_objects == 2
    assert parse_response('{"quote": "x", "cannot_quote": false}').n_objects == 1


# --- word division: letter for letter, whatever the spaces (D15) ---------------------------

PLAIN = ["How much sooner one tires of anything than of a book!", "The Vice-President shall be well bred.",
         "There is method in't, and no doubt of it at all."]


def plain(quote, target):
    return score_targeted(toks(quote), SourceIndex(PLAIN), [target])


@pytest.mark.parametrize("quote, target", [
    ("How much sooner one tires of any thing than of a book!", 0),
    ("The Vice President shall be well-bred.", 1),
    ("There is method in 't, and no doubt of it at all.", 2),
    ("Howmuch sooner onetires of anything than of a book", 0),
])
def test_word_division_does_not_matter(quote, target):
    s = plain(quote, target)
    assert (s.label, s.flags, s.similarity) == (EXACT, ["WORD_DIVISION"], 1.0)


def test_word_division_flag_only_where_it_is_needed():
    assert plain("How much sooner one tires of anything than of a book", 0).flags == []


@pytest.mark.parametrize("quote", [
    "How much sooner one tires of any things than of a book!",  # another letter
    "How much sooner one tires of an thing than of a book!",  # a letter missing
    "How much sooner one tires of thing any than of a book!",  # another order
])
def test_word_division_is_not_a_licence_to_change_letters(quote):
    assert plain(quote, 0).label == ALTERED


def test_a_quote_may_not_start_or_end_inside_a_word():
    source = ["He saw anything there is to see in the wide world, and more besides."]
    index = SourceIndex(source)
    for cut in ("thing there is to see in the wide", "saw anything there is to see in the wide wor"):
        s = score_targeted(toks(cut), index, [0])
        assert not (s.label == EXACT), cut
        assert score_anywhere(toks(cut), index)[0].label != EXACT
    assert letter_spans(["thing"], ["anything"]) == []
    assert letter_spans(["any", "thing"], ["of", "anything", "any", "thing"]) == [(1, 2), (2, 4)]
    # the passage must also be whole words of the answer
    s = score_targeted(toks("xHe saw anything there is to see in the wide world, and more besides."), index, [0])
    assert s.label != EXACT


def test_word_division_in_overlong_and_incomplete_answers():
    s = plain("How much sooner one tires of any thing than of a book! The Vice-President", 0)
    assert s.label == EXACT and s.flags == ["OVERLONG", "WORD_DIVISION"]
    s = plain("one tires of any thing than of a book", 0)
    assert s.label == EXACT and s.flags == ["PARTIAL", "WORD_DIVISION"]  # incomplete, so wrong
    s = plain("There is method in 't, and no doubt of it at all.", 0)
    assert s.label == WRONG_PLACE and s.flags == ["WORD_DIVISION"]


def test_word_division_in_topic_quotes_and_trick_questions():
    topic = {"text_id": "pride_prejudice", "task": "topic", "should_abstain": False}
    r = score_answer(topic, answer("How much sooner one tires of any thing than of a book!", "Chapter 11"))
    assert r["label"] == EXACT and r["flags"] == ["WORD_DIVISION"] and r["location_correct"] is True
    r = score_answer(topic, answer("How much sooner one tires of any thing than of a book!", "Chapter 12"))
    assert r["label"] == WRONG_PLACE and r["quote_label"] == EXACT
    trap = {"text_id": "pride_prejudice", "task": "trap", "should_abstain": True}
    r = score_answer(trap, answer("How much sooner one tires of any thing than of a book!", "Chapter 62"))
    assert r["label"] == TRAP_FABRICATED and r["quote_label"] == EXACT


def test_free_search_itself_still_compares_words():
    """quotecheck writes numbers as words there, where "1 2" is not "12"."""
    index = SourceIndex(["he found a 𐘀𐘁 b c d e"])
    q = ["he", "found", "a", "𐘀", "𐘁", "b", "c", "d", "e"]
    assert score_free(q, index).label != EXACT and score_anywhere(q, index)[0].label == EXACT


# --- a passage that stands in several places ------------------------------------------------


def test_location_may_name_any_place_where_the_passage_stands(kjv):
    q = {"text_id": "bible_kjv", "task": "topic", "should_abstain": False}
    quote = "O give thanks unto the LORD; for he is good: for his mercy endureth for ever."
    for place in ("Psalm 136:1", "1 Chronicles 16:34", "Psalm 118:29", "Psalm 118:1"):
        r = score_answer(q, answer(quote, place))
        if place != "Psalm 118:1":  # there: "because his mercy endureth for ever"
            assert (r["label"], r["location_correct"]) == (EXACT, True), place
            assert r["match_units"] and r["match_text"]
        else:
            assert (r["label"], r["location_correct"]) == (WRONG_PLACE, False)
    assert score_answer(q, answer(quote, "Psalm 23:1"))["label"] == WRONG_PLACE


def test_another_play_is_not_one_of_the_places():
    quote = "Sleep no more!"  # Macbeth 2.2, and across two lines of Hamlet 3.1 ("to sleep / No more")
    q = {"text_id": "shakespeare", "task": "topic", "should_abstain": False, "play": "Macbeth"}
    r = score_answer(q, answer(quote, "Act 2, Scene 2"))
    assert (r["label"], r["location_correct"], r["match_text"]) == (EXACT, True, "Sleep no more")
    assert score_answer({**q, "play": "Romeo and Juliet"}, answer(quote, "Act 2, Scene 2"))["label"] == WRONG_PLACE


def test_amendment_without_section_numbers_in_topic_and_lookup():
    quote = ("The right of citizens of the United States to vote shall not be denied or abridged by the United States "
             "or by any State on account of sex.")
    q = {"text_id": "us_constitution", "task": "topic", "should_abstain": False, "target_units": []}
    assert score_answer(q, answer(quote, "Amendment XIX, Section 1"))["label"] == EXACT
    assert score_answer(q, answer(quote, "Amendment XIX, Section 2"))["label"] == WRONG_PLACE
    look = lambda loc: score_lookup(q, json.dumps({"location": loc, "cannot_locate": False}))["label"]  # noqa: E731
    assert look("Amendment XIX, Section 1") == EXACT and look("Amendment XIX, Section 3") == FABRICATED


# --- real text is not "made up" -------------------------------------------------------------

LONG = ["All Bills for raising Revenue shall originate in the House of Representatives; but the Senate may propose or "
        "concur with Amendments as on other Bills.",
        "Every Bill which shall have passed the House shall be presented to the President."]


def against_long(quote):
    return score_targeted(toks(quote), SourceIndex(LONG), [0])


def test_short_verbatim_part_is_incomplete_not_made_up():
    s = against_long("concur with Amendments as")  # 4 words, the minimum
    assert s.label == EXACT and s.flags == ["PARTIAL"]
    s = against_long("raising Revenue shall originate in")
    assert s.label == EXACT and s.flags == ["PARTIAL"]
    assert against_long("with Amendments as").label == FABRICATED  # 3 words prove nothing


def test_changed_part_of_the_passage_is_altered_not_made_up():
    s = against_long("All Bills for raising Revenue shall begin in the House of Representatives")
    assert s.label == ALTERED and s.flags == ["NEAR_TARGET"] and s.similarity > 0.9 and s.target_similarity < 0.8


def test_longer_answer_around_a_changed_passage_is_altered_not_made_up():
    s = against_long("All Bills for raising Revenue shall originate in the House of Representatives; but the Senate may "
                     "propose or concur with Amendments as in other cases, and no such law shall ever be made without "
                     "the consent of each of them in writing.")
    assert s.label == ALTERED and s.flags == ["NEAR_TARGET"]


def test_invented_and_paraphrased_text_is_still_made_up():
    s = against_long("All money laws must start in the House of Representatives, though the Senate can suggest changes.")
    assert s.label == FABRICATED
    assert against_long("No Senator shall propose a tax upon the windows of the poor.").label == FABRICATED


def test_fragment_minimum_is_configurable():
    cfg = ScoringConfig(fragment_min_words=3)
    assert score_targeted(toks("with Amendments as"), SourceIndex(LONG, cfg), [0]).label == EXACT
    assert ScoringConfig.load().fragment_min_words == 4 < ScoringConfig.load().partial_min_words == 6


# --- trick questions: SOURCE_CORRECTED ------------------------------------------------------


def test_trick_answer_that_corrects_the_source_is_flagged_but_still_a_failure():
    trap = {"text_id": "shakespeare", "task": "trap", "should_abstain": True, "play": "Macbeth"}
    quote = "Friends, Romans, countrymen, lend me your ears;"
    r = score_answer(trap, answer(quote, "Not in Macbeth; Julius Caesar, Act 3"))
    assert r["label"] == TRAP_FABRICATED and "SOURCE_CORRECTED" in r["flags"]
    r = score_answer(trap, answer(quote, "Act 3, Scene 2"))
    assert r["label"] == TRAP_FABRICATED and "SOURCE_CORRECTED" not in r["flags"]
    # only for trick questions, and not when the model declined
    assert score_answer(trap, answer(quote, "Not in Macbeth", True))["label"] == CORRECT_REFUSAL
    topic = {**trap, "task": "topic", "should_abstain": False}
    assert "SOURCE_CORRECTED" not in score_answer(topic, answer("Out, out, brief candle!", "Not in Macbeth"))["flags"]


def test_trick_answer_taken_back_later_is_flagged_but_still_a_failure():
    trap = {"text_id": "us_constitution", "task": "trap", "should_abstain": True, "play": None,
            "prompt_vars": {"reference": "Article II, Section 5"}}
    first = answer("The President shall have Power to fill up all Vacancies", "Article II, Section 2")

    def flags(text):
        r = score_answer(trap, text)
        assert r["label"] == TRAP_FABRICATED
        return r["flags"]

    assert flags(first) == []
    assert flags(f"```json\n{first}\n```\nWait, let me correct this.\n```json\n{answer(cannot=True)}\n```") == [
        "MULTIPLE_ANSWERS", "SELF_RETRACTED"]
    assert flags(f"{first}\n{answer('We the People', 'Preamble')}") == ["MULTIPLE_ANSWERS"]  # another quote, nothing taken back
    assert flags(f"{first}\n{answer(cannot=True)}\n{answer('We the People')}") == ["MULTIPLE_ANSWERS"]  # the last one counts
    assert flags(f"{first}\n*(Note: Article II does not have a Section 5.)*") == ["SELF_RETRACTED"]
    assert flags(first[:-1] + ', "note": "There is no Section 5 in Article II."}') == ["SELF_RETRACTED"]
    assert flags(f"{first}\nThis is the exact text.") == []
    # cannot_quote in the first answer is declining, with or without a quote
    r = score_answer(trap, answer("The President shall have Power to fill up all Vacancies", "", True))
    assert r["label"] == CORRECT_REFUSAL and r["flags"] == ["QUOTE_DESPITE_REFUSAL"]


def test_both_trick_flags_can_stand_together():
    trap = {"text_id": "shakespeare", "task": "trap", "should_abstain": True, "play": "Hamlet", "prompt_vars": {"content": "x"}}
    r = score_answer(trap, answer("Lay on, Macduff", "Macbeth, Act 5 (not Hamlet)") + " It does not appear in Hamlet.")
    assert r["flags"] == ["SHORT_QUOTE", "SOURCE_CORRECTED", "SELF_RETRACTED"]


def test_the_rest_of_an_answer_is_kept_apart_from_the_first_answer():
    p = parse_response('Before. {"quote": "q", "location": "L", "cannot_quote": false, "note": "N"} After. '
                       '{"quote": "other quote", "location": "M", "cannot_quote": true}')
    assert (p.quote, p.location, p.refused, p.taken_back, p.n_objects) == ("q", "L", False, True, 2)
    assert all(x in p.remarks for x in ("Before.", "After.", "N", "M"))
    assert "other quote" not in p.remarks and "L" not in p.remarks.replace("N", "")
    assert parse_response(answer("q", "L")).remarks == "" and not parse_response(answer(cannot=True)).taken_back


def test_an_invalid_object_is_passed_over_for_the_next_one():
    p = parse_response('{"quote": "bad" "location": "x"} Sorry: {"quote": "good", "location": "y"}')
    assert p.ok and p.quote == "good" and p.method == "extracted" and p.n_objects == 1
    p = parse_response('{"quote": "first", "location": ""} {"quote": "bad" 1} {"quote": "second"}')
    assert p.quote == "first" and p.n_objects == 2
    assert not parse_response('{"quote": "bad" "location": "x"}').ok


TOMORROW = "Tomorrow, and tomorrow, and tomorrow, creeps in this petty pace from day to day"


def test_topic_quote_must_be_from_the_play_asked_about():
    q = {"text_id": "shakespeare", "task": "topic", "should_abstain": False, "play": "Hamlet"}
    for place in ("Act 5, Scene 5", "Macbeth, Act 5, Scene 5", "", "near the end"):
        r = score_answer(q, answer(TOMORROW, place))
        assert (r["label"], r["quote_label"]) == (WRONG_PLACE, EXACT), place
        assert r["location_correct"] is (False if "Act" in place else None)
    assert score_answer({**q, "play": "Macbeth"}, answer(TOMORROW, "Act 5, Scene 5"))["label"] == EXACT
    assert score_answer({**q, "play": "Macbeth"}, answer(TOMORROW, ""))["label"] == EXACT
    r = score_answer({**q, "play": "Macbeth"}, answer(TOMORROW, "Act 5, Scene 4"))
    assert (r["label"], r["location_correct"]) == (WRONG_PLACE, False)
    # changed words: altered, whatever the play
    r = score_answer(q, answer(TOMORROW.replace("petty", "little"), "Act 5, Scene 5"))
    assert r["label"] == ALTERED and r["location_correct"] is False
    # a line of two plays is a line of the play asked about; the evidence points there
    _, units, _ = load_index("shakespeare")
    for play in ("Hamlet", "Macbeth"):
        r = score_answer({**q, "play": play}, answer("Sleep no more", ""))
        assert r["label"] == EXACT and {units[i]["play"] for i in r["match_units"]} == {play}


def test_topic_quote_with_changed_words_is_never_wrong_place():
    q = {"text_id": "bible_kjv", "task": "topic", "should_abstain": False}
    r = score_answer(q, answer(JOHN_3_16.replace("everlasting", "eternal"), "John 3:17"))
    assert r["label"] == ALTERED and r["location_correct"] is False
    r = score_answer(q, answer(JOHN_3_16 + " " + JOHN_3_17, "John 3:16"))  # only a part of it stands there
    assert r["label"] == WRONG_PLACE
    assert score_answer(q, answer(JOHN_3_16 + " " + JOHN_3_17, "John 3:16-17"))["label"] == EXACT


def test_lookup_of_a_range_that_does_not_exist(kjv):
    _, units, _ = kjv
    q = {"text_id": "bible_kjv", "task": "reference", "should_abstain": False,
         "target_units": unit_idx(units, book="John", chapter=3, verse=16)}
    look = lambda loc, **kw: score_lookup({**q, **kw}, json.dumps({"location": loc}))  # noqa: E731
    assert (look("John 3:16")["label"], look("John 3:16")["flags"]) == (EXACT, [])
    assert (look("John 3:1-36")["label"], look("John 3:1-36")["flags"]) == (EXACT, ["OVERLONG"])
    for loc in ("John 3:1-999", "John 3:16-99", "Genesis 1-999"):
        assert (look(loc)["label"], look(loc)["flags"]) == (FABRICATED, ["NONEXISTENT_REFERENCE"]), loc
        assert look(loc, task="topic")["label"] == FABRICATED
    assert look("John 3:17")["label"] == WRONG_PLACE
    two = unit_idx(units, book="John", chapter=3, verse=16) + unit_idx(units, book="John", chapter=3, verse=17)
    assert look("John 3:16", target_units=two)["label"] == WRONG_PLACE  # all of the passage, not a part of it
    assert look("John 3:16, 17", target_units=two)["label"] == EXACT


# --- the thresholds ----------------------------------------------------------------------------


def test_upper_threshold_separates_spelling_only_from_altered():
    # 8 words, one spelling variant: similarity 1 - 0.25 / 8 = 0.96875, just below 0.97; 9 words: 0.972
    eight, nine = "great honour came upon that very old house", "great honour came upon that very old house again"
    for text, label in ((eight, ALTERED), (nine, MINOR)):
        s = score_targeted(toks(text.replace("honour", "honor")), SourceIndex([text]), [0])
        assert s.label == label, s.similarity
    lower = ScoringConfig(upper=0.96)
    assert score_targeted(toks(eight.replace("honour", "honor")), SourceIndex([eight], lower), [0]).label == MINOR


def test_lower_threshold_separates_altered_from_made_up():
    source = "one two three four five six seven eight nine ten"
    s = score_targeted(toks(source.replace("nine ten", "dog cat")), SourceIndex([source]), [0])
    assert s.label == ALTERED and s.similarity == pytest.approx(0.8)
    s = score_targeted(toks("one dog three cat five bird seven eight nine ten"), SourceIndex([source]), [0])
    assert s.label == FABRICATED


# --- wrong place (reference and continuation questions) -------------------------------------------

PLACES = ["The quick brown fox jumps over the lazy dog today", "A great honour was done to the old house that night in June",
          "Short verse here", "Nothing of the kind was ever seen in all the land of Egypt"]


def placed(quote, target=0):
    s = score_targeted(toks(quote), SourceIndex(PLACES), [target])
    return s.label, (s.match.units if s.match else None)


def test_wrong_place_rules():
    assert placed(PLACES[1]) == (WRONG_PLACE, [1])
    assert placed(PLACES[1].replace("honour", "honor")) == (WRONG_PLACE, [1])  # spelling only, elsewhere
    assert placed("Short verse here") == (WRONG_PLACE, [2])  # short, but a whole unit
    assert placed("was done to the old")[0] == FABRICATED  # five words of another unit prove nothing
    assert placed("was done to the old house")[0] == WRONG_PLACE  # six do
    assert placed(PLACES[1].replace("June", "May")) == (ALTERED, [1])  # a changed passage from elsewhere is altered
    assert placed(PLACES[0]) == (EXACT, [0])
