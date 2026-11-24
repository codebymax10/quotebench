"""Counting rules for the headline metric (DECISIONS D15) and the reporting layer (D14-D16)."""

import json
import re
import shutil
import subprocess

import pandas as pd
import pytest

from quotebench import report as R
from quotebench.report import lookup_metrics, quote_metrics


def frame(rows):
    base = {"should_abstain": False, "task": "reference", "location_correct": None, "flags": ""}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_verbatim_counting_rules():
    d = frame([
        {"label": "EXACT"},                       # correct
        {"label": "EXACT", "flags": "OVERLONG"},  # complete quote + extra text: correct
        {"label": "EXACT", "flags": "PARTIAL"},   # cut short: wrong (incomplete)
        {"label": "MINOR"},                       # spelling only: wrong
        {"label": "ALTERED"}, {"label": "FABRICATED"}, {"label": "WRONG_PLACE"},
        {"label": "UNPARSEABLE"},                 # excluded, but counted in correct_strict
        {"label": "ABSTAINED"},
        {"label": "CORRECT_REFUSAL", "should_abstain": True},
        {"label": "TRAP_FABRICATED", "should_abstain": True},
    ])
    m = quote_metrics(d)
    assert (m["correct"]["k"], m["correct"]["n"]) == (2, 7)
    assert (m["correct_strict"]["k"], m["correct_strict"]["n"]) == (2, 8)
    assert m["incomplete"]["k"] == 1 and m["spelling_only"]["k"] == 1
    assert m["altered"]["k"] == m["fabricated"]["k"] == m["wrong_place"]["k"] == 1
    assert (m["abstained"]["k"], m["abstained"]["n"]) == (1, 8)
    assert (m["trap_failure"]["k"], m["trap_failure"]["n"]) == (1, 2)
    assert m["unparseable"] == 1
    assert (m["correct_of_all"]["k"], m["correct_of_all"]["n"]) == (2, 9)  # the declined question counts here
    # the chart segments add up to the wrong answers on the strict base
    assert sum(k for _, k in R.error_segments(m)) == 6 == R.wrong_strict(m)[0]
    assert R.wrong_strict(m) == (6, 8)


def test_lookup_strict_counts_unreadable_answers_as_wrong():
    m = lookup_metrics(frame([
        {"label": "EXACT"}, {"label": "EXACT"}, {"label": "FABRICATED"}, {"label": "ABSTAINED"},
        {"label": "UNPARSEABLE"}, {"label": "UNPARSEABLE", "should_abstain": True},  # a trap: not in the base
    ]))
    assert (m["wrong_reference"]["k"], m["wrong_reference"]["n"]) == (1, 3)
    assert (m["wrong_reference_strict"]["k"], m["wrong_reference_strict"]["n"]) == (2, 4)


def test_trick_question_shares_split_by_what_the_answer_says():
    m = metrics(1, 0, traps_uncorrected=2, traps_corrected=3, traps=10)
    assert (m["trap_failure"]["k"], m["trap_failure"]["n"]) == (5, 10)  # a quote is a failure, corrected or not
    assert (m["trap_uncorrected"]["k"], m["trap_uncorrected"]["n"]) == (2, 10)
    assert (m["trap_uncorrected"]["lo"], m["trap_uncorrected"]["hi"]) == (R.wilson(2, 10)["lo"], R.wilson(2, 10)["hi"])
    assert [k for _, k in R.trap_segments(m)] == [2, 3]
    # the flags change nothing for questions that have a real answer
    assert quote_metrics(frame([{"label": "EXACT", "flags": "SOURCE_CORRECTED,SELF_RETRACTED"}]))["correct"]["k"] == 1


