from quotebench.textutil import clean_ws, split_sentences


def test_clean_ws():
    assert clean_ws("  a\n\tb  c­ d ") == "a b c d"


def test_split_honorifics_and_dialogue():
    p = "“My dear Mr. Bennet,” said his lady to him one day, “have you heard that Netherfield Park is let at last?” Mr. Bennet replied that he had not."
    assert split_sentences(p, "en") == [
        "“My dear Mr. Bennet,” said his lady to him one day, “have you heard that Netherfield Park is let at last?”",
        "Mr. Bennet replied that he had not.",
    ]


def test_split_question_inside_quote_followed_by_lowercase():
    assert len(split_sentences("“Is he married?” said she. “Yes.”", "en")) == 2


def test_split_initials_and_pronoun_i():
    assert len(split_sentences("When on board H.M.S. ‘Beagle,’ I sailed. Then I rested.", "en")) == 2
    assert split_sentences("So said I. Then we left.", "en") == ["So said I.", "Then we left."]


def test_split_russian_dialogue():
    p = "— Ах! — сказала она. — Пойдём домой. А. С. Пушкин написал это, т. е. давно."
    assert split_sentences(p, "ru") == [
        "— Ах! — сказала она.",
        "— Пойдём домой.",
        "А. С. Пушкин написал это, т. е. давно.",
    ]
