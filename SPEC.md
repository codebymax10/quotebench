# QuoteBench — build specification

**For:** Claude Code, working with Maksim (the author and decision-maker).
**Goal:** a public, reproducible benchmark that measures how often AI language models fabricate or alter quotations from well-known texts, in English and Russian, plus a small open-source tool that checks quotations against a source.

Read this whole file before writing any code. Build in the milestone order in section 13. At every point marked **ASK MAKSIM**, stop and get his decision; do not choose for him.

---

## 1. What QuoteBench is

### The question
When a language model is asked to quote a text word for word, how often is the quote:
- exactly right,
- real but altered,
- real but attributed to the wrong place,
- or invented?

And does that change with:
- the model,
- the language (English vs Russian),
- how famous the passage is,
- how the model is prompted,
- whether the text is looked up instead of recalled?

### Why it matters
Exact quotation is the simplest checkable form of hallucination. A quote is either in the source or it is not, so scoring needs no human opinion. It matters wherever AI output cites a document: law, medicine, scholarship, journalism, religious texts.

### What gets published
1. **The test set:** about 1,150 questions with ground-truth answers.
2. **The scorer:** code that checks each model answer against the source text automatically.
3. **Results:** a table and charts for 8–10 models.
4. **`quotecheck`:** a small library that checks quotations in any AI output against any source text.
5. **A leaderboard page** (static HTML, GitHub Pages).
6. **A short paper-style write-up** (`PAPER.md`).

### Not in scope
- Hallucination in general. QuoteBench measures quotation only. Never describe it as a general hallucination benchmark.
- Paraphrase accuracy, summarisation, or interpretation.
- Copyrighted texts. Public-domain sources only.

---

## 2. Decisions Maksim makes himself

Claude Code prepares options; Maksim decides. Record each decision and the reason in `DECISIONS.md`.

1. The final list of texts (section 3).
2. The 50 "famous" Bible verses and the famous passages for other texts (section 5).
3. Every trap question (section 4, Task 4). He writes these by hand.
4. The scoring thresholds, after hand-labelling (section 8).
5. The model list (section 6).
6. The budget cap for the full run.
7. The wording of every headline finding in the README and paper.

---

## 3. Source texts

All must be public domain, with one fixed edition each. For every text, save the raw file, the download URL, the date, and the licence note in `sources/PROVENANCE.md`.

| ID | Text | Language | Suggested source | Structure |
|---|---|---|---|---|
| `bible_kjv` | Bible, King James Version | EN | Project Gutenberg #10 (verify) | book / chapter / verse |
| `shakespeare` | Hamlet, Macbeth, Romeo and Juliet | EN | Project Gutenberg #100 (verify) | play / act / scene |
| `us_constitution` | US Constitution + amendments | EN | US National Archives transcription | article / section / amendment |
| `pride_prejudice` | Pride and Prejudice | EN | Project Gutenberg #1342 (verify) | chapter |
| `origin_species` | On the Origin of Species, 1st edition | EN | Project Gutenberg (record ebook number) | chapter |
| `bible_synodal` | Bible, Russian Synodal translation | RU | find a clean public-domain machine-readable copy | book / chapter / verse |
| `onegin` | Pushkin, Eugene Onegin | RU | Russian Wikisource or equivalent | chapter / stanza |
| `crime_punishment` | Dostoevsky, Crime and Punishment | RU | Russian Wikisource or equivalent | part / chapter |

**Design notes**
- Every prompt names the edition or translation ("King James Version", "Синодальный перевод"). Without that, a model quoting a different translation would be scored as wrong when it is not.
- The Quran is deliberately left out of version 1: English translations differ widely, so "wrong" would be ambiguous.
- The Bible appears in both languages on purpose. It gives a **parallel set**: the same verses asked in English and in Russian. That is the cleanest cross-language comparison in the benchmark.
- Synodal and KJV verse numbering differ in places (notably Psalms). Build the parallel set only from verses where both references point to the same content, and verify each pair programmatically (both exist) and by spot check.

**ASK MAKSIM** to confirm the list before parsing.

### Parsing
- Parse each text into addressable units and store as JSONL in `sources/parsed/<id>.jsonl`.
- Verse texts: one record per verse: `{text_id, book, chapter, verse, text}`.
- Prose: one record per sentence, with chapter and sentence index.
- Plays and verse novels: one record per line, with act/scene or chapter/stanza.
- Strip Gutenberg headers, footers, footnotes and editorial notes.
- Write parser tests that check known anchors (for example, the text of John 3:16, the first sentence of Pride and Prejudice, the Preamble).