def test_the_two_kinds_of_correction_are_counted_apart():
    trap = {"label": "TRAP_FABRICATED", "should_abstain": True}
    m = quote_metrics(frame([{**trap, "flags": f} for f in ("", "SOURCE_CORRECTED", "MULTIPLE_ANSWERS,SELF_RETRACTED",
                                                            "SOURCE_CORRECTED,SELF_RETRACTED")]
                            + [{"label": "CORRECT_REFUSAL", "should_abstain": True, "flags": "SELF_RETRACTED"}]))
    assert [m[f"trap_{x}"]["k"] for x in ("failure", "uncorrected", "source_corrected", "self_retracted")] == [4, 1, 2, 2]
    assert {m[f"trap_{x}"]["n"] for x in ("failure", "uncorrected", "source_corrected", "self_retracted")} == {5}


# known 95% Wilson score intervals (R: prop.test(k, n, correct = FALSE); Newcombe 1998 for 81/263)
@pytest.mark.parametrize("k, n, lo, hi", [(81, 263, 0.2553, 0.3662), (15, 148, 0.0624, 0.1605), (0, 20, 0.0, 0.1611),
                                          (1, 29, 0.0061, 0.1718), (5, 10, 0.2366, 0.7634), (10, 10, 0.7225, 1.0)])
def test_wilson_interval_known_values(k, n, lo, hi):
    w = R.wilson(k, n)
    assert (w["k"], w["n"], w["rate"]) == (k, n, k / n)
    assert w["lo"] == pytest.approx(lo, abs=1e-4) and w["hi"] == pytest.approx(hi, abs=1e-4)


def test_wilson_of_nothing():
    assert R.wilson(0, 0) == {"k": 0, "n": 0, "rate": None, "lo": None, "hi": None}


def test_strict_base_has_no_trick_questions():
    m = quote_metrics(frame([{"label": "EXACT"}, {"label": "UNPARSEABLE"}, {"label": "UNPARSEABLE", "should_abstain": True},
                             {"label": "TRAP_FABRICATED", "should_abstain": True}]))
    assert (m["correct_strict"]["k"], m["correct_strict"]["n"], m["unparseable"]) == (1, 2, 1)
    assert (m["correct_of_all"]["n"], m["trap_failure"]["n"]) == (2, 1)  # an unreadable trick answer is in no rate


def test_location_errors_are_counted_on_topic_questions_only():
    m = quote_metrics(frame([
        {"label": "EXACT", "task": "topic", "location_correct": True}, {"label": "WRONG_PLACE", "task": "topic", "location_correct": False},
        {"label": "ALTERED", "task": "topic", "location_correct": False}, {"label": "EXACT", "task": "topic", "location_correct": None},
        {"label": "EXACT", "task": "reference", "location_correct": False}]))
    assert (m["location_error"]["k"], m["location_error"]["n"]) == (2, 3)


def test_lookup_unparseable_has_the_base_of_the_strict_rate():
    m = lookup_metrics(frame([{"label": "EXACT"}, {"label": "UNPARSEABLE"}, {"label": "UNPARSEABLE", "should_abstain": True}]))
    assert m["unparseable"] == 1 == m["wrong_reference_strict"]["n"] - m["wrong_reference"]["n"]


# --------------------------------------------------------------------------- summarise


ROW = {"model": "x/a", "task": "reference", "text_id": "bible_kjv", "fame": "famous", "should_abstain": False, "flags": "",
       "location_correct": None, "repeat": 0, "condition": "baseline", "label": "EXACT", "cost": 0.1, "provider": "H",
       "served_model": "a-served", "timestamp": "2026-10-11T00:00:00", "completion_tokens": 10}


@pytest.fixture
def summarised(monkeypatch, tmp_path):
    """Run ``summarise`` on a handful of rows of one model."""
    monkeypatch.setattr(R, "SUMMARY_PATH", tmp_path / "summary.json")
    monkeypatch.setattr(R, "archived_costs", lambda: {"x/a": 1.0})
    monkeypatch.setattr(R, "load_config", lambda: {"models": [
        {"id": "x/a", "label": "A", "provider": "X", "role": "main", "api": "anthropic", "api_model": "a-api"}]})

    def run(rows, complete=True):
        monkeypatch.setattr(R, "incomplete_models", lambda calls: [] if complete else ["x/a: 1 of 2 calls"])
        return R.summarise(pd.DataFrame([{**ROW, **r} for r in rows]))
    return run


