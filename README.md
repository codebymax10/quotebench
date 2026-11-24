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

> **Version 1.0** (November 2026). Every number below comes from the files in `results/`.
> The write-up is [`PAPER.md`](PAPER.md).

## Headline findings

*Plain prompt, 95% intervals in brackets. Drafted by an AI model (Claude) from `results/`; five of the nine models are Claude models. Details and caveats: [`PAPER.md`](PAPER.md).*

- **The ranking depends on how declining is counted.** Claude Sonnet 4.6 is second among the quotations it attempted (93.5%, 375/401 [90.7–95.5]) but seventh over all 600 questions (62.5%, 375/600 [58.6–66.3]), because it declined 199 of them. On the 401 questions it attempted, it is not clearly different from Claude Sonnet 5.5 (375 vs 385 correct; paired test p = 0.087). Read every rate below with this in mind.
- **Models differ widely.** Of attempted quotations, Claude Opus 5.5 got 97.1% word for word (575/592 [95.4–98.2]), Llama 4 Maverick 21.4% (125/585 [18.2–24.9]). Opus 5.5 is ahead of every other model in paired tests; over all 600 questions it got 95.8% (575/600 [93.9–97.2]).
- **Prose is much harder than the Bible.** DeepSeek V4 Pro, which declined nothing, got 98.3% on the Bible (226/230 [95.6–99.3]) and 52.5% on *Pride and Prejudice* and Darwin together (84/160 [44.8–60.1]). All nine models were worse on prose; for Opus 5.5 it was 230/230 against 138/152.
- **Fame helps most models.** Six of nine were clearly better on famous than on random passages (Gemini 3.1 Flash Lite: 125/138 vs 220/307; Llama 4 Maverick: 63/133 vs 11/303). The intervals overlap for Opus 5.5, Sonnet 5.5 and Sonnet 4.6.
- **"Only quote if you are certain" helps some models, at a price.** Wrong quotations out of 600 fell for Claude Haiku 4.5 (150 to 98), Sonnet 4.6 (26 to 7), GPT-6 Luna (81 to 59) and Haiku 5.5 (80 to 59); Llama's drop (460 to 441) is not significant after adjustment for nine comparisons. Sonnet 4.6 also lost 110 correct ones (375 to 265) and Haiku 4.5 lost 21 (344 to 323). There was no clear change for Opus 5.5, Sonnet 5.5, DeepSeek or Gemini.
- **Giving a quote on a trick question is not the same as being fooled.** GPT-6 Luna gave one on 25 of 100 trick questions, but in 20 of the 25 it said itself that the line comes from another work. With no correction anywhere in the answer: Llama 20 of 100, Gemini 15, Haiku 4.5 8, GPT-6 Luna 5. (The word rules that separate these were written by Claude after the answers were seen; they bring three Claude models to 0.)
- **Looking the text up removes wording errors by design,** and only 1 of 2,300 references did not exist (Bible and Constitution only). This says little about knowledge: on most of these questions the prompt already contains the reference, and whether a passage fits the topic is not checked.

## Results