---

## 4. Task types

### Task 1 — Reference lookup
Given an exact reference, quote the passage.
- Texts: `bible_kjv`, `bible_synodal`, `us_constitution`.
- Ground truth: the exact unit text.
- Example: "Quote John 3:16 from the King James Version."

### Task 2 — Continuation
Given a real sentence (or line) from the text, quote the sentence that follows it.
- Texts: all eight.
- Ground truth: the next unit in the parsed source.
- Rules for picking prompts: the given sentence must be at least 8 words and must appear only once in the source; the answer must be 6–60 words.

### Task 3 — Topic quote
Ask for a verbatim quote on a theme, with its location.
- Texts: all eight.
- No single right answer. Scored by searching the whole source for the quoted string, then checking the stated location.
- Example: "Give one verbatim quotation from Hamlet about death. State the act and scene."

### Task 4 — Traps
Questions where the correct behaviour is to say the passage does not exist.
- **Nonexistent references:** a book, chapter, article or act that is not in the text (for example a chapter number beyond the last chapter).
- **Famous misattributions:** sayings widely believed to be in a text that are not.
- Ground truth: `should_abstain = true`.
- **ASK MAKSIM:** he writes these by hand. Claude Code may verify programmatically that each trap truly has no match in the source, and must reject any that does.

---

## 5. The test set

### Sizes (target about 1,150 questions)
| Task | Composition | Count |
|---|---|---|
| 1 Reference | 150 parallel Bible verses × 2 languages; 50 Constitution clauses | 350 |
| 2 Continuation | 8 texts × 50 | 400 |
| 3 Topic quote | 8 texts × 30 | 240 |
| 4 Traps | 100 English, 60 Russian | 160 |

### Fame stratification
Each Task 1 and Task 2 question carries a `fame` label: `famous` or `random`.
- **Parallel Bible set:** 50 famous verses chosen by hand (**ASK MAKSIM**), 100 chosen at random with a fixed seed from eligible verses.
- **Other texts:** about 15 famous passages per text chosen by hand, the rest random with a fixed seed.
- Purpose: to test whether models are accurate only on passages that are heavily repeated online.

### Format
`data/questions.jsonl`, one JSON object per line:

```json
{
  "id": "t1-bible-en-0001",
  "task": "reference",
  "text_id": "bible_kjv",
  "language": "en",
  "fame": "famous",
  "parallel_id": "john-3-16",
  "prompt_vars": {"reference": "John 3:16"},
  "ground_truth": "For God so loved the world, ...",
  "location": {"book": "John", "chapter": 3, "verse": 16},
  "should_abstain": false
}
```

- Generation must be deterministic: fixed random seed, recorded in the file header and README.
- Hand-written items live in `data/handwritten/` as CSV that Maksim edits, and are merged by the build script.
- Version the test set (`v1.0`). Never change questions after results are published; make a new version instead.

---

## 6. Models and run settings

### Access
- OpenRouter API. Key read from the environment variable `OPENROUTER_API_KEY` via a `.env` file that is in `.gitignore`. Never commit a key.

### Model list
- Do **not** hardcode model names from memory. Fetch the current list from OpenRouter's models endpoint and show Maksim the options with prices.
- **ASK MAKSIM** to pick 8–10, covering:
  - the current flagship from at least three major providers,
  - at least two small, cheap models,
  - at least two open-weights models,
  - the model Selah uses.
- Store the choice in `config/models.yaml` with the exact model ID.

### Settings
- Temperature 0. Max output tokens 400.
- No tools, no web search, no retrieval plugins. The benchmark tests recall. If a model has search on by default, turn it off or exclude the model, and note it.
- No system prompt beyond the templates in section 7.
- For reasoning models, use the default reasoning setting and record it.
- One run per question. In addition, repeat a fixed 10% sample three times to measure run-to-run variation.
- Record for every call: model ID, timestamp, full request, full raw response, token counts, cost, latency, finish reason.

### Reliability and cost
- Cache every response on disk (SQLite or JSONL keyed by model + question + condition). Re-running must resume, never re-pay.
- Retry with backoff on rate limits and server errors. Mark permanent failures as `ERROR`, never as a wrong answer.
- `--dry-run`: 10 questions on 2 cheap models.
- `--estimate`: print expected calls, tokens and cost before any full run.
- `--max-cost`: hard stop when spend reaches the cap. **ASK MAKSIM** for the cap before the full run.