def test_only_the_main_run_is_counted(summarised):
    s = summarised([{"question_id": "q1"}, {"question_id": "q2", "label": "ALTERED"}]
                   + [{"question_id": "q1", "repeat": r, "label": "FABRICATED"} for r in (1, 2, 3)])
    b = s["per_model"]["x/a"]["baseline"]
    assert (b["correct_strict"]["k"], b["correct_strict"]["n"], b["fabricated"]["k"]) == (1, 2, 0)
    m = s["models"][0]
    assert m["calls_done"] == 5 and m["cost_usd"] == pytest.approx(1.5)  # repeats and replaced answers cost money too
    assert (m["api_model"], m["served_models"]) == ("a-api", ["a-served"])


def test_stability_needs_four_runs(summarised):
    def runs(q, *labels, condition="baseline"):
        return [{"question_id": q, "repeat": i, "label": x, "condition": condition} for i, x in enumerate(labels)]
    s = summarised(runs("same", *["EXACT"] * 4) + runs("differs", *["EXACT"] * 3, "ALTERED") + runs("three", *["EXACT"] * 3)
                   + runs("once", "EXACT") + runs("cautious", *["EXACT"] * 4, condition="cautious")
                   + runs("same wrong", *["FABRICATED"] * 4))
    st = s["per_model"]["x/a"]["stability"]
    assert (st["k"], st["n"]) == (2, 3)


def test_lookup_subset_is_the_questions_that_have_a_lookup_version(summarised):
    s = summarised([{"question_id": "q1", "condition": c} for c in ("baseline", "cautious", "lookup")]
                   + [{"question_id": "q2", "condition": c, "label": "ALTERED"} for c in ("baseline", "cautious")])
    sub = s["per_model"]["x/a"]["lookup_subset"]
    assert sub["n_questions"] == 1
    assert [(sub[c]["correct_strict"]["k"], sub[c]["correct_strict"]["n"]) for c in ("baseline", "cautious")] == [(1, 1)] * 2
    assert s["per_model"]["x/a"]["baseline"]["correct_strict"]["n"] == 2


def test_a_partial_summary_is_a_draft(summarised):
    assert summarised([{"question_id": "q1"}])["status"] == "released"
    assert summarised([{"question_id": "q1"}], complete=False)["status"] == "draft"


def test_incomplete_models():
    from quotebench.runner import build_jobs

    models = [m["id"] for m in R.load_config()["models"]]
    calls = [(m, j.question_id, j.condition, j.repeat) for m in models for j in build_jobs(["any"])]
    assert R.incomplete_models(calls) == []
    n = len(calls) // len(models)
    assert R.incomplete_models(calls[1:]) == [f"{models[0]}: {n - 1} of {n} calls"]
    assert R.incomplete_models(calls[n:]) == [f"{models[0]}: 0 of {n} calls"]
    old = [*calls[1:], (models[0], "t9-gone-0001", "baseline", 0)]  # as many calls, but not the same ones
    assert R.incomplete_models(old) == [f"{models[0]}: {n - 1} of {n} calls, and 1 that are not in the test set"]


def test_host_errors_are_reported_and_excluded():
    rec = {"status": "ok", "error": None, "finish_reason": "error"}
    assert R.call_error(rec) == R.HOST_ERROR
    assert R.call_error({**rec, "finish_reason": "stop"}) is None
    assert R.call_error({**rec, "finish_reason": "length"}) is None  # unfinished is wrong, not an error (D16)
    assert R.call_error({**rec, "status": "error", "error": "HTTP 500", "finish_reason": None}) == "HTTP 500"
    m = quote_metrics(frame([{"label": "EXACT"}, {"label": "ABSTAINED"}, {"label": "ERROR"},
                             {"label": "ERROR", "should_abstain": True}]))
    assert m["errors"] == 2 and m["unparseable"] == 0
    assert (m["correct_strict"]["n"], m["correct_of_all"]["n"], m["abstained"]["n"], m["trap_failure"]["n"]) == (1, 2, 2, 0)


