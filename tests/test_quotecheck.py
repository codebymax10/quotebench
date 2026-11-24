"""quotecheck: checking quotations against a source, and the command line."""

import dataclasses
import io
import json
import random
import time
from pathlib import Path

import pytest

import quotecheck.core as core
from quotebench.scoring import ScoringConfig
from quotecheck import LABELS, Source, check
from quotecheck.cli import main

ROOT = Path(__file__).resolve().parents[1]
LEASE = (ROOT / "examples" / "lease.txt").read_text(encoding="utf-8")
ANSWER = (ROOT / "examples" / "answer.md").read_text(encoding="utf-8")
NOVEL = ROOT / "sources" / "raw" / "pride_prejudice" / "pg1342.txt"
RU = "Всё ещё шёл дождь.\nМой дядя самых честных правил, когда не в шутку занемог,\nон уважать себя заставил и лучше выдумать не мог."


@pytest.fixture(scope="module")
def lease():
    return Source.from_text(LEASE, language="en")


@pytest.fixture(scope="module")
def novel():
    return Source.from_file(NOVEL)


def one(text, source, **kw):
    report = check(text if text[0] in '"“«>' else f'"{text}"', source, **kw)
    assert len(report.quotes) == 1, report.quotes
    return report.quotes[0]


# --- labels -------------------------------------------------------------------------------


def test_spec_example(lease):
    report = check(ANSWER, lease)
    assert [q.label for q in report.quotes] == ["EXACT", "EXACT", "ALTERED", "FABRICATED"]
    assert report.counts == {"EXACT": 2, "MINOR": 0, "ALTERED": 1, "FABRICATED": 1}
    assert [s.text for s in report.skipped] == ["one cat"] and not report.all_exact
    for q in report.quotes:
        assert q.label in LABELS and 0 <= q.similarity <= 1
        assert lease.text[q.source_start : q.source_end] == q.best_match
    assert ANSWER[report.quotes[0].start : report.quotes[0].end] == report.quotes[0].text


def test_exact_ignores_case_punctuation_dashes_and_line_breaks(lease):
    q = one("THE LANDLORD may enter the apartment: to make repairs — but only, between nine in the morning", lease)
    assert q.label == "EXACT" and q.similarity == 1 and q.exact
    assert lease.text[q.source_start : q.source_end] == q.best_match
    assert q.best_match.startswith("The Landlord may enter") and q.best_match.endswith("in the morning")


@pytest.mark.parametrize("wrong", [
    "The Tenant may keep one cat or one large dog",  # changed
    "The Tenant may keep one cat or one dog",  # dropped
    "The Tenant may now keep one cat or one small dog",  # added
    "The Tenant may keep one small dog or one cat",  # order
    "The Tenant may not keep one cat or one small dog",
])
def test_any_word_change_is_not_exact(lease, wrong):
    q = one(wrong, lease)
    assert q.label in ("ALTERED", "FABRICATED") and q.similarity < 1


def test_spelling_variant_is_minor_in_english_only():
    text = "We honour the colour of every neighbour who comes to live in this quiet old street of ours"
    q = one(text.replace("honour", "honor"), Source.from_text(text))
    assert q.label == "MINOR" and not q.exact
    q = one(text.replace("honour", "honor"), Source.from_text(text, language="de"))
    assert q.label == "ALTERED"


def test_invented_quote_and_no_shared_word(lease):
    assert one("Pets are absolutely forbidden everywhere without exception", lease).label == "FABRICATED"
    q = one("zzz yyy xxx www vvv", lease)
    assert (q.label, q.similarity, q.best_match, q.source_start, q.source_end) == ("FABRICATED", 0.0, "", None, None)


def test_thresholds_change_the_split_but_never_exact(lease):
    altered = "The Tenant may keep one cat or one large dog"
    assert one(altered, lease, lower=0.95).label == "FABRICATED"
    assert one(altered, lease, lower=0.1, upper=0.2).label == "ALTERED"  # a word change is never MINOR
    assert one("The Tenant may keep one cat or one small dog", lease, lower=1, upper=1).label == "EXACT"