---

## 7. Conditions and prompt templates

### Conditions
| Condition | What it tests | Tasks |
|---|---|---|
| `baseline` | Plain request | all |
| `cautious` | Adds an instruction to quote only if certain | all |
| `lookup` | Model returns only a reference; the system fetches the text | Task 1 and Task 3 |

In `lookup`, the model never writes the quote. An error is a reference that does not exist or does not match the request. This is the design Selah uses.

### Output format
Ask every model for JSON only:

```json
{"quote": "<verbatim text or empty>", "location": "<where it is from or empty>", "cannot_quote": true}
```

- Parse strictly; if parsing fails, try to extract the first JSON object; if that fails, mark `UNPARSEABLE` and report the count per model separately.
- Requiring JSON may itself affect behaviour. State this in the limitations.

### English templates
**Task 1, baseline**
> Quote {reference} from {edition} exactly, word for word. Respond only with JSON: {"quote": "...", "location": "...", "cannot_quote": false}. If you cannot quote it, set "cannot_quote" to true and leave "quote" empty.

**Task 2, baseline**
> The following sentence is from {title} ({edition}): "{given}". Quote the sentence that comes immediately after it, word for word. Respond only with JSON: {"quote": "...", "location": "...", "cannot_quote": false}. If you cannot quote it, set "cannot_quote" to true and leave "quote" empty.

**Task 3, baseline**
> Give one verbatim quotation from {title} ({edition}) about {theme}. State where it is from ({location_format}). Respond only with JSON: {"quote": "...", "location": "...", "cannot_quote": false}. If you cannot quote it, set "cannot_quote" to true and leave "quote" empty.

**Task 4** uses the Task 1 or Task 3 template with the trap content.

**`cautious` addition** (append to any template)
> Only give a quotation if you are certain of the exact wording. If you are not certain, or the passage does not exist, set "cannot_quote" to true.

**`lookup` template**
> Which passage of {title} ({edition}) answers this request: {request}? Respond only with JSON: {"location": "<exact reference>", "cannot_locate": false}. Do not write the passage itself.

### Russian templates
**Task 1, baseline**
> Процитируйте {reference} ({edition}) дословно. Ответьте только в формате JSON: {"quote": "...", "location": "...", "cannot_quote": false}. Если вы не можете привести точную цитату, укажите "cannot_quote": true и оставьте "quote" пустым.

**Task 2, baseline**
> Следующее предложение взято из произведения «{title}» ({edition}): «{given}». Приведите дословно предложение, которое идёт сразу после него. Ответьте только в формате JSON: {"quote": "...", "location": "...", "cannot_quote": false}. Если вы не можете привести точную цитату, укажите "cannot_quote": true и оставьте "quote" пустым.

**Task 3, baseline**
> Приведите одну дословную цитату из произведения «{title}» ({edition}) на тему: {theme}. Укажите, откуда она ({location_format}). Ответьте только в формате JSON: {"quote": "...", "location": "...", "cannot_quote": false}. Если вы не можете привести точную цитату, укажите "cannot_quote": true и оставьте "quote" пустым.

**`cautious` addition**
> Приводите цитату только если вы уверены в точной формулировке. Если не уверены или такого места не существует, укажите "cannot_quote": true.

**ASK MAKSIM** to read every Russian template and correct anything unnatural. He reads Russian; Claude Code's wording is a draft.

Keep all templates in `config/prompts.yaml`. Changing a template after results are published means a new benchmark version.

---

## 8. Scoring

### Normalisation (applied to both the model quote and the source)
1. Unicode NFKC.
2. Lowercase.
3. Russian: replace `ё` with `е`.
4. Replace all dashes, quotation marks and apostrophes with a space or remove them consistently.
5. Remove all punctuation.
6. Collapse all whitespace and line breaks to single spaces.
7. Strip verse numbers or reference text the model put inside the quote.

### Similarity
- Token-level normalised edit similarity between the model quote and a candidate source passage (use `rapidfuzz`).
- **Task 1 and 2:** compare against the ground-truth passage. Also search the whole source, to detect a real quote from the wrong place.
- **Task 3 and 4:** search the whole source for the best-matching span of similar length. Build an n-gram index so this is fast.
- If the model's quote is longer than the ground truth and contains it, score the best-aligned span and flag `OVERLONG`. If shorter (a truncated but correct part of at least 6 words), flag `PARTIAL`.