def test_score_all_labels_a_host_error(tmp_path, monkeypatch):
    from quotebench.questions import load_questions

    q = next(q for q in load_questions() if q["task"] == "reference")
    rec = {"model": "x/a", "question_id": q["id"], "condition": "baseline", "repeat": 0, "status": "ok", "error": None,
           "content": '{"quote": "And we know that all things', "finish_reason": "error", "prompt_tokens": 0,
           "completion_tokens": 0, "reasoning_tokens": 0, "cost": 0.0, "latency": 1.0, "timestamp": "2026-10-11",
           "served_model": "a", "provider": "H"}

    class OneCall:
        def rows(self):
            return [rec]

    monkeypatch.setattr(R, "SCORED_PATH", tmp_path / "scored.parquet")
    row = R.score_all(OneCall()).iloc[0]
    assert row["label"] == "ERROR" and row["flags"] == f"{R.HOST_ERROR},FINISH_ERROR"


@pytest.mark.parametrize("k, n, text", [(571, 592, "96.5%"), (61, 80, "76.3%"), (1, 80, "1.3%"), (0, 5, "0.0%"),
                                        (5, 5, "100.0%"), (0, 0, "–")])
def test_percentages_have_one_decimal_and_round_half_up(k, n, text):
    assert R.pct(k, n) == text


def test_n_range():
    assert R.n_range([100, 100]) == "100"
    assert R.n_range([99, None, 100]) == "99–100"
    assert R.n_range([]) == "0"


# ---------------------------------------------------------------------------- a small summary


def metrics(correct, altered, unreadable=0, traps_uncorrected=1, traps_corrected=1, traps=4, declined=3):
    rows = ([{"label": "EXACT"}] * correct + [{"label": "ALTERED"}] * altered + [{"label": "UNPARSEABLE"}] * unreadable
            + [{"label": "ABSTAINED"}] * declined
            + [{"label": "TRAP_FABRICATED", "should_abstain": True}] * traps_uncorrected
            + [{"label": "TRAP_FABRICATED", "should_abstain": True, "flags": "SHORT_QUOTE,SOURCE_CORRECTED"}] * traps_corrected
            + [{"label": "CORRECT_REFUSAL", "should_abstain": True}] * (traps - traps_uncorrected - traps_corrected))
    m = quote_metrics(frame(rows))
    m["by_text"] = {"bible_kjv": quote_metrics(frame(rows))}
    m["by_fame"] = {"famous": quote_metrics(frame(rows)), "random": quote_metrics(frame(rows))}
    m["by_task"] = {}
    return m


def per_model(correct, altered, unreadable, stable):
    q = metrics(correct, altered, unreadable)
    lk = lookup_metrics(frame([{"label": "EXACT"}] * 3 + [{"label": "UNPARSEABLE"}]))
    return {"baseline": q, "cautious": q, "lookup": lk, "stability": R.wilson(stable, 10),
            "lookup_subset": {"n_questions": 14, "baseline": q, "cautious": q}}


