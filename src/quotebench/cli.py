"""The `quotebench` command line."""

from __future__ import annotations

from typing import Optional

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True, help="QuoteBench: verbatim quotation benchmark.")


def fail(message: str) -> typer.Exit:
    """Print a one-line error; ``raise fail(...)``."""
    typer.echo(f"Error: {message}", err=True)
    return typer.Exit(1)


def open_cache():
    from . import runner as R

    cache = R.Cache()
    if cache.imported:
        typer.echo(f"{cache.imported} published answers were missing from results/cache.sqlite; added from results/raw")
    if cache.differing:
        typer.echo(f"{cache.differing} cached answers are not the published ones in results/raw; the cached ones are used",
                   err=True)
    return cache


@app.callback()
def main() -> None:
    """QuoteBench: how often do language models fabricate or alter verbatim quotations?"""
    from .sources import IN_CHECKOUT, NOT_A_CHECKOUT

    if not IN_CHECKOUT:
        raise fail(NOT_A_CHECKOUT)


@app.command()
def sources(
    only: Optional[list[str]] = typer.Option(None, "--only", help="Text IDs to process (default: all)."),
    refresh: bool = typer.Option(False, help="Re-download raw files even if present."),
):
    """Download (if missing) and parse the source texts into sources/parsed/."""
    from . import sources as S

    ids = only or list(S.REGISTRY)
    for text_id in ids:
        src = S.REGISTRY[text_id]
        for msg in S.download(src, refresh=refresh):
            typer.echo(msg)
        records = S.parse(src)
        path = S.write_parsed(src, records)
        typer.echo(f"{text_id}: {len(records):,} units -> {path.relative_to(S.ROOT)}")
    S.write_provenance_md()


@app.command()
def questions():
    """Build data/questions.jsonl from parsed sources and data/handwritten/*.csv."""
    from . import questions as Q

    result = Q.build()
    meta = result["meta"]
    typer.echo(f"{meta['n_questions']} questions (seed {meta['seed']}) -> data/questions.jsonl")
    for key, n in meta["counts"].items():
        typer.echo(f"  {key}: {n}")
    typer.echo(f"repeat sample: {len(meta['repeat_sample'])} questions x {meta['repeat_runs']} runs")
    for p in result["problems"]:
        typer.echo(f"PROBLEM: {p}")
    manual = [r for r in result["trap_report"] if r["verdict"] == "check by hand"]
    for r in manual:
        typer.echo(f"CHECK BY HAND: {r['text_id']} {r['content']!r} ({r['detail']})")


@app.command()
def run(
    dry_run: bool = typer.Option(False, "--dry-run", help="10 fixed questions on the 2 dry-run models."),
    estimate: bool = typer.Option(False, "--estimate", help="Print expected calls, tokens and cost; make no calls."),
    max_cost: Optional[float] = typer.Option(None, "--max-cost", help="Hard cap in USD on total spend (all runs so far + this one)."),
    models: Optional[list[str]] = typer.Option(None, "--models", help="Model IDs (default: all in config/models.yaml)."),
    conditions: Optional[list[str]] = typer.Option(None, "--conditions", help="baseline / cautious / lookup (default: all)."),
    retry_errors: bool = typer.Option(False, help="Retry calls that previously ended in ERROR."),
    concurrency: Optional[int] = typer.Option(None, help="Parallel requests per model (default: config)."),
):
    """Query models (Anthropic API / OpenRouter). Cached: re-running resumes and never pays twice."""
    import asyncio

    import httpx

    from . import runner as R

    cfg = R.load_config()
    settings = cfg["settings"]
    if concurrency:
        settings["concurrency"] = concurrency
    model_ids = models or (cfg["dry_run_models"] if dry_run else [m["id"] for m in cfg["models"]])
    qids = cfg["dry_run_questions"] if dry_run else None
    jobs = R.build_jobs(model_ids, conditions, qids, repeats=not dry_run)
    try:
        pricing = R.fetch_pricing(model_ids)
    except httpx.HTTPError as e:
        raise fail(f"cannot fetch the model prices from {R.MODELS_URL}: {type(e).__name__} {e}".rstrip())
    except RuntimeError as e:
        raise fail(str(e))
    cache = open_cache()
    routes = R.model_routes(cfg)
    limits = R.token_limits(routes)
    for m, used in cache.max_tokens_used().items():
        limit = limits.get(m, settings["max_tokens"])
        if any(t > limit for t in used):
            raise typer.BadParameter(f"cache holds {m} answers made with max_tokens={sorted(used)} but config "
                                     f"says {limit}; one benchmark must use one setting")
    redo = cache.cut_off_below(settings["max_tokens"], limits)
    if redo:
        typer.echo(f"{len(redo)} cached answers were cut off at a lower token limit; they will be asked again "
                   f"with max_tokens={settings['max_tokens']} (DECISIONS D16)")
    rows = R.estimate(jobs, pricing, settings, cache, limits)
    typer.echo(f"{'model':38s} {'calls':>6s} {'tokens':>10s} {'expected':>9s} {'worst':>8s}  basis")
    for r in rows:
        typer.echo(f"{r['model']:38s} {r['calls']:6d} {r['expected_tokens']:10,d} ${r['expected_cost']:8.2f} ${r['worst_cost']:7.2f}  {r['basis']}")
    typer.echo(f"{'TOTAL':38s} {sum(r['calls'] for r in rows):6d} {sum(r['expected_tokens'] for r in rows):10,d} ${sum(r['expected_cost'] for r in rows):8.2f} "
               f"${sum(r['worst_cost'] for r in rows):7.2f}")
    archived = sum(R.archived_costs().values())
    spent = cache.total_cost() + archived
    typer.echo("(tokens: expected prompt + output tokens; costs in USD, expected and worst case)")
    typer.echo(f"already spent: ${spent:.4f} (cached answers ${cache.total_cost():.4f} "
               f"+ replaced/archived answers ${archived:.4f})")
    if estimate:
        return
    if max_cost is None and not dry_run:
        raise typer.BadParameter("a full run needs --max-cost (SPEC §6)")
    cap = max_cost if max_cost is not None else 1.0
    n_calls = sum(r["calls"] for r in rows)
    if n_calls and cap <= spent:
        raise fail(f"the cap of ${cap:.2f} counts all recorded spend, which is already ${spent:.2f} (results/raw and "
                   f"results/archive included), so none of the {n_calls} calls can be made; pass a --max-cost above ${spent:.2f}")

    def progress(s):
        if s["done"] % 50 == 0 or s["done"] == len(jobs):
            typer.echo(f"{s['done']} done, {s['errors']} errors, total spent ${s['spent']:.4f}")

    needs_openrouter = any(routes[m]["api"] == "openrouter" for m in model_ids)
    try:
        api_key = R.load_api_key() if needs_openrouter else None
    except RuntimeError as e:
        raise fail(str(e))
    if redo:
        out = R.ROOT / "results" / "archive" / "cut_off_at_lower_limit"
        for p in R.archive_cut_off(cache, settings["max_tokens"], out, limits):
            typer.echo(f"  old answers kept in {p.relative_to(R.ROOT)}")
    if n_calls or retry_errors:
        R.save_pricing(pricing)
    stats = asyncio.run(R.run_jobs(jobs, cache, pricing, settings, api_key, cap,
                                   retry_errors=retry_errors, progress=progress, routes=routes,
                                   spent_before=archived))
    typer.echo("")
    typer.echo(f"made {stats['done']} calls ({stats['errors']} errors), {stats['skipped_cached']} already cached, "
               f"total spend ${stats['spent_total']:.4f}")
    if stats["budget_stopped"]:
        typer.echo(f"STOPPED at the ${cap:.2f} cap: {stats['not_run_budget']} calls not made. "
                   "Raise --max-cost and re-run to resume.")
    for p in R.export_raw(cache):
        typer.echo(f"raw responses -> {p.relative_to(R.ROOT)}")


