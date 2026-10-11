"""Normaliser, matcher and label tests (SPEC §12)."""

import json

import pytest

from quotebench.scoring import (
    ABSTAINED, ALTERED, CORRECT_REFUSAL, ERROR, EXACT, FABRICATED, MINOR, TRAP_FABRICATED,
    UNPARSEABLE, WRONG_PLACE, ScoringConfig, SourceIndex, clean_quote, load_index, normalize,
    parse_response, score_answer, score_free, score_targeted, tokenize,
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