@pytest.fixture
def summary():
    def model(id_, label, calls=100, dates=("2026-10-11", "2026-10-14")):
        return {"id": id_, "label": label, "provider": "X", "role": "main", "note": None, "api": "openrouter",
                "api_model": id_, "served_models": [id_], "hosts": ["H"], "calls_done": calls, "cost_usd": 1.0, "run_dates": list(dates), "mean_output_tokens": 1.0}
    return {
        "benchmark": "QuoteBench", "version": "v1.0", "generated": "2026-11-24T00:00:00+00:00", "status": "released",
        "n_questions": 700, "expected_calls_per_model": 100,
        "scoring": {"status": "frozen-v1.0", "thresholds": {"upper": 0.97, "lower": 0.8}, "partial_min_words": 6},
        # B has the higher rate of answered questions (9/10) but the lower strict rate (9/12 < 8/10)
        "models": [model("x/b", "Model B"), model("x/a", "Model A", dates=("2026-10-28", "2026-10-28"))],
        "per_model": {"x/b": per_model(9, 1, 2, 7), "x/a": per_model(8, 2, 0, 10)},
    }


# ---------------------------------------------------------------------------- figures


@pytest.fixture
def drawn(summary, tmp_path, monkeypatch):
    """Draw the figures; returns a function giving all text of figure ``i`` (captions with plain spaces)."""
    pytest.importorskip("matplotlib")
    import matplotlib.pyplot as plt

    monkeypatch.setattr(R, "FIGURES_DIR", tmp_path)

    def draw(s=summary):
        figs = []
        with monkeypatch.context() as mp:
            mp.setattr(plt, "close", lambda f=None: figs.append(f))
            names = R.make_figures(s)
        texts = []
        for f in figs:
            t = [x.get_text() for x in f.texts]
            for ax in f.axes:
                t += [x.get_text() for x in ax.texts] + [ax.get_title(loc="left")]
                t += [x.get_text() for x in ax.get_yticklabels()]
                t += [x.get_text() for x in ax.get_legend().get_texts()] if ax.get_legend() else []
            texts.append("\n".join(t).replace("\xa0", " "))
            plt.close(f)
        return names, texts
    return draw


def test_figures_have_no_draft_caption(summary, drawn):
    for status in ("released", "draft"):
        summary["status"] = status
        names, texts = drawn()
        assert len(names) == 4
        assert not any(re.search("draft|validated", t, re.I) for t in texts)
        assert "not checked against human labels" in texts[0].replace("\n", " ")


def test_figure_1_is_labelled_and_ordered_by_the_strict_rate(drawn):
    _, texts = drawn()
    assert "80.0% correct (strict)" in texts[0] and "75.0% correct (strict)" in texts[0]
    assert "90.0%" not in texts[0]           # B's rate of answered questions only
    assert "Unfinished" in texts[0]
    assert "answered + unfinished" in texts[0].replace("\n", " ") and "n = 10–12" in texts[0]
    assert texts[0].index("Model A") < texts[0].index("Model B")


def test_figures_2_and_3_use_the_strict_base(drawn):
    _, texts = drawn()
    assert "(strict)" in texts[1] and "famous n = 10–12" in texts[1].replace("\n", " ")
    flat = texts[2].replace("\n", " ")
    assert "25.0%" in flat and "plain n = 10–12" in flat and "lookup n = 4" in flat
    assert "95% Wilson intervals" in texts[3].replace("\n", " ") and "n = 4" in texts[3]


def test_figure_4_shows_both_parts(drawn):
    flat = drawn()[1][3].replace("\n", " ")
    assert "50.0%, 25.0% uncorrected" in flat
    assert "No correction in the answer" in flat and "Corrected in the same answer" in flat
    assert "gave a quote" in flat and "a failure, corrected or not" in flat and "cannot_quote counts as declining" in flat


def test_no_claim_that_a_model_fell_for_anything(summary, drawn, page):
    texts = [*drawn()[1], page, *(make(summary) for make in R.TABLES.values())]
    assert not any(re.search(r"\bfell for|fallen for", t, re.I) for t in texts)
    assert not any(re.search(r"genuine|presented as|always a failure", t, re.I) for t in texts)
    for t in (R.readme_table(summary), page):
        assert "Gave a quote on a trick question" in t and "of which with no correction" in t
        assert re.search(r"marked `?cannot_quote`? counts as declining, even if it also contains a quote", t)