def test_benchmark_settings_are_used_unless_overridden():
    assert core.default_config() == ScoringConfig.load()


# --- numbers --------------------------------------------------------------------------------


@pytest.mark.parametrize("wrong", [
    "The Landlord shall return the deposit within 60 days",
    "a monthly rent of $1,540, due on the first day",
    "a monthly rent of $14,50, due on the first day",
    "a monthly rent of $, due on the first day",
    "late, and the Landlord may add a late fee of $400",  # at the very end of the quote
])
def test_changed_numbers_are_caught(lease, wrong):
    q = one(wrong, lease)
    assert not q.exact, q
    assert one(wrong, lease, compare_numbers=False).exact


def test_numbers_differ_flag(lease):
    assert one("return the deposit within 60 days after the Tenant", lease).flags == ["NUMBERS_DIFFER"]
    assert one("return the deposit in 30 days after the Tenant", lease).flags == []


def test_long_numbers_are_never_spelling_variants():
    s = Source.from_text("The company paid a total of 1000000 dollars to the city in that first year of the long new contract")
    q = one(s.text.replace("1000000", "1000001"), s)
    assert q.label == "ALTERED" and q.flags == ["NUMBERS_DIFFER"]


def test_number_formatting():
    s = Source.from_text("It sold 1,500 units in 2012–2015 at a rate of 2.5 per day and ½ per night, at 9:30.")
    assert one("It sold 1500 units in 2012-2015 at a rate", s).exact
    assert not one("It sold 1.500 units in 2012-2015 at a rate", s).exact
    assert not one("units in 2012-2015 at a rate of 25 per day", s).exact
    assert not one("per day and ¼ per night, at 9:30", s).exact
    assert not one("per day and ½ per night, at 9:45", s).exact
    assert one("per day and ½ per night, at 9:30", s).exact


def test_verse_numbers_can_be_ignored():
    s = Source.from_text("3:16 For God so loved the world.\n3:17 For God sent not his Son into the world.")
    quote = "For God so loved the world. For God sent not his Son"
    assert not one(quote, s).exact
    assert one(quote, s, compare_numbers=False).exact
    assert one("John 3:16 " + quote, s, compare_numbers=False).exact


# --- ellipses and brackets ------------------------------------------------------------------


@pytest.mark.parametrize("dots", ["...", "…", " . . . ", "[...]", "[…]", "(...)", "....", " […] "])
def test_ellipsis_parts_in_order_are_exact(lease, dots):
    q = one(f"The Tenant shall pay the Landlord{dots}due on the first day of each month", lease)
    assert q.label == "EXACT" and q.flags == ["ELLIPSIS"] and len(q.parts) == 2
    assert all(p.label == "EXACT" for p in q.parts)
    for p in q.parts:
        assert lease.text[p.source_start : p.source_end] == p.best_match
    assert q.source_start == q.parts[0].source_start and q.source_end == q.parts[1].source_end


def test_ellipsis_wrong_order_is_not_exact(lease):
    q = one("due on the first day of each month ... The Tenant shall pay the Landlord", lease)
    assert q.label == "ALTERED" and "OUT_OF_ORDER" in q.flags


def test_ellipsis_with_one_invented_or_altered_part(lease):
    q = one("The Tenant shall pay the Landlord ... and dance on the roof at midnight", lease)
    assert not q.exact and [p.label for p in q.parts] == ["EXACT", "FABRICATED"]
    q = one("The Tenant shall pay the Landlord ... due on the last day of each month", lease)
    assert q.label == "ALTERED" and [p.label for p in q.parts] == ["EXACT", "ALTERED"]


