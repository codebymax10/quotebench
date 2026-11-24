"""quotecheck: finding the quotations in a text."""

import random

import pytest

from quotecheck import extract_quotes


def texts(s):
    return [q.text for q in extract_quotes(s)[0]]


def kinds(s):
    return [q.kind for q in extract_quotes(s)[0]]


@pytest.mark.parametrize("text, kind", [
    ('He said "one two three four five" and left.', "straight"),
    ("He said “one two three four five” and left.", "curly"),
    ("Er sagte „one two three four five“ und ging.", "curly"),
    ("Он сказал «one two three four five» и ушёл.", "guillemet"),
    ("Er sagte »one two three four five« und ging.", "guillemet"),
    ("Il dit « one two three four five » puis.", "guillemet"),
    ("He said 'one two three four five' and left.", "single"),
    ("He said ‘one two three four five’ and left.", "single"),
    ("Intro:\n\n> one two three four five\n\nMore.", "block"),
    ('("one two three four five").', "straight"),
    ('**"one two three four five"**', "straight"),
    ('said:"one two three four five"[1]', "straight"),
    ('word—"one two three four five"—word', "straight"),
    ("“one two three four five\" mixed marks", "curly"),
    ("”one two three four five” alike", "curly"),
    ('\\"one two three four five\\" escaped', "straight"),
])
def test_all_kinds_of_marks(text, kind):
    quotes, stray = extract_quotes(text)
    assert [(q.text.strip(), q.kind, q.closed) for q in quotes] == [("one two three four five", kind, True)]
    assert stray == 0
    assert text[quotes[0].start : quotes[0].end] == quotes[0].text


def test_apostrophes_are_not_quotes():
    assert texts("The tenants' duties and the landlord's rights don't end; 'tis the '90s, rock 'n' roll.") == []
    assert texts("It’s the tenants’ duty, ’tis true, and the ’90s weren’t kind.") == []
    assert texts("\"I don't think it's the tenants' job\"") == ["I don't think it's the tenants' job"]
    assert texts("‘I don’t think it’s the tenants’ job to pay’, he said.") == ["I don’t think it’s the tenants’ job to pay"]
    assert texts("'The tenants' duty to pay' is clear.") == ["The tenants' duty to pay"]


def test_nested_quotes_are_part_of_the_outer_quote():
    assert texts('“He said ‘yes, at once’ to me,” she wrote.') == ["He said ‘yes, at once’ to me,"]
    assert texts('"He said "yes" to me"') == ['He said "yes" to me']
    assert texts("«Он сказал „да“ и «нет» сразу»") == ["Он сказал „да“ и «нет» сразу"]
    assert texts("‘He said “yes, at once” to me’") == ["He said “yes, at once” to me"]
    assert texts('"outer \\"inner words\\" outer"') == ['outer \\"inner words\\" outer']
    assert texts("“outer “inner” outer”") == ["outer “inner” outer"]


def test_multi_paragraph_quotes():
    # the usual typography: every paragraph opens, only the last closes
    assert texts("“First paragraph.\n\n“Second paragraph.”\n\nThen “other”.") == \
        ["First paragraph.\n\n“Second paragraph.", "other"]
    assert texts('"First paragraph.\n\n"Second paragraph."\n\nThen "other".') == \
        ['First paragraph.\n\n"Second paragraph.', "other"]
    # opened once, closed two paragraphs later
    assert texts("“First paragraph.\n\nSecond.\n\nThird.” End") == ["First paragraph.\n\nSecond.\n\nThird."]
    assert texts('"First paragraph.\n\nSecond.\n\nThird." End') == ["First paragraph.\n\nSecond.\n\nThird."]
    assert texts("“They shall:\n1. pay rent\n2. keep clean”") == ["They shall:\n1. pay rent\n2. keep clean"]