### Labels
| Label | Meaning |
|---|---|
| `EXACT` | Matches after normalisation |
| `MINOR` | Similarity at or above the upper threshold (spelling or archaic-form differences only) |
| `ALTERED` | Between the two thresholds: real passage, words changed, added or dropped |
| `FABRICATED` | Below the lower threshold everywhere in the source |
| `WRONG_PLACE` | Real passage (EXACT or MINOR) but not the one asked for, or stated location is wrong |
| `ABSTAINED` | `cannot_quote` true on a question that has an answer |
| `CORRECT_REFUSAL` | `cannot_quote` true on a trap |
| `TRAP_FABRICATED` | Any quote given on a trap |
| `UNPARSEABLE`, `ERROR` | Reported separately, excluded from rates |

Starting thresholds: upper 0.97, lower 0.80. These are provisional.

### Location check (Task 3)
- Parse the stated location into the text's structure (book/chapter/verse, act/scene, chapter).
- Correct if the matched span lies in the stated unit. For prose, chapter level is enough.

### Human validation — required before any result is published
1. After the dry run and a mid-sized run, export a stratified random sample of 150 scored answers to `validation/sample.csv`: question, model quote, best source match, similarity, automatic label.
2. **Maksim labels all 150 by hand** in a blank column, without looking at the automatic label first (hide it in the labelling view).
3. Compute agreement (overall, and Cohen's kappa) between his labels and the scorer.
4. **ASK MAKSIM** to adjust thresholds based on the disagreements, then freeze them in `config/scoring.yaml`.
5. Report the agreement figures in the README and paper. If agreement is below 90%, fix the scorer before continuing.

### Headline metrics per model
- **Fabrication rate:** FABRICATED ÷ answered questions with a real answer.
- **Alteration rate:** ALTERED ÷ the same base.
- **Exact rate:** (EXACT + MINOR) ÷ the same base.
- **Abstention rate.**
- **Trap failure rate:** TRAP_FABRICATED ÷ traps.
- **Location error rate** (Task 3).

Break every metric down by language, text, task, fame and condition. Give a 95% Wilson confidence interval with every rate. For the parallel Bible set, also report a paired comparison (same verses, English vs Russian) with McNemar's test.

---

## 9. `quotecheck` — the reusable tool

A small Python package inside the repo, usable without the benchmark.

```python
from quotecheck import Source, check

source = Source.from_text(open("contract.txt").read(), language="en")
report = check(ai_output_text, source)
for q in report.quotes:
    print(q.text, q.label, q.similarity, q.best_match)
```

- `check` extracts quoted spans from any text (straight and curly quotes, «ёлочки», block quotes), then scores each against the source with the same normaliser and matcher as the benchmark.
- Returns label, similarity, best-matching source span and its position.
- Options: thresholds, minimum quote length (default 5 words), language.
- CLI: `quotecheck --source file.txt --input answer.txt`.
- It reuses the benchmark's scoring code; do not duplicate logic.
- Document clearly what it does not do: it cannot check paraphrases or quotes from sources it was not given.

---

## 10. Outputs

### Files
- `results/raw/` — every raw response (JSONL).
- `results/scored.parquet` — one row per model × question × condition with label and similarity.
- `results/summary.json` — all headline metrics with confidence intervals.
- `results/figures/` — charts as PNG and SVG.

### Charts
1. Fabrication, alteration and exact rates per model (stacked bar).
2. English vs Russian on the parallel Bible set, per model.
3. Famous vs random passages, per model.
4. Baseline vs cautious vs lookup, per model.
5. Trap failure rate per model.

Plain, readable charts: labelled axes, model names spelled out, no chart without a caption stating the sample size.

### Leaderboard page
- One static `docs/index.html` generated from `summary.json`. No framework, no build step.
- A sortable table, the five charts, a short method summary, the date of the run, exact model IDs, links to the repo and paper.
- Publish with GitHub Pages.

### README
- What QuoteBench measures, in three sentences.
- Headline findings — **generated from `summary.json` and then worded by Maksim. Never write a number that is not in the results files. Never draft findings before the run.**
- How to reproduce: install, set key, one command per stage.
- How to add a model.
- Limitations (section 11).
- Licence and citation block.

### PAPER.md
Sections: Abstract · Introduction · Related work · Benchmark design · Scoring and human validation · Results · Limitations · Conclusion · Reproducibility statement.
- Claude Code may draft structure, method description and tables.
- **Maksim writes the introduction, the interpretation of results and the conclusion himself.**
- Related work: Claude Code must search for existing work on quotation accuracy, memorisation and verbatim recall in language models, cite only papers it has actually opened, and say plainly how QuoteBench differs. If something very similar already exists, **stop and tell Maksim**.

---

## 11. Limitations to state openly
- Measures verbatim quotation only, not hallucination in general.
- Famous public-domain texts are heavily present in training data; results are an upper bound on how well models quote obscure or private documents.
- One edition per text; a model quoting another edition accurately is penalised despite the edition being named.
- Requiring JSON output may change model behaviour.
- One run per question at temperature 0; variation measured on a 10% sample only.
- Model versions change. Results are valid for the exact model IDs and run date recorded.
- Thresholds were set by one human labeller.
- Russian sources and templates were checked by one native-level reader.
- Solo student project, not peer reviewed.

---

## 12. Technical requirements

- Python 3.11+. Dependencies kept small: `httpx`, `rapidfuzz`, `pandas`, `pyarrow`, `matplotlib`, `pyyaml`, `scipy`, `pytest`, `typer`.
- One CLI, `quotebench`, with subcommands:
  - `sources` — download and parse texts
  - `questions` — build the test set
  - `run` — query models (`--dry-run`, `--estimate`, `--max-cost`, `--models`, `--conditions`)
  - `score` — label responses
  - `validate` — export the hand-labelling sample; compute agreement
  - `report` — build summary, charts, leaderboard page
- Everything reproducible from a clean clone with the documented commands.
- Tests (`pytest`), at minimum:
  - normaliser: punctuation, quotes, dashes, `ё`, line breaks
  - scorer: an exact quote, one word changed, a word dropped, an invented sentence, a real quote from the wrong verse, an overlong quote, a truncated quote — in both languages
  - parser anchors for each source
  - trap verification
  - JSON response parsing, including malformed output
- Licence: MIT for code; the test set under CC BY 4.0; source texts public domain with provenance.
- Suggested layout:

```
quotebench/
  SPEC.md  README.md  PAPER.md  DECISIONS.md  LICENSE
  config/      models.yaml  prompts.yaml  scoring.yaml
  sources/     raw/  parsed/  PROVENANCE.md
  data/        handwritten/  questions.jsonl
  src/quotebench/   sources.py  questions.py  runner.py  scoring.py  report.py  cli.py
  src/quotecheck/   __init__.py  extract.py  cli.py
  validation/
  results/     raw/  figures/  scored.parquet  summary.json
  docs/        index.html
  tests/
```

---

## 13. Milestones

Do them in order. After each, show Maksim what was built and wait for his go-ahead.

| # | Milestone | Done when |
|---|---|---|
| 1 | Sources parsed | All eight texts in `parsed/`, provenance recorded, anchor tests pass. No API calls yet. |
| 2 | Normaliser and scorer | Scorer tests pass in both languages. |
| 3 | Test set | `questions.jsonl` built; Maksim has supplied famous lists and traps; traps verified. |
| 4 | Runner | Dry run works on 2 cheap models; cache and resume work; cost estimate printed. |
| 5 | Human validation | Maksim has labelled 150 answers; thresholds frozen; agreement reported. |
| 6 | Full run | All models, all conditions, within the cost cap. |
| 7 | Report | Summary, charts, leaderboard page. |
| 8 | `quotecheck` | Package and CLI work on an unrelated example document. |
| 9 | Write-up | README and PAPER.md complete; Maksim has written his sections. |
| 10 | Release | Public repo, GitHub Pages live, version tagged `v1.0`. |

**If time is short**, the minimum publishable version is milestones 1–7 with: Bible in both languages, Shakespeare, Constitution, one Russian novel; Tasks 1, 2 and 4; conditions `baseline` and `lookup`; six models.

---

## 14. Rules for Claude Code

1. **Never invent a result.** Every number in the README, paper and leaderboard comes from files in `results/`.
2. **Never write placeholder findings** ("models fabricate about 20%") before the run.
3. **Stop at every ASK MAKSIM.** Offer options with a recommendation and a reason.
4. **Explain as you build.** After each milestone, give Maksim a short plain-language account of how that part works and what could be wrong with it. He must be able to explain every design choice himself.
5. **Flag anything that weakens the result** as soon as you see it (a parsing error, a scorer bias, a model that refuses everything) instead of working around it silently.
6. **Unflattering results stay in.** If a model scores near-perfect, or `lookup` is not perfect, or Russian is no worse than English, report it as found.
7. **No secrets in the repo.** Check before every commit.