def test_ellipsis_uses_a_later_occurrence_if_the_first_is_out_of_order():
    s = Source.from_text("alpha beta gamma delta one. The red house stood there. Then alpha beta gamma delta two came.")
    q = one("The red house stood there … alpha beta gamma delta", s)
    assert q.exact and q.parts[1].source_start > q.parts[0].source_end


def test_leading_and_trailing_ellipsis(lease):
    assert one("...the Landlord may add a late fee...", lease).label == "EXACT"
    assert one("...the Landlord may add a late fee...", lease).parts == []


def test_ellipsis_that_stands_in_the_source():
    s = Source.from_text("Well... I suppose that we could go home now, said the old man.")
    q = one("Well... I suppose that we could go home now", s)
    assert q.exact and q.flags == []


def test_scattered_single_words_are_not_a_quotation(novel, lease):
    assert not one("the … of … and … to … in … a", novel).exact
    q = one("Landlord ... Tenant ... month ... the ... late", lease)
    assert not q.exact
    assert not one("[you] the [never] Landlord [x] may [y] to [z] repairs [w] but", lease).exact
    far = one("It is a truth universally acknowledged … Pemberley woods", novel)
    assert not far.exact and "FAR_APART" in far.flags


def test_brackets(lease):
    for text in ["the Tenant may keep one cat or [even] one small dog", "[He] may keep one cat or one small dog",
                 "[T]he Tenant may keep one cat or one small dog", "The Tenant may keep one cat [sic] or one small dog[1]",
                 "The [renter] may keep one cat or one small dog", "The [Tenant] may keep one cat or one small dog",
                 "The Tenant may keep one cat or one small[er] dog"]:
        assert one(text, lease).label == "EXACT", text
    assert one("The [renter] may keep one cat or one small dog", lease).flags == ["BRACKETS"]
    assert one("[T]he Tenant may keep one cat or one small dog", lease).flags == []
    # a citation mark is not an insertion: it may not stand for missing words
    assert not one("The Tenant may keep [1] or one small dog", lease).exact
    # words left over outside the brackets must still match
    assert one("The [renter] may keep one cat or one large dog", lease).label == "ALTERED"
    # too few words of the source left
    assert check('"The [renter must never ever keep a cat or a] dog"', lease).quotes == []


def test_brackets_of_the_source_itself():
    s = Source.from_text("The fee must be paid within [30] days of the [first] notice.")
    assert one("The fee must be paid within [30] days of the [first] notice", s).flags == []
    assert one("The fee must be paid within 30 days of the first notice", s).exact
    assert not one("The fee must be paid within [60] days of the first notice", s).exact


# --- what is checked and what is skipped ---------------------------------------------------------


def test_min_words(lease):
    text = '"one cat" and "one small dog" and "keep one cat or one"'
    report = check(text, lease)
    assert len(report.quotes) == 1 and len(report.skipped) == 2
    assert len(check(text, lease, min_words=2).quotes) == 3
    assert len(check(text, lease, min_words=50).quotes) == 0
    assert check("no quotes at all", lease).all_exact
    assert check('"" "..." “ ”', lease).skipped == []


def test_unclosed_quote_is_checked_and_flagged(lease):
    report = check("It says “The Tenant may keep one cat or one small dog.\n\nFine.", lease)
    assert report.quotes[0].label == "EXACT" and report.quotes[0].flags == ["UNCLOSED"] and report.warnings


def test_block_quote_attribution(lease):
    q = one("> The Tenant may keep one cat or one small dog.\n> — Lease, section 4", lease)
    assert q.label == "EXACT" and q.flags == ["ATTRIBUTION_IGNORED"]
    q = one("> No notice is needed in an emergency.\n> — Except on every second Tuesday of the month.", lease)
    assert not q.exact


def test_multi_paragraph_quote(lease):
    q = one("“No notice is needed in an emergency.\n\n“4. Pets\n\n“The Tenant may keep one cat”", lease)
    assert q.exact


