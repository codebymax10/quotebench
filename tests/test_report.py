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
    m = metrics(1, 0, traps_presented=2, traps_corrected=3, traps=10)
    assert (m["trap_failure"]["k"], m["trap_failure"]["n"]) == (5, 10)  # any quote is a failure
    assert (m["trap_presented"]["k"], m["trap_presented"]["n"]) == (2, 10)
    assert (m["trap_presented"]["lo"], m["trap_presented"]["hi"]) == (R.wilson(2, 10)["lo"], R.wilson(2, 10)["hi"])
    assert [k for _, k in R.trap_segments(m)] == [2, 3]
    # the flag changes nothing for questions that have a real answer
    assert quote_metrics(frame([{"label": "EXACT", "flags": "SOURCE_CORRECTED"}]))["correct"]["k"] == 1


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


def metrics(correct, altered, unreadable=0, traps_presented=1, traps_corrected=1, traps=4, declined=3):
    rows = ([{"label": "EXACT"}] * correct + [{"label": "ALTERED"}] * altered + [{"label": "UNPARSEABLE"}] * unreadable
            + [{"label": "ABSTAINED"}] * declined
            + [{"label": "TRAP_FABRICATED", "should_abstain": True}] * traps_presented
            + [{"label": "TRAP_FABRICATED", "should_abstain": True, "flags": "SHORT_QUOTE,SOURCE_CORRECTED"}] * traps_corrected
            + [{"label": "CORRECT_REFUSAL", "should_abstain": True}] * (traps - traps_presented - traps_corrected))
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
                "hosts": ["H"], "calls_done": calls, "cost_usd": 1.0, "run_dates": list(dates), "mean_output_tokens": 1.0}
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
    assert "50.0%, 25.0% as genuine" in flat
    assert "Presented as from the named text" in flat and "Said itself that it is not from the named text" in flat
    assert "gave a quote" in flat and "any quote is a failure" in flat


def test_no_claim_that_a_model_fell_for_anything(summary, drawn, page):
    texts = [*drawn()[1], page, *(make(summary) for make in R.TABLES.values())]
    assert not any(re.search(r"\bfell for|fallen for", t, re.I) for t in texts)
    for t in (R.readme_table(summary), page):
        assert "Gave a quote on a trick question" in t and "of which presented as genuine" in t


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
    assert not re.search(r'<(script|link|img)[^>]+(src|href)=', page)


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
    assert R.update_readme(summary) is False
    assert not list(docs.iterdir())
    for text in ("no markers\n", "<!-- results:start -->\nprose\n", "<!-- fame:end -->\nx\n<!-- fame:start -->\n"):
        (docs / "README.md").write_text(text, encoding="utf-8")
        (docs / "PAPER.md").write_text(text, encoding="utf-8")
        assert R.update_readme(summary) is False
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
    assert R.update_readme(summary) is True
    paper = (docs / "PAPER.md").read_text(encoding="utf-8")
    assert paper == (docs / "README.md").read_text(encoding="utf-8")
    assert "old" not in paper and paper.count("prose") == 5 and paper.startswith("intro") and paper.endswith("end\n")
    for n in names:
        body = re.search(rf"<!-- {n}:start -->(.*?)<!-- {n}:end -->", paper, re.S)[1]
        assert body.index("Model A") < body.index("Model B")  # strict order everywhere
    before = paper
    R.update_readme(summary)
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