@app.command()
def score():
    """Label every cached response -> results/scored.parquet."""
    from . import report as Rep

    cache = open_cache()
    for problem in Rep.incomplete_models(tuple(r[k] for k in Rep.CALL) for r in cache.rows()):
        typer.echo(f"incomplete: {problem}", err=True)
    df = Rep.score_all(cache)
    typer.echo(f"{len(df)} responses scored -> results/scored.parquet")
    typer.echo(df.groupby(["model", "label"]).size().unstack(fill_value=0).to_string())


@app.command()
def report(
    draft: bool = typer.Option(False, "--draft", help="Build the charts and the page from incomplete answers, marked as a "
                                                      "draft; README.md and PAPER.md are left alone."),
):
    """Score all responses, then write results/summary.json, results/figures/ and docs/index.html."""
    from . import report as Rep

    cache = open_cache()
    incomplete = Rep.incomplete_models(tuple(r[k] for k in Rep.CALL) for r in cache.rows())
    for problem in incomplete:
        typer.echo(f"incomplete: {problem}", err=True)
    if incomplete and not draft:
        raise fail("not every model has all its answers, so nothing was written (run the missing calls, or use --draft)")
    df = Rep.score_all(cache)
    summary = Rep.summarise(df)
    if draft:
        summary["status"] = "draft"
        Rep.write_summary(summary)
    figs = Rep.make_figures(summary)
    page = Rep.build_page(summary)
    typer.echo(f"{len(df)} responses scored; summary -> results/summary.json; {len(figs)} figures -> results/figures/")
    typer.echo(f"leaderboard -> {page.relative_to(Rep._ROOT)}  (status: {summary['status']})")
    if not draft:
        for block in Rep.update_readme(summary):
            typer.echo(f"WARNING: no generated block in {block}; that table was not updated", err=True)


validate_app = typer.Typer(no_args_is_help=True, help="Human validation of the scorer (SPEC §8).")
app.add_typer(validate_app, name="validate")


@validate_app.command("export")
def validate_export():
    """Write validation/labeling_sheet.csv (no automatic labels) and validation/sample_key.csv."""
    from . import validate as V

    sheet, key = V.export()
    typer.echo(f"labelling sheet -> {sheet.relative_to(V.ROOT)}  (fill in the your_label column)")
    typer.echo(f"answer key      -> {key.relative_to(V.ROOT)}  (do not open before labelling)")


@validate_app.command("agree")
def validate_agree():
    """Agreement between the human labels and the scorer, plus a threshold sensitivity table."""
    import pandas as pd

    from . import validate as V

    try:
        r = V.agreement()
    except (FileNotFoundError, ValueError) as e:
        raise fail(str(e))
    typer.echo(f"labelled {r['n_labelled']} / {r['n_total']}")
    typer.echo(f"agreement {r['agreement']:.1%}   Cohen's kappa {r['kappa']:.3f}")
    typer.echo("\nconfusion (rows = human, columns = scorer):")
    typer.echo(r["confusion"].to_string())
    with pd.option_context("display.max_colwidth", 60, "display.width", 200):
        typer.echo(f"\n{len(r['disagreements'])} disagreements:")
        typer.echo(r["disagreements"].to_string(index=False))
        typer.echo("\nsensitivity (same sample, other settings):")
        typer.echo(r["sensitivity"].to_string(index=False))


if __name__ == "__main__":
    app()