def test_host_errors_are_named_under_the_table(summary):
    assert "host ended" not in R.readme_table(summary)
    q = summary["per_model"]["x/b"]
    q["baseline"] = {**q["baseline"], "errors": 1}
    assert "host ended with an error are in no rate: Model B 1 plain, 0 cautious." in R.readme_table(summary)


def test_unfinished_models_keep_the_partial_data_caption(summary, drawn):
    assert not any("partial data" in t for t in drawn()[1])
    summary["models"][0]["calls_done"] = 50
    assert all("partial data" in t and "Model B *" in t for t in drawn()[1])


# ---------------------------------------------------------------------------- leaderboard page


@pytest.fixture
def page(summary, tmp_path, monkeypatch):
    monkeypatch.setattr(R, "PAGE_PATH", tmp_path / "docs" / "index.html")
    return R.build_page(summary).read_text(encoding="utf-8")


def js(expression, *args):
    """Evaluate an expression with the page's own helper functions in scope."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    html = R.PAGE_TEMPLATE.read_text(encoding="utf-8")
    helpers = re.search(r"// helpers:start.*?\n(.*?)// helpers:end", html, re.S)[1]
    src = f"{helpers}\nconst args = {json.dumps(args)};\nconsole.log(JSON.stringify({expression}));"
    return json.loads(subprocess.run([node, "-e", src], capture_output=True, text=True, check=True).stdout)


def test_release_status_and_banner():
    assert R.RELEASE_STATUS == "released"
    assert js("bannerHtml('released')") == ""
    assert "Draft" in js("bannerHtml('draft')")


def test_page_is_one_static_file_with_the_paper_link(page):
    assert "__SUMMARY_JSON__" not in page
    assert 'href="https://github.com/codebymax10/quotebench/blob/main/PAPER.md"' in page
    assert "paper at release" not in page
    assert not re.search(r'<(script|link|img)[^>]+(src|href)="(?!data:)', page)  # the icon is a data URI
    assert page.count('<link rel="icon" href="data:image/svg+xml,') == 1


def test_data_cannot_close_the_script_element(summary, tmp_path, monkeypatch):
    monkeypatch.setattr(R, "PAGE_PATH", tmp_path / "index.html")
    summary["models"][0]["note"] = "</script><b>x</b>"
    page = R.build_page(summary).read_text(encoding="utf-8")
    assert page.count("</script>") == R.PAGE_TEMPLATE.read_text(encoding="utf-8").count("</script>")
    data = re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S)[1]
    assert json.loads(data) == json.loads(json.dumps(summary))  # and it is still the same data


def test_page_discloses_how_it_was_made(page):
    text = re.sub(r"\s+", " ", page)
    for words in ("drafted with Claude", "not reviewed line by line by the author", "code and the paper were written with Claude",
                  "corrected after the results were seen", "DECISIONS D19", "Not peer reviewed", "was not checked by humans",
                  "finished under the earlier 2,000-token limit were kept", "digits"):
        assert words in text, words
    assert "<details" not in text[text.index("What to know"):text.index("Leaderboard</h2>")]  # visible, not folded away
    ms = [{"id": i, "provider": p} for i, p in (("b", "OpenAI"), ("a", "Anthropic"), ("c", "Anthropic"), ("d", "Anthropic"))]
    rates = {i: {"baseline": {"correct_strict": {"rate": r}}} for i, r in (("a", .9), ("c", .8), ("b", .7), ("d", .6))}
    assert js("claudeNote(args[0], args[1])", ms, rates) == "3 of the 4 models are Claude models, including the top 2"


def test_page_shows_what_the_api_was_asked_for_and_what_answered(page):
    assert "Model ID (API)" in page and "m.api_model" in page and "m.served_models" in page
    assert "including answers that were later replaced" in page and "Cost incl. replaced answers" in page


def test_page_tiles_and_condition_choice(page):
    assert js("modelsTile('released', 9, 9)") == ["Models", "9"]
    assert js("modelsTile('draft', 8, 9)") == ["Models finished", "8 of 9"]
    assert "localStorage" not in page and 'let cond = "baseline"' in page


def test_model_column_is_sticky_at_every_width(page):
    css = page[page.index("<style>"):page.index("</style>")]
    assert re.search(r"^#board th:first-child \{ position: sticky; left: 0;", css, re.M)  # outside any media query


def contrast(a, b):
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = (x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_text_contrast(page):
    css = page[page.index("<style>"):page.index("</style>")]
    for block in re.findall(r"\{\s*color-scheme: (?:light|dark);.*?\}", css, re.S):
        v = dict(re.findall(r"--([\w-]+): (#[0-9a-f]{6})", block))
        for ink in ("ink", "ink2", "muted", "link"):
            assert all(contrast(v[ink], v[bg]) >= 4.5 for bg in ("page", "surface")), (ink, v[ink])
    assert "a { color: var(--link); }" in css


def test_page_shows_the_range_of_run_dates():
    assert js("runDates(['2026-10-11', '2026-10-14'])") == "2026-10-11 to 2026-10-14"
    assert js("runDates(['2026-10-28', '2026-10-28'])") == "2026-10-28"
    assert js("runDates([])") == "not run"
    assert "runDates(m.run_dates)" in R.PAGE_TEMPLATE.read_text(encoding="utf-8")


def test_page_rounds_like_the_readme_and_the_figures():
    cases = [(k, n) for n in (70, 80, 99, 130, 582, 600) for k in range(n + 1)] + [(0, 0)]
    assert js("args[0].map(([k, n]) => pct(k, n))", cases) == [R.pct(k, n) for k, n in cases]


def test_page_chart_segments_match_the_figures():
    q = metrics(9, 1, 2)
    assert js("segments(args[0])", q) == [list(s) for s in R.error_segments(q)]
    assert js("wrong(args[0])", q) == {"k": 3, "n": 12}
    assert js("trapSegments(args[0])", q) == [list(s) for s in R.trap_segments(q)]
    assert js("[range([100, 100]), range([99, null, 100]), range([])]") == ["100", "99–100", "0"]


def test_page_charts_use_only_the_strict_base(page):
    script = page[page.index("helpers:end"):]
    body = script[script.index("const order"):]
    # `correct` without _strict is used in the leaderboard table only (here: the Answered column)
    assert re.findall(r"\.correct\b.{6}", body) == [".correct.n, de"]
    assert "correct_strict" in re.search(r"const order = .*?;\n", body, re.S)[0]


def test_page_has_a_sortable_coverage_column_with_a_definition(page):
    assert re.search(r'key: "correct_of_all", label: "Correct of all asked", rate: true, def: "[^"]*declining counts as not', page)
    assert 'key: "errors", label: "Errors"' in page


def test_page_shows_stability_with_its_definition(page):
    assert 'key: "stability"' in page and "same scorer label in all four runs" in page
    assert "Consistency, not correctness" in page and "n = ${stabN} per model" in page


def test_page_accessibility(page):
    # sorting: real buttons, aria-sort, focus kept after the table is rebuilt
    assert "<button type=\"button\" data-key=" in page and "aria-sort=" in page and ".focus()" in page
    # every chart is a labelled group; every mark carries its own label
    assert 'role: "group", "aria-label": label' in page
    assert page.count('role: "img", "aria-label"') == 2  # bars and dots
    # wide tables scroll in their own focusable, labelled container
    wraps = re.findall(r'<div class="table-wrap"[^>]*>', page)
    assert len(wraps) == 3 and all('tabindex="0"' in w and "aria-label" in w for w in wraps)
    assert 'name="viewport"' in page


# ---------------------------------------------------------------------------- generated tables


@pytest.fixture
def docs(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "README_PATH", tmp_path / "README.md")
    monkeypatch.setattr(R, "PAPER_PATH", tmp_path / "PAPER.md")
    return tmp_path


def block(name, body="old"):
    return f"<!-- {name}:start -->\n{body}\n<!-- {name}:end -->"


def test_missing_files_and_markers_are_left_alone(summary, docs):
    everything = ["README.md: results", "README.md: stability", *(f"PAPER.md: {n}" for n in R.TABLES)]
    assert R.update_readme(summary) == everything
    assert not list(docs.iterdir())
    for text in ("no markers\n", "<!-- results:start -->\nprose\n", "<!-- fame:end -->\nx\n<!-- fame:start -->\n"):
        (docs / "README.md").write_text(text, encoding="utf-8")
        (docs / "PAPER.md").write_text(text, encoding="utf-8")
        assert R.update_readme(summary) == everything
        assert (docs / "README.md").read_text(encoding="utf-8") == text
        assert (docs / "PAPER.md").read_text(encoding="utf-8") == text


def test_a_lost_end_marker_does_not_swallow_prose(summary, docs):
    text = f"<!-- traps:start -->\nkeep me\n{block('fame')}\n{block('traps')}\n"
    (docs / "PAPER.md").write_text(text, encoding="utf-8")
    assert R.update_blocks(R.PAPER_PATH, summary) == ["fame", "traps"]
    assert "keep me" in (docs / "PAPER.md").read_text(encoding="utf-8")


def test_all_tables_in_readme_and_paper(summary, docs):
    names = ["results", "stability", "by_text", "fame", "conditions", "traps"]
    text = "intro\n\n" + "\n\nprose\n\n".join(block(n) for n in names) + "\n\nend\n"
    (docs / "README.md").write_text(text.replace("old", "OLD"), encoding="utf-8")
    (docs / "PAPER.md").write_text(text, encoding="utf-8")
    assert R.update_readme(summary) == []
    paper = (docs / "PAPER.md").read_text(encoding="utf-8")
    assert paper == (docs / "README.md").read_text(encoding="utf-8")
    assert "old" not in paper and paper.count("prose") == 5 and paper.startswith("intro") and paper.endswith("end\n")
    for n in names:
        body = re.search(rf"<!-- {n}:start -->(.*?)<!-- {n}:end -->", paper, re.S)[1]
        assert body.index("Model A") < body.index("Model B")  # strict order everywhere
    before = paper
    (docs / "README.md").write_text(block("stability"), encoding="utf-8")
    assert R.update_readme(summary) == ["README.md: results"]  # the missing block is named
    assert (docs / "PAPER.md").read_text(encoding="utf-8") == before  # idempotent


def test_tables_carry_sample_sizes_and_intervals(summary):
    all_asked = R.interval(R.wilson(9, 15))  # 9 correct, 1 altered, 2 unfinished, 3 declined
    assert (f"| Model B | 75.0% | 90.0% | 60.0% (9/15), {all_asked} | 0.0% | 50.0% | 25.0% | 10 | 2 |"
            in R.readme_table(summary))
    assert "n = 4 per model" in R.readme_table(summary)
    v = summary["per_model"]["x/b"]["stability"]
    assert f"| Model B | 70.0% (7/10) | {R.interval(v)} |" in R.stability_table(summary)
    assert "| Model B | 25.0% (3/12) | – | – | – | – |" in R.by_text_table(summary)
    assert "| Model B | 75.0% (9/12) | 75.0% (9/12) |" in R.fame_table(summary)
    assert "| Model B | 25.0% (3/12) | 25.0% (3/12) | 25.0% (1/4) |" in R.conditions_table(summary)
    gave, shown = (f"{100 * k // 4}.0% ({k}/4), {R.interval(R.wilson(k, 4))}" for k in (2, 1))
    assert f"| Model B | {gave} | {shown} | {gave} | {shown} |" in R.traps_table(summary)