def test_markup_inside_quotes(lease):
    for text in ["The **Tenant** may _keep_ one cat or *one* small dog", "The <em>Tenant</em> may keep<br>one cat or one small dog",
                 "The [Tenant](https://example.org/x) may keep one cat or one small dog", "The Ten­ant may keep one​ cat or one small dog",
                 "The Tenant may keep one cat or one small dog【3†source】", "The **T**enant may keep one cat or one small dog"]:
        assert one(text, lease).exact, text


def test_line_end_hyphenation():
    s = Source.from_text("These obligations sur-\nvive the end of the lease in all cases.")
    q = one("obligations survive the end of the lease", s)
    assert q.exact and s.text[q.source_start : q.source_end] == q.best_match


def test_empty_source_and_empty_text(lease):
    report = check('"The Tenant may keep one cat"', Source.from_text(""))
    assert report.quotes[0].label == "FABRICATED" and report.quotes[0].best_match == "" and report.warnings
    assert check("", lease).quotes == [] and check("", Source.from_text(" \n— …")).all_exact
    long = " ".join(f"w{i}x" for i in range(700))
    assert check(f'"{long}"', Source.from_text("")).quotes[0].label == "FABRICATED"


def test_quote_longer_than_source():
    s = Source.from_text("only four words here")
    assert one("only four words here and then a great many more", s).label == "FABRICATED"


def test_exact_is_found_in_a_very_repetitive_source():
    s = Source.from_text("the cat sat on the mat and " * 3000 + "the cat sat on the hat and " + "the cat sat on the mat and " * 3000)
    q = one("mat and the cat sat on the hat and the cat sat on the mat", s)
    assert q.exact and "hat" in q.best_match


def test_long_quotes(novel):
    words = novel.text[40_000:60_000].split()[5:2000]
    text = " ".join(words)
    for mark in '"“”«»[]':
        text = text.replace(mark, " ")
    assert one(f"« {text} »", novel).exact
    q = one(f"« {text.replace(' and ', ' zebra ')} »", novel)
    assert q.label == "ALTERED" and len(q.parts) > 5 and "OUT_OF_ORDER" not in q.flags
    half = text.split()
    dropped = " ".join(half[:800] + half[850:])
    assert one(f"« {dropped} »", novel).label == "ALTERED"


# --- Russian -------------------------------------------------------------------------------------


def test_russian():
    s = Source.from_text(RU, language="ru")
    q = one("«Все еще шел дождь. Мой дядя»", s)
    assert q.exact and q.best_match == "Всё ещё шёл дождь.\nМой дядя"
    assert one("«Мой дядя самых честных правил, когда не в шутку занемог»", s).exact
    assert one("«Мой дядя … он уважать себя заставил»", s).flags == ["ELLIPSIS"]
    q = one("«Мой дядя самых строгих правил, когда не в шутку занемог»", s)
    assert q.label == "ALTERED"
    q = one("«Мой дядя самых честным правил, когда не в шутку занемог»", s)
    assert q.label == "ALTERED"  # an inflection is a change, not a spelling
    assert one("«Мой дядя любил по вечерам играть в карты с соседями»", s).label == "FABRICATED"
    # decomposed letters (й = и + breve, ё = е + diaeresis) and a stress mark
    assert one("«Мой дядя самых че́стных правил, когда не»", s).exact
    assert one("> Он уважать себя заставил\n> и лучше выдумать не мог.", s).exact
    r = check("„Мой дядя самых честных правил“ и «коротко»", s)
    assert r.quotes[0].exact and len(r.skipped) == 1


def test_other_scripts_do_not_crash():
    s = Source.from_text("日本語のテキスト。 النص العربي هنا في هذا المكان", language="ar")
    assert one("النص العربي هنا في هذا المكان", s).exact


# --- properties checked on random input ------------------------------------------------------------


