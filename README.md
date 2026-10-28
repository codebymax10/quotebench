# QuoteBench

**How often do AI language models get a quotation wrong when asked to quote a famous text word for word?**

QuoteBench asks models to quote well-known public-domain texts — the King James Bible, three
Shakespeare plays, the U.S. Constitution, *Pride and Prejudice* and Darwin's *On the Origin of
Species* (1859) — and checks every answer automatically against the source. A quote counts as
correct only if every word matches the named edition (punctuation and capitals ignored); wrong
answers are sorted into spelling only, incomplete, altered, a real passage from the wrong place,
or made up. It also asks trick questions about passages that do not exist, and compares a plain
prompt, an "only quote if you are certain" prompt, and a *lookup* design where the model only
names the passage and the system fetches the text.

QuoteBench measures **verbatim quotation only** — not hallucination in general.

> **Status:** v1.0 in progress. Data collection is complete for 9 models; the write-up is not
> finished. Numbers below are generated from `results/summary.json` and may still change before
> the v1.0 tag.

## Results

Interactive leaderboard: **[codebymax10.github.io/quotebench](https://codebymax10.github.io/quotebench/)** (source: [`docs/index.html`](docs/index.html)) (sortable table, charts, per-text breakdown).

<!-- results:start -->
| Model | Correct (strict) | Correct | Made up | Fell for trick questions | Answered |
|---|---|---|---|---|---|
| Claude Opus 5.5 | 96.5% | 96.5% | 0.3% | 2.0% | 592 |
| Claude Sonnet 4.6 | 93.0% | 93.0% | 2.7% | 4.0% | 401 |
| Claude Sonnet 5.5 | 91.8% | 91.8% | 1.0% | 8.0% | 582 |
| GPT-6 Luna | 84.6% | 84.6% | 7.3% | 25.0% | 564 |
| Claude Haiku 5.5 | 83.4% | 83.4% | 3.0% | 6.0% | 501 |
| DeepSeek V4 Pro | 83.3% | 85.9% | 5.3% | 4.0% | 582 |
| Gemini 3.1 Flash Lite | 76.0% | 76.1% | 17.3% | 17.0% | 595 |
| Claude Haiku 4.5 | 69.6% | 69.6% | 12.8% | 11.0% | 494 |
| Llama 4 Maverick | 21.4% | 21.4% | 65.0% | 24.0% | 585 |

Plain prompt; shares of answered questions that have a real answer. Ranked by *Correct (strict)*, which also counts answers the model never finished (it reasoned past the token limit) as wrong; *Correct* leaves those out. Generated 2026-10-28 from `results/summary.json`; 95% intervals and all breakdowns are in that file and on the leaderboard.
<!-- results:end -->

## What is in the benchmark

| | |
|---|---|
| **Texts** | `bible_kjv` (Project Gutenberg #10), `shakespeare` (Hamlet, Macbeth, Romeo and Juliet from Gutenberg #100), `us_constitution` (National Archives transcription, original spelling), `pride_prejudice` (Gutenberg #1342), `origin_species` (1st ed. 1859, Gutenberg #1228). Provenance and checksums: [`sources/PROVENANCE.md`](sources/PROVENANCE.md). |
| **Tasks** (700 questions) | 1 — quote a reference (Bible, Constitution; 200) · 2 — quote the passage that comes next (250) · 3 — give a verbatim quote on a theme with its location (150) · 4 — trick questions: nonexistent references, famous misattributions, absent topics (100). About a third of tasks 1–2 are famous passages, the rest drawn at random (seed 20261011). |
| **Conditions** | `baseline` (plain request) · `cautious` (adds "only quote if you are certain") · `lookup` (Bible and Constitution only: the model returns a reference, the system fetches the text). |
| **Models** (v1.0) | Claude Opus 5.5, Claude Sonnet 5.5, Claude Haiku 5.5, and the previous-generation Claude Sonnet 4.6 and Claude Haiku 4.5 (Anthropic API); GPT-6 Luna, Gemini 3.1 Flash Lite, DeepSeek V4 Pro, Llama 4 Maverick (OpenRouter, each pinned to one host). Exact IDs, hosts and dates are on the leaderboard and in [`config/models.yaml`](config/models.yaml). |
| **Settings** | One user message, JSON answer, no system prompt, no tools or web search, temperature 0 where the model accepts it, up to 16,000 output tokens (8,192 for Llama 4 Maverick, its host's maximum), each model's default reasoning. A fixed 10% sample is run three more times to measure run-to-run stability. |

## How scoring works

1. Model quote and source are normalised the same way: Unicode NFKC, case-folded, punctuation
   and quotation marks removed, apostrophes and in-word hyphens joined ("to-morrow" = "tomorrow"),
   verse numbers and references stripped.
2. **Correct** = the normalised words are identical to the requested passage. A complete quote
   followed by extra text still counts (flagged `OVERLONG`); a correct fragment does not
   (`incomplete`).
3. Everything else is wrong, and is sorted by a word-level edit distance with an n-gram search
   over the whole source: *spelling only* (e.g. "choose" for the 1787 "chuse"), *altered*
   (≥ 80% word similarity), *wrong place* (a real passage, but not the one asked for), *made up*
   (below 80% everywhere in the source). This split is approximate.
4. Trick questions: any quote given is a failure; declining is correct. Topic quotes: any real
   passage counts, then the stated location is checked.

Every rule is covered by tests in [`tests/`](tests/). Design decisions and their reasons:
[`DECISIONS.md`](DECISIONS.md). Full specification: [`SPEC.md`](SPEC.md).

## Reproduce

Requires Python 3.11+.

```bash
git clone https://github.com/codebymax10/quotebench && cd quotebench
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp .env.example .env    # then add OPENROUTER_API_KEY and ANTHROPIC_API_KEY
```

| Stage | Command |
|---|---|
| Parse the source texts (raw files are committed; downloads only if missing) | `quotebench sources` |
| Build the test set (deterministic) | `quotebench questions` |
| Cost estimate, no calls | `quotebench run --estimate` |
| Dry run: 10 questions on 2 cheap models | `quotebench run --dry-run` |
| Full run, with a hard spending cap in USD | `quotebench run --max-cost 25` |
| Score, summary, charts and leaderboard | `quotebench report` |
| Tests | `pytest` |

Every API response is cached in `results/cache.sqlite` (not committed), so a run can stop at any
point and resume without paying twice; all raw responses are published in `results/raw/`.
Re-scoring needs no API key: the published answers can be re-scored from `results/raw/`.

## Add a model

Add a line to [`config/models.yaml`](config/models.yaml) with the exact OpenRouter model ID (and,
ideally, `providers:` to pin one host), then run `quotebench run --estimate --models <id>`,
`quotebench run --models <id> --max-cost <usd>` and `quotebench report`.

## Limitations

- Measures verbatim quotation only, not hallucination in general; nothing about paraphrase or
  interpretation.
- Famous public-domain texts are heavily present in training data: results are an upper bound
  for quoting obscure or private documents.
- One edition per text. A model that quotes another edition or translation accurately is scored
  wrong, although every prompt names the edition. The Constitution keeps its 1787 spelling, so
  modernised spellings count as wrong ("spelling only").
- English only in v1.0. Nine models, five of them from Anthropic. Only Anthropic has its main
  and top models in (Claude Sonnet 5.5, Claude Opus 5.5) — OpenAI and Google appear through
  their small models. Open-weights models are served by a third-party host in fp8.
- Requiring a JSON answer may change model behaviour. Some models (OpenAI GPT-6, Anthropic 5.x)
  do not accept temperature 0; Claude Sonnet 4.6 and Haiku 4.5 do and get it.
- The first run used a 2,000-token limit; the 451 answers it cut off were asked again at 16,000
  ([`DECISIONS.md`](DECISIONS.md) D16). For models without temperature 0 the new answer is a
  fresh sample, not a continuation. Answers still unfinished count as wrong in the ranking
  (*strict*).
- One run per question; run-to-run stability is measured on a 10% sample only. Results hold for
  the exact model IDs and dates recorded.
- The split of wrong answers into kinds depends on similarity thresholds that were not
  checked against human labels.
- Famous-passage lists, topics and trick questions were drafted with an AI assistant (Claude)
  and reviewed by the author.
- Solo student project; not peer reviewed.

## Related work

The closest existing benchmark is YouVersion's
[Bible Accuracy Benchmark](https://github.com/youversion/biblelab-bibleaccuracybenchmark)
(Bible quotation by reference, many translations, nonexistent-reference traps). QuoteBench
differs in covering several genres, next-passage and topic tasks, misattribution traps and the
plain / cautious / lookup comparison, with all ground truth in the repository. Notes on further
related work: [`notes/related_work_scan.md`](notes/related_work_scan.md).

## Licence and citation

- Code: MIT ([`LICENSE`](LICENSE)).
- Test set (`data/`) and results (`results/`): CC BY 4.0 ([`data/LICENSE`](data/LICENSE)).
- Source texts: public domain; see [`sources/PROVENANCE.md`](sources/PROVENANCE.md).

```bibtex
@misc{quotebench2026,
  title  = {QuoteBench: How often do language models misquote famous texts?},
  author = {Maksim},
  year   = {2026},
  note   = {Version 1.0 (in progress)},
  url    = {https://github.com/codebymax10/quotebench}
}
```