Interactive leaderboard: **[codebymax10.github.io/quotebench](https://codebymax10.github.io/quotebench/)** (source: [`docs/index.html`](docs/index.html)) (sortable table, charts, per-text breakdown).

<!-- results:start -->
| Model | Correct (strict) | Correct | Correct of all asked (k/n, 95% interval) | Made up | Gave a quote on a trick question | of which with no correction | Answered | Unfinished |
|---|---|---|---|---|---|---|---|---|
| Claude Opus 5.5 | 97.1% | 97.1% | 95.8% (575/600), 93.9–97.2% | 0.3% | 2.0% | 0.0% | 592 | 0 |
| Claude Sonnet 4.6 | 93.5% | 93.5% | 62.5% (375/600), 58.6–66.3% | 2.0% | 4.0% | 0.0% | 401 | 0 |
| Claude Sonnet 5.5 | 92.3% | 92.3% | 89.5% (537/600), 86.8–91.7% | 0.7% | 8.0% | 0.0% | 582 | 0 |
| GPT-6 Luna | 85.6% | 85.6% | 80.5% (483/600), 77.1–83.5% | 6.6% | 25.0% | 5.0% | 564 | 0 |
| DeepSeek V4 Pro | 84.3% | 86.9% | 84.3% (506/600), 81.2–87.0% | 5.3% | 4.0% | 3.0% | 582 | 18 |
| Claude Haiku 5.5 | 84.0% | 84.0% | 70.2% (421/600), 66.4–73.7% | 2.6% | 6.0% | 4.0% | 501 | 0 |
| Gemini 3.1 Flash Lite | 77.1% | 77.1% | 76.6% (459/599), 73.1–79.8% | 16.8% | 17.0% | 15.0% | 595 | 0 |
| Claude Haiku 4.5 | 69.6% | 69.6% | 57.3% (344/600), 53.3–61.2% | 12.1% | 11.0% | 8.0% | 494 | 0 |
| Llama 4 Maverick | 21.4% | 21.4% | 20.8% (125/600), 17.8–24.3% | 63.8% | 24.0% | 20.0% | 585 | 0 |

Plain prompt; questions that have a real answer. Ranked by *Correct (strict)*: share of *Answered* + *Unfinished*, where an unfinished answer (no readable answer, nearly always because the model was still reasoning at the token limit) counts as wrong. *Correct* and *Made up* are shares of *Answered* only. Questions the model declined are in neither. *Correct of all asked*: correct answers as a share of all questions with a real answer, so declining counts as not correct. *Gave a quote on a trick question*: gave a quote although there is none to give; a failure, corrected or not. An answer marked `cannot_quote` counts as declining, even if it also contains a quote. *Of which with no correction*: nowhere in the answer does it say that the line is not from the named text or that the passage asked for does not exist, or take the quote back (found by word rules; naming another place in the same text without comment is not a correction). Both are shares of all trick questions, n = 99–100 per model. Answers that the model's host ended with an error are in no rate: Gemini 3.1 Flash Lite 1 plain, 1 cautious. Generated 2026-11-24 from `results/summary.json`; 95% intervals and all breakdowns are in that file and on the leaderboard.
<!-- results:end -->

### Run-to-run stability

<!-- stability:start -->
| Model | Same label in all 4 runs | 95% interval |
|---|---|---|
| Claude Opus 5.5 | 97.1% (68/70) | 90.2–99.2% |
| Claude Sonnet 4.6 | 90.0% (63/70) | 80.8–95.1% |
| Claude Sonnet 5.5 | 91.4% (64/70) | 82.5–96.0% |
| GPT-6 Luna | 87.1% (61/70) | 77.3–93.1% |
| DeepSeek V4 Pro | 82.9% (58/70) | 72.4–89.9% |
| Claude Haiku 5.5 | 87.1% (61/70) | 77.3–93.1% |
| Gemini 3.1 Flash Lite | 100.0% (70/70) | 94.8–100.0% |
| Claude Haiku 4.5 | 100.0% (70/70) | 94.8–100.0% |
| Llama 4 Maverick | 67.1% (47/70) | 55.5–77.0% |

Share of the repeated questions (fixed sample, plain prompt, all question types including trick questions) that got the same scorer label (exact, altered, made up, declined, …) in all four runs. It measures consistency, not correctness: the same wrong label four times counts as stable, and the wording may differ.
<!-- stability:end -->

## What is in the benchmark

| | |
|---|---|
| **Texts** | `bible_kjv` (Project Gutenberg #10), `shakespeare` (Hamlet, Macbeth, Romeo and Juliet from Gutenberg #100), `us_constitution` (National Archives transcription, original spelling), `pride_prejudice` (Gutenberg #1342), `origin_species` (1st ed. 1859, Gutenberg #1228). Provenance and checksums: [`sources/PROVENANCE.md`](sources/PROVENANCE.md). |
| **Tasks** (700 questions) | 1 — quote a reference (Bible, Constitution; 200) · 2 — quote the passage that comes next (250) · 3 — give a verbatim quote on a theme with its location (150) · 4 — trick questions: nonexistent references, famous misattributions, absent topics (100). About a third of tasks 1–2 are famous passages, the rest drawn at random (seed 20261011). |
| **Conditions** | `baseline` (plain request) · `cautious` (adds "only quote if you are certain") · `lookup` (Bible and Constitution only: the model returns a reference, the system fetches the text). |
| **Models** (v1.0) | Claude Opus 5.5, Claude Sonnet 5.5, Claude Haiku 5.5, and the previous-generation Claude Sonnet 4.6 and Claude Haiku 4.5 (Anthropic API); GPT-6 Luna, Gemini 3.1 Flash Lite, DeepSeek V4 Pro, Llama 4 Maverick (OpenRouter, each pinned to one host). Exact IDs, hosts and dates are on the leaderboard and in [`config/models.yaml`](config/models.yaml). |
| **Settings** | One user message, JSON answer, no system prompt, no tools or web search, temperature 0 where the model accepts it, up to 16,000 output tokens (8,192 for Llama 4 Maverick, its host's maximum; first-day answers that finished under the earlier 2,000-token limit were kept, see Limitations), each model's default reasoning. A fixed 10% sample is run three more times to measure run-to-run stability. |

## How scoring works

1. Model quote and source are normalised the same way: Unicode NFKC, case-folded, punctuation
   and quotation marks removed, apostrophes and in-word hyphens joined ("to-morrow" = "tomorrow"),
   verse numbers and references stripped. Word division does not count ("any thing" = "anything").
2. **Correct** = the normalised text is identical, letter for letter, to the requested passage. A
   complete quote with extra text around it still counts (flagged `OVERLONG`); a correct fragment
   does not (`incomplete`). For topic quotes, any verbatim passage of the named text counts, unless
   the stated location is wrong; whether it fits the theme is not checked.
3. Everything else is wrong, and is sorted by a word-level edit distance with an n-gram search
   over the whole source: *spelling only* (e.g. "choose" for the 1787 "chuse"), *altered*
   (≥ 80% word similarity), *wrong place* (a real passage, but not the one asked for, or the wrong
   location), *made up* (below 80% everywhere in the named edition; matches of only a few words do
   not count). This split is approximate.
4. Trick questions: the right answer is to decline. Two figures are given: how often the model
   *gave a quote*, and how often it did so *with no correction* (some answers quote a line and say
   that it is from another work, or that the passage asked for does not exist).
5. Two accuracy figures matter together: **Correct (strict)**, the share of *attempted* questions,
   which ranks the table, and **Correct of all asked**, which counts declining as not correct.

The rules are covered by tests in [`tests/`](tests/). Design decisions and their reasons:
[`DECISIONS.md`](DECISIONS.md). Original plan (DECISIONS.md
prevails where they differ): [`SPEC.md`](SPEC.md).

## Reproduce

Requires Python 3.11+ and a checkout of this repository (the benchmark commands read its data
files; only `quotecheck` works from an installed wheel).

```bash
git clone https://github.com/codebymax10/quotebench && cd quotebench
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

Everything except new model runs works without an API key:

| Stage | Command |
|---|---|
| Parse the source texts (raw files are committed; downloads only if missing) | `quotebench sources` |
| Build the test set (deterministic) | `quotebench questions` |
| Re-score the published answers, rebuild summary, charts and leaderboard | `quotebench report` |
| Print every hand-written number in the paper | `python scripts/paper_numbers.py` |
| Tests | `pytest` |
| Cost estimate, no calls | `quotebench run --estimate` |

For model runs, copy `.env.example` to `.env` and add `OPENROUTER_API_KEY` and
`ANTHROPIC_API_KEY`. All published answers in `results/raw/` count as already done, so in a fresh
clone `quotebench run` has nothing left to ask for the nine models. Every response is cached in
`results/cache.sqlite` (not committed): a run can stop at any point and resume without paying twice.

## Add a model

Add a line to [`config/models.yaml`](config/models.yaml) with the exact OpenRouter model ID (and,
ideally, `providers:` to pin one host), then run `quotebench run --estimate --models <id>`,
`quotebench run --models <id> --max-cost <usd>` and `quotebench report`. `--max-cost` caps *total*
recorded spend, which already includes the published runs: `quotebench run --estimate` prints what
is already recorded, so set the cap to that amount plus what you want to spend.

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
- Digits are ignored by the scorer, so a wrong number inside an otherwise exact quote is not caught
  (two ground truths contain digits; every correct answer to them has the right ones).
- The split of wrong answers into kinds depends on similarity thresholds that were not
  checked against human labels.
- Famous-passage lists, topics and trick questions were drafted with an AI assistant (Claude).
  They were checked by script where a script can check them, and by a second AI audit before
  release (D19); the author has **not** reviewed them line by line
  ([`DECISIONS.md`](DECISIONS.md) D18). The code and the paper were also written with Claude,
  and five of the nine models, including the top-ranked one, are Claude models. Readers should
  weigh that.
- Solo student project; not peer reviewed.

## quotecheck: check the quotations in any text

`quotecheck` finds the quotations in a text (for example an AI answer) and checks each one, word
for word, against a source you give it. It uses the benchmark's scoring code and needs no network.

```bash
quotecheck --source examples/lease.txt --input examples/answer.md
```

```python
from quotecheck import Source, check

report = check(ai_output_text, Source.from_file("contract.txt", language="en"))
for q in report.quotes:
    print(q.label, q.similarity, q.text, q.best_match, q.source_start, q.source_end)
```

Labels: `EXACT` (every word matches; the only correct label), `MINOR` (spelling only), `ALTERED`,
`FABRICATED`. Exit code: 0 all exact, 1 some not, 2 usage error. Unlike the benchmark, numbers are
compared ("30 days" is not "60 days"); `--ignore-numbers` turns that off.

It does not check paraphrases or quotations from texts it was not given, and it ignores symbols
("$" and "€" count as the same). The split between `MINOR`, `ALTERED` and `FABRICATED` is
approximate and was not checked against human labels. Details:
[`src/quotecheck/README.md`](src/quotecheck/README.md).

## Related work

The closest existing benchmarks are YouVersion's
[Bible Accuracy Benchmark](https://github.com/youversion/biblelab-bibleaccuracybenchmark)
(Bible quotation by reference, many translations, nonexistent-reference traps) and
[BibleQuoteBench](https://github.com/x4g4p3x/BibleQuoteBench) (strict closed-book recall from
three public-domain English Bibles). Most of QuoteBench's ingredients appear in earlier work; the
lookup idea, for example, is close to Yeung's
[deterministic quoting](https://mattyyeung.github.io/deterministic-quoting). What we have not
found elsewhere is the combination: five texts from different genres, next-passage and topic
tasks, misattribution traps, and a plain / cautious / lookup comparison (lookup on two texts
only), with all ground truth in the repository. Full discussion in [`PAPER.md`](PAPER.md); notes
in [`notes/`](notes/).

## Licence and citation

- Code: MIT ([`LICENSE`](LICENSE)).
- Test set (`data/`) and results (`results/`): CC BY 4.0 ([`data/LICENSE`](data/LICENSE)).
- Source texts: public domain; see [`sources/PROVENANCE.md`](sources/PROVENANCE.md).

```bibtex
@misc{quotebench2026,
  title  = {QuoteBench: How often do language models misquote famous texts?},
  author = {Maksim},
  year   = {2026},
  note   = {Version 1.0},
  url    = {https://github.com/codebymax10/quotebench}
}
```