def test_random_spans_are_exact_and_random_edits_are_not(novel):
    rng = random.Random(3)
    _, index = novel._index(True, "en", core.default_config())
    words, _ = novel._indexed[True]
    tokens = words.tokens
    for _ in range(80):
        n = rng.randrange(5, 60)
        a = rng.randrange(len(tokens) - n)
        raw = [novel.text[words.original(t.start) : words.original(t.end, end=True)] for t in tokens[a : a + n]]
        q = one("«" + " ".join(raw) + "»", novel)
        assert q.exact, raw
        assert [t.norm for t in core._Words(q.best_match, True).tokens] == [t.norm for t in tokens[a : a + n]]
        k = rng.randrange(1, n - 1)
        for edited in (raw[:k] + ["quuxword"] + raw[k + 1 :], raw[:k] + ["quuxword"] + raw[k:]):
            assert not one("«" + " ".join(edited) + "»", novel).exact
    assert index.tokens[:5] == [t.norm for t in tokens[:5]]


def test_random_soup_never_crashes(lease):
    rng = random.Random(11)
    bits = ["the Tenant ", "shall pay ", "... ", "…", "[the] ", "[T]he ", "[1]", "“", "”", '"', "«", "»", "'", "\n\n", "\n> ", "-\n",
            "30 ", "1,450 ", "­", "​", "½", "[", "]", "(", ")", "* ", "**", "the deposit ", "\\\"", "<br>", "【", "】", "é̀ ", "\x00"]
    for _ in range(800):
        text = "".join(rng.choice(bits) for _ in range(rng.randrange(40)))
        for numbers in (True, False):
            report = check(text, lease, min_words=1, compare_numbers=numbers)
            json.dumps(report.to_dict())
            for q in report.quotes:
                assert q.label in LABELS and 0 <= q.similarity <= 1
                assert (q.label == "EXACT") == (q.similarity == 1 and q.exact)
                if not q.parts and q.source_start is not None:
                    assert lease.text[q.source_start : q.source_end] == q.best_match


def test_source_is_reusable_with_different_options(lease):
    quote = "The Landlord shall return the deposit within 60 days"
    labels = [one(quote, lease, compare_numbers=n, lower=x, upper=1).label
              for n, x in [(True, 0.8), (False, 0.8), (True, 0.99), (True, 0.8)]]
    assert labels == ["ALTERED", "EXACT", "FABRICATED", "ALTERED"]


def test_whole_novel_is_fast(novel):
    start = time.perf_counter()
    source = Source.from_text(novel.text)
    quote = "It is a truth universally acknowledged, that a single man in possession of a good fortune must be in want of a wife."
    report = check("\n\n".join(f'"{quote.replace("single", w)}"' for w in ["single", "married", "wealthy", "lonely"] * 5), source)
    assert [q.label for q in report.quotes[:2]] == ["EXACT", "ALTERED"]
    assert time.perf_counter() - start < 5


@pytest.mark.parametrize("kwargs", [
    {"min_words": 0}, {"min_words": 2.5}, {"min_words": True}, {"upper": 0.5}, {"lower": -1}, {"upper": 2},
    {"lower": float("nan")}, {"language": ""}, {"language": "not a code"},
])
def test_bad_options(lease, kwargs):
    with pytest.raises(ValueError):
        check("text", lease, **kwargs)


def test_bad_types(lease):
    for bad in [lambda: check(None, lease), lambda: check("x", "source"), lambda: Source.from_text(b"x")]:
        with pytest.raises(TypeError):
            bad()


# --- command line ----------------------------------------------------------------------------------


def run(capsys, *args):
    code = main([str(a) for a in args])
    out = capsys.readouterr()
    return code, out.out, out.err


LEASE_FILE, ANSWER_FILE = ROOT / "examples" / "lease.txt", ROOT / "examples" / "answer.md"


