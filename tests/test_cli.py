"""The command line and the answer cache: no network, no spending, never the real cache."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from quotebench import cli, report as Rep, runner as R, sources as S, validate as V

ROOT = Path(__file__).resolve().parents[1]


def rec(n, content="answer", timestamp="2026-10-11", model="x/a"):
    return {"key": f"{model}|q{n}|baseline|0", "model": model, "question_id": f"q{n}", "condition": "baseline", "repeat": 0,
            "status": "ok", "timestamp": timestamp, "latency": 1.0, "attempts": 1, "request": {"max_tokens": 400},
            "response": {"id": n}, "content": content, "finish_reason": "stop", "served_model": "a", "provider": "H",
            "prompt_tokens": 10, "completion_tokens": 5, "reasoning_tokens": None, "cost": 0.5, "error": None}


def publish(raw_dir, recs):
    raw_dir.mkdir(exist_ok=True)
    (raw_dir / "x__a.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")


def contents(cache):
    return {k: c for k, c in cache.db.execute("SELECT key, content FROM calls")}


@pytest.fixture
def raw(tmp_path):
    publish(tmp_path / "raw", [rec(i) for i in range(5)])
    return tmp_path / "raw"


# ------------------------------------------------------------------------------- the cache


def test_a_fresh_clone_imports_everything(tmp_path, raw):
    c = R.Cache(tmp_path / "c.sqlite", raw_dir=raw)
    assert (c.imported, c.differing, len(contents(c))) == (5, 0, 5)
    row = c.get("x/a|q1|baseline|0")
    assert json.loads(row["request"]) == {"max_tokens": 400} and json.loads(row["response"]) == {"id": 1}
    assert R.Cache(tmp_path / "c.sqlite", raw_dir=raw).imported == 0
    assert not contents(R.Cache(tmp_path / "other.sqlite"))  # only the benchmark's own cache is completed


def test_an_interrupted_import_leaves_nothing_and_is_made_up_for(tmp_path, raw, monkeypatch):
    real, n = R.Cache._insert, []

    def interrupted(self, how, record):
        n.append(1)
        if len(n) == 4:
            raise KeyboardInterrupt
        return real(self, how, record)

    monkeypatch.setattr(R.Cache, "_insert", interrupted)
    with pytest.raises(KeyboardInterrupt):
        R.Cache(tmp_path / "c.sqlite", raw_dir=raw)
    assert sqlite3.connect(tmp_path / "c.sqlite").execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 0
    monkeypatch.setattr(R.Cache, "_insert", real)
    assert R.Cache(tmp_path / "c.sqlite", raw_dir=raw).imported == 5


def test_a_process_killed_during_the_import_leaves_nothing(tmp_path, raw):
    code = ("import os, sys; from pathlib import Path; from quotebench import runner as R\n"
            "real, n = R.Cache._insert, []\n"
            "def ins(self, how, rec):\n    n.append(1)\n    if len(n) == 4: os._exit(9)\n    return real(self, how, rec)\n"
            "R.Cache._insert = ins\nR.Cache(Path(sys.argv[1]), raw_dir=Path(sys.argv[2]))")
    p = subprocess.run([sys.executable, "-c", code, str(tmp_path / "c.sqlite"), str(raw)], cwd=ROOT,
                       env={"PYTHONPATH": str(ROOT / "src")})
    assert p.returncode == 9
    assert R.Cache(tmp_path / "c.sqlite", raw_dir=raw).imported == 5


def test_a_partial_or_stale_cache_gets_the_missing_calls(tmp_path, raw):
    c = R.Cache(tmp_path / "c.sqlite")
    for i in (0, 1):  # left by an import that was interrupted half-way
        c.put({**rec(i), "request": "{}", "response": "{}"})
    assert R.Cache(tmp_path / "c.sqlite", raw_dir=raw).imported == 3
    publish(raw, [rec(i) for i in range(5)] + [rec(0, model="x/new")])  # git pull
    c = R.Cache(tmp_path / "c.sqlite", raw_dir=raw)
    assert (c.imported, c.differing, len(contents(c))) == (1, 0, 6)


def test_paid_answers_are_never_overwritten_or_dropped(tmp_path, raw):
    c = R.Cache(tmp_path / "c.sqlite")
    c.put({**rec(1, "a newer, paid answer", "2026-11-01"), "request": "{}", "response": "{}"})
    c.put({**rec(99, "paid, not exported yet"), "request": "{}", "response": "{}"})
    c = R.Cache(tmp_path / "c.sqlite", raw_dir=raw)
    assert (c.imported, c.differing) == (4, 1)
    got = contents(c)
    assert got["x/a|q1|baseline|0"] == "a newer, paid answer" and got["x/a|q99|baseline|0"] == "paid, not exported yet"
    assert len(got) == 6 and c.total_cost() == pytest.approx(3.0)


def test_the_benchmark_cache_is_not_created_outside_a_checkout(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "CACHE_PATH", tmp_path / "results" / "cache.sqlite")
    monkeypatch.setattr(R, "IN_CHECKOUT", False)
    with pytest.raises(RuntimeError, match="needs a checkout"):
        R.Cache(R.CACHE_PATH)
    assert not (tmp_path / "results").exists()


# --------------------------------------------------------------------------- the command line


def invoke(*args):
    return CliRunner().invoke(cli.app, list(args))


@pytest.mark.parametrize("command", ["score", "report", "run", "questions", "sources"])
def test_outside_a_checkout_there_is_one_clear_line(command, monkeypatch):
    monkeypatch.setattr(S, "IN_CHECKOUT", False)
    r = invoke(command)
    assert r.exit_code == 1 and isinstance(r.exception, SystemExit)
    assert r.output.strip() == f"Error: {S.NOT_A_CHECKOUT}" and len(r.output.strip().splitlines()) == 1


def test_installed_without_the_checkout(tmp_path):
    """The package copied somewhere else, as a wheel would be."""
    import shutil

    site = tmp_path / "lib" / "site-packages"
    shutil.copytree(ROOT / "src" / "quotebench", site / "quotebench", ignore=shutil.ignore_patterns("__pycache__"))
    p = subprocess.run([sys.executable, "-c", "import sys, quotebench.cli as c; assert c.__file__.startswith(sys.argv[1]); "
                        "sys.argv = ['quotebench', 'score']; c.app()", str(site)], cwd=tmp_path, capture_output=True, text=True, env={"PYTHONPATH": str(site)})
    assert p.returncode == 1 and "Traceback" not in p.stderr and "needs a checkout" in p.stderr
    assert sorted(x.name for x in tmp_path.rglob("*") if x.is_file() and x.suffix != ".pyc") == sorted(
        x.name for x in (ROOT / "src" / "quotebench").glob("*") if x.is_file())


@pytest.fixture
def cache(tmp_path, monkeypatch):
    c = R.Cache(tmp_path / "cache.sqlite")
    monkeypatch.setattr(cli, "open_cache", lambda: c)
    return c


def test_report_refuses_incomplete_answers_and_writes_nothing(cache, monkeypatch):
    cache.put({**rec(1, model=R.load_config()["models"][0]["id"]), "request": "{}", "response": "{}"})
    for name in ("score_all", "summarise", "make_figures", "build_page", "update_readme"):
        monkeypatch.setattr(Rep, name, lambda *a, **k: pytest.fail("the report must not be written"))
    r = invoke("report")
    assert r.exit_code == 1 and isinstance(r.exception, SystemExit)
    assert "nothing was written" in r.output and r.output.count("incomplete:") == len(R.load_config()["models"])


@pytest.mark.parametrize("problem", ["failed call", "cache differs from results/raw"])
def test_report_refuses_failed_or_unpublished_answers(cache, monkeypatch, problem):
    monkeypatch.setattr(Rep, "incomplete_models", lambda calls: [])
    monkeypatch.setattr(Rep, "score_all", lambda cache: pytest.fail("must not score"))
    if problem == "failed call":
        cache.put({**rec(1), "status": "error", "error": "429", "request": "{}", "response": "{}"})
    else:
        cache.differing = 3
    r = invoke("report")
    assert r.exit_code == 1 and "nothing was written" in r.output
    assert ("1 calls failed" if problem == "failed call" else "3 cached answers differ") in r.output


def test_report_draft_is_marked_and_leaves_the_documents_alone(cache, monkeypatch):
    seen = []
    monkeypatch.setattr(Rep, "score_all", lambda c: [])
    monkeypatch.setattr(Rep, "summarise", lambda df: {"status": "released"})
    monkeypatch.setattr(Rep, "write_summary", lambda s: seen.append(s["status"]))
    monkeypatch.setattr(Rep, "make_figures", lambda s: [])
    monkeypatch.setattr(Rep, "build_page", lambda s: seen.append(s["status"]) or Rep.PAGE_PATH)
    monkeypatch.setattr(Rep, "update_readme", lambda s: pytest.fail("a draft must not change README.md or PAPER.md"))
    r = invoke("report", "--draft")
    assert r.exit_code == 0 and seen == ["draft", "draft"] and "status: draft" in r.output


def test_report_names_the_missing_blocks(cache, monkeypatch):
    monkeypatch.setattr(Rep, "incomplete_models", lambda calls: [])
    monkeypatch.setattr(Rep, "score_all", lambda c: [])
    monkeypatch.setattr(Rep, "summarise", lambda df: {"status": "released"})
    monkeypatch.setattr(Rep, "make_figures", lambda s: [])
    monkeypatch.setattr(Rep, "build_page", lambda s: Rep.PAGE_PATH)
    monkeypatch.setattr(Rep, "update_readme", lambda s: ["PAPER.md: fame"])
    r = invoke("report")
    assert r.exit_code == 0 and "WARNING: no generated block in PAPER.md: fame" in r.output


PRICES = {"note": "n", "fetched": "now", "models": {}}


@pytest.fixture
def prices(monkeypatch):
    saved = []
    monkeypatch.setattr(R, "fetch_pricing", lambda ids: {**PRICES, "models": {
        m: {"prompt": 1e-6, "completion": 5e-6, "supported_parameters": []} for m in ids}})
    monkeypatch.setattr(R, "save_pricing", saved.append)
    monkeypatch.setattr(R, "run_jobs", lambda *a, **k: pytest.fail("no call may be made"))
    return saved


MODEL = "anthropic/claude-haiku-5.5"


def test_estimate_prints_tokens_and_writes_no_file(cache, prices):
    r = invoke("run", "--estimate", "--models", MODEL)
    assert r.exit_code == 0, r.output
    row = next(line for line in r.output.splitlines() if line.startswith(MODEL)).split()
    assert row[1] == "1920" and int(row[2].replace(",", "")) > 1920 * 350 and "tokens" in r.output
    assert prices == []


def test_fetching_prices_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "PRICING_PATH", tmp_path / "pricing.json")
    monkeypatch.setattr(R, "RESULTS_DIR", tmp_path)
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"data": [
        {"id": "x/a", "pricing": {"prompt": "0.000001", "completion": "0.000002"}}]})))
    out = R.fetch_pricing(["x/a"], client)
    assert out["models"]["x/a"]["prompt"] == 1e-6 and not (tmp_path / "pricing.json").exists()
    R.save_pricing(out)
    assert json.loads((tmp_path / "pricing.json").read_text())["note"] == R.PRICING_NOTE


def test_the_committed_prices_say_what_they_are():
    assert json.loads(R.PRICING_PATH.read_text())["note"] == R.PRICING_NOTE


def test_offline_estimate_fails_in_one_line(cache, monkeypatch):
    def offline(ids):
        raise httpx.ConnectError("no network")
    monkeypatch.setattr(R, "fetch_pricing", offline)
    r = invoke("run", "--estimate")
    assert r.exit_code == 1 and isinstance(r.exception, SystemExit)
    assert r.output.startswith("Error: cannot fetch the model prices") and len(r.output.strip().splitlines()) == 1


def test_a_cap_below_the_recorded_spend_is_explained(cache, prices, monkeypatch):
    monkeypatch.setattr(R, "archived_costs", lambda: {"x/a": 31.83})
    r = invoke("run", "--models", MODEL, "--max-cost", "25")
    assert r.exit_code == 1 and isinstance(r.exception, SystemExit) and prices == []
    assert "already $31.83" in r.output and "--max-cost above $31.83" in r.output and "1920 calls" in r.output


def test_validate_agree_without_a_sheet(tmp_path, monkeypatch):
    monkeypatch.setattr(V, "SHEET_PATH", tmp_path / "labeling_sheet.csv")
    r = invoke("validate", "agree")
    assert r.exit_code == 1 and isinstance(r.exception, SystemExit)
    assert "no validation/labeling_sheet.csv" in r.output and "validate export" in r.output


def test_validate_rescoring_uses_the_benchmark_cache(cache, monkeypatch):
    import pandas as pd

    from quotebench.questions import load_questions
    from quotebench.scoring import ScoringConfig

    q = next(q for q in load_questions() if q["task"] == "reference")
    r = {**rec(1, json.dumps({"quote": q["ground_truth"], "location": ""})), "question_id": q["id"]}
    cache.put({**r, "request": "{}", "response": "{}"})
    monkeypatch.setattr(R, "Cache", lambda: cache)
    key = pd.DataFrame([{"model": "x/a", "question_id": q["id"], "condition": "baseline"}])
    assert V.rescore(key, ScoringConfig.load()) == ["EXACT"]


# ------------------------------------------------------------------------- scripts/paper_numbers.py


def test_old_counts_agree_with_the_history():
    import io

    import pandas as pd

    old = json.loads((ROOT / "results/archive/pre_d19_counts.json").read_text())
    p = subprocess.run(["git", "show", f"{old['commit']}:results/scored.parquet"], capture_output=True, cwd=ROOT)
    if p.returncode:
        pytest.skip("the old commit is not available here")
    df = pd.read_parquet(io.BytesIO(p.stdout))
    df = df[(df["condition"] == "baseline") & (df["repeat"] == 0) & ~df["should_abstain"]]
    for model, d in df.groupby("model"):
        flags = d["flags"].fillna("")
        ok = (d["label"] == "EXACT") & ~flags.str.contains("PARTIAL")
        answered = d["label"].isin(["EXACT", "MINOR", "ALTERED", "FABRICATED", "WRONG_PLACE"])
        assert old["models"][model] == {
            "n": len(d), "ok": ok.sum(), "ans": answered.sum(), "wrong": (answered & ~ok).sum(),
            "abst": (d["label"] == "ABSTAINED").sum(), "unf": (d["label"] == "UNPARSEABLE").sum(),
            "fab": (d["label"] == "FABRICATED").sum(), "err": (d["label"] == "ERROR").sum()}


def test_paper_numbers_without_history_exits_0_with_a_notice(tmp_path):
    """Run where git finds no repository: Table 4 is still printed, the list of changed labels is not."""
    (tmp_path / "git").write_text("#!/bin/sh\nexit 128\n")
    (tmp_path / "git").chmod(0o755)
    p = subprocess.run([sys.executable, str(ROOT / "scripts/paper_numbers.py")], capture_output=True, text=True,
                       env={"PATH": str(tmp_path)})
    assert p.returncode == 0, p.stderr
    assert "NOTICE: skipped, commit cc1d009 is not available here" in p.stdout
    assert "| Model | Correct before | Correct after | Gain | Strict before | Strict after | Strict rank |" in p.stdout
    assert "rows only in one file" not in p.stdout