def test_unclosed_mark_ends_with_its_paragraph_and_does_not_swallow_the_next():
    quotes, _ = extract_quotes("“Never closed here.\n\nNext paragraph has “a real one” in it.")
    assert [(q.text, q.closed) for q in quotes] == [("Never closed here.", False), ("a real one", True)]
    quotes, _ = extract_quotes('"Never closed, but "a real one" follows.')
    assert [(q.text, q.closed) for q in quotes] == [("Never closed, but", False), ("a real one", True)]
    quotes, _ = extract_quotes('- "never closed\n- "closed"')
    assert [(q.text, q.closed) for q in quotes] == [("never closed", False), ("closed", True)]


def test_stray_closing_marks_and_inches():
    quotes, stray = extract_quotes('stray” and another" mark, then “fine here”.')
    assert [q.text for q in quotes] == ["fine here"] and stray == 2
    assert extract_quotes('A 6" pipe, 5\'10" tall.') == ([], 0)


def test_block_quotes():
    assert texts("> line one\n> line two\n\nBetween.\n\n> other\n") == ["line one\nline two", "other"]
    assert texts("> para one\n>\n> para two") == ["para one\npara two"]
    assert texts(">> nested **bold**") == ["nested **bold**"]
    assert texts("- > in a list\n  > goes on\n- > second") == ["in a list\ngoes on", "second"]
    assert texts("> line one\r\n> line two\r\n") == ["line one\nline two"]
    assert texts("```\n> not a quote in code\n```") == []
    assert texts("> [!NOTE]\n> This is only a call-out box.") == []
    assert texts(">\n>\n") == []
    quotes, _ = extract_quotes("ab\n> cd ef\n> gh")
    assert (quotes[0].start, quotes[0].end) == (5, 15)


def test_block_quote_with_its_own_marks_and_attribution():
    assert texts('> "The words themselves." — Section 4') == ["The words themselves."]
    assert texts("> “The words themselves.”\n> — *Jane Austen*, 1813") == ["The words themselves."]
    assert texts('> **"The words themselves"** (Section 4)') == ["The words themselves"]
    assert texts('> "The first."\n>\n> "The second."') == ["The first.", "The second."]
    assert texts('> "The first."\n>\n> — Author') == ["The first."]
    # dialogue: marks inside the block do not delimit the quotation
    assert texts('> "Is he married?" she said. "Oh, single."') == ['"Is he married?" she said. "Oh, single."']
    q = extract_quotes("> The words themselves.\n> — Jane Austen")[0][0]
    assert q.text == "The words themselves.\n— Jane Austen" and q.without_attribution == "The words themselves."
    q = extract_quotes("> Он вошёл.\n> — Здравствуй, брат, как живёшь?")[0][0]
    assert q.without_attribution is None  # a spoken line, not an attribution


def test_quote_marks_in_html_attributes_are_ignored():
    assert texts('<a href="x" title="one two three four five">link</a> and "the quote"') == ["the quote"]


def test_quotes_do_not_cross_block_quotes():
    quotes, _ = extract_quotes("He wrote “never closed\n\n> block words\n\nand then it ends” here")
    assert [(q.text, q.kind, q.closed) for q in quotes] == \
        [("never closed", "curly", False), ("block words", "block", True)]


def test_random_text_never_crashes_and_positions_hold():
    rng = random.Random(7)
    alphabet = list("ab c.,’‘'\"“”„«»>\n\n\\…[]()*—-1<| ") + ["word ", "\n> ", "\r\n", " ", "```\n"]
    for _ in range(4000):
        s = "".join(rng.choice(alphabet) for _ in range(rng.randrange(60)))
        quotes, stray = extract_quotes(s)
        assert stray >= 0
        for a, b in zip(quotes, quotes[1:]):
            assert a.start <= a.end <= b.start, (s, quotes)
        for q in quotes:
            assert 0 <= q.start <= q.end <= len(s)
            if s[q.start : q.end] != q.text:  # only inside block quotes
                assert ">" in s, s