def test_cli_text_and_exit_code(capsys, tmp_path):
    code, out, _ = run(capsys, "--source", LEASE_FILE, "--input", ANSWER_FILE)
    assert code == 1 and "[3] ALTERED" in out and "Result: 2 EXACT, 1 ALTERED, 1 FABRICATED" in out
    good = tmp_path / "good.txt"
    good.write_text('"The Tenant may keep one cat or one small dog."', encoding="utf-8-sig")
    assert run(capsys, "--source", LEASE_FILE, "--input", good)[0] == 0
    good.write_text("nothing quoted")
    code, out, _ = run(capsys, "--source", LEASE_FILE, "--input", good)
    assert code == 0 and "no quotes to check" in out


def test_cli_json(capsys):
    code, out, _ = run(capsys, "--source", LEASE_FILE, "--input", ANSWER_FILE, "--json")
    data = json.loads(out)
    assert code == 1 and data["all_exact"] is False and data["skipped_short"] == 1
    assert data["quotes"][2]["flags"] == ["NUMBERS_DIFFER"]


def test_cli_options(capsys):
    code, out, _ = run(capsys, "--source", LEASE_FILE, "--input", ANSWER_FILE, "--json", "--min-words", "2", "--lower", "0.95")
    data = json.loads(out)
    assert data["skipped_short"] == 0 and data["counts"]["FABRICATED"] == 2
    code, out, _ = run(capsys, "--source", LEASE_FILE, "--input", ANSWER_FILE, "--json", "--ignore-numbers", "--language", "en-GB")
    assert json.loads(out)["counts"]["EXACT"] == 3


def test_cli_stdin(capsys, monkeypatch):
    stdin = io.TextIOWrapper(io.BytesIO("«Мой дядя самых честных правил»".encode()))
    monkeypatch.setattr("sys.stdin", stdin)
    assert run(capsys, "--source", LEASE_FILE, "--input", "-", "--language", "ru")[0] == 1


def test_cli_usage_errors(capsys, tmp_path):
    empty, binary = tmp_path / "empty.txt", tmp_path / "binary"
    empty.write_text("")
    binary.write_bytes(b"\xff\xfe\x00\x80")
    for args in [("--source", tmp_path / "missing", "--input", ANSWER_FILE), ("--source", LEASE_FILE, "--input", tmp_path / "missing"),
                 ("--source", empty, "--input", ANSWER_FILE), ("--source", binary, "--input", ANSWER_FILE),
                 ("--source", LEASE_FILE, "--input", tmp_path), ("--source", "-", "--input", ANSWER_FILE),
                 ("--source", LEASE_FILE, "--input", ANSWER_FILE, "--min-words", "0"),
                 ("--source", LEASE_FILE, "--input", ANSWER_FILE, "--lower", "0.99"),
                 ("--source", LEASE_FILE, "--input", ANSWER_FILE, "--language", "??")]:
        code, out, err = run(capsys, *args)
        assert code == 2 and out == "" and err.startswith("quotecheck: error:"), args
    for args in [[], ["--source", "x"], ["--nonsense"], ["--source", "a", "--input", "b", "--min-words", "x"]]:
        with pytest.raises(SystemExit) as e:
            main(args)
        assert e.value.code == 2


def test_cli_output_has_no_control_characters(capsys, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text('"The Tenant \x1b[31mmay keep one cat or two small dogs"')
    _, out, _ = run(capsys, "--source", LEASE_FILE, "--input", f)
    assert "\x1b" not in out


def test_readme_output_is_real(capsys, monkeypatch):
    monkeypatch.chdir(ROOT)
    run_args = ("--source", "examples/lease.txt", "--input", "examples/answer.md")
    _, out, _ = run(capsys, *run_args)
    assert out.strip() in (ROOT / "examples" / "README.md").read_text(encoding="utf-8")


def test_version_matches_pyproject():
    import tomllib

    import quotecheck

    assert tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"] == quotecheck.__version__


def test_result_fields_are_documented_names():
    assert {"text", "label", "similarity", "best_match", "source_start", "source_end", "start", "end"} <= {
        f.name for f in dataclasses.fields(core.QuoteResult)}
