"""The `quotebench` command line."""

from __future__ import annotations

from typing import Optional

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True, help="QuoteBench: verbatim quotation benchmark.")


@app.callback()
def main() -> None:
    """QuoteBench: how often do language models fabricate or alter verbatim quotations?"""


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
):
    """Query models through OpenRouter. Cached: re-running resumes and never pays twice."""
    import asyncio

    from . import runner as R

    cfg = R.load_config()
    settings = cfg["settings"]
    model_ids = models or (cfg["dry_run_models"] if dry_run else [m["id"] for m in cfg["models"]])
    qids = cfg["dry_run_questions"] if dry_run else None
    jobs = R.build_jobs(model_ids, conditions, qids, repeats=not dry_run)
    pricing = R.fetch_pricing(model_ids)
    cache = R.Cache()
    other = cache.max_tokens_used() - {settings["max_tokens"]}
    if other:
        raise typer.BadParameter(f"cache holds answers made with max_tokens={sorted(other)} but config says "
                                 f"{settings['max_tokens']}; one benchmark must use one setting")
    rows = R.estimate(jobs, pricing, settings, cache)
    typer.echo(f"{'model':38s} {'calls':>6s} {'expected':>9s} {'worst':>8s}  basis")
    for r in rows:
        typer.echo(f"{r['model']:38s} {r['calls']:6d} ${r['expected_cost']:8.2f} ${r['worst_cost']:7.2f}  {r['basis']}")
    typer.echo(f"{'TOTAL':38s} {sum(r['calls'] for r in rows):6d} ${sum(r['expected_cost'] for r in rows):8.2f} "
               f"${sum(r['worst_cost'] for r in rows):7.2f}")
    typer.echo(f"already spent (all cached calls): ${cache.total_cost():.4f}")
    if estimate:
        return
    if max_cost is None and not dry_run:
        raise typer.BadParameter("a full run needs --max-cost (SPEC §6)")
    cap = max_cost if max_cost is not None else 1.0

    def progress(s):
        if s["done"] % 50 == 0 or s["done"] == len(jobs):
            typer.echo(f"{s['done']} done, {s['errors']} errors, total spent ${s['spent']:.4f}")

    routes = R.model_routes(cfg)
    needs_openrouter = any(routes[m]["api"] == "openrouter" for m in model_ids)
    api_key = R.load_api_key() if needs_openrouter else None
    stats = asyncio.run(R.run_jobs(jobs, cache, pricing, settings, api_key, cap,
                                   retry_errors=retry_errors, progress=progress, routes=routes))
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

    df = Rep.score_all()
    typer.echo(f"{len(df)} responses scored -> results/scored.parquet")
    typer.echo(df.groupby(["model", "label"]).size().unstack(fill_value=0).to_string())


@app.command()
def report():
    """Score all responses, then write results/summary.json, results/figures/ and docs/index.html."""
    from . import report as Rep

    df = Rep.score_all()
    summary = Rep.summarise(df)
    figs = Rep.make_figures(summary)
    page = Rep.build_page(summary)
    Rep.update_readme(summary)
    typer.echo(f"{len(df)} responses scored; summary -> results/summary.json; {len(figs)} figures -> results/figures/")
    typer.echo(f"leaderboard -> {page.relative_to(Rep._ROOT)}  (status: {summary['status']})")


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

    r = V.agreement()
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
