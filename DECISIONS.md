# Decisions

Decisions made by Maksim (see SPEC.md §2). Each entry: what was decided, the options considered, and why.

## D1 — Text list (2026-10-11)
**Decision:** all eight texts from SPEC §3: `bible_kjv`, `shakespeare`, `us_constitution`, `pride_prejudice`, `origin_species`, `bible_synodal`, `onegin`, `crime_punishment`.
**Alternatives:** the spec's minimum set (Bible ×2, Shakespeare, Constitution, one Russian novel).
**Why:** full design gives four English and three Russian-native texts plus the parallel Bible set, so language comparisons are not driven by a single text.

## D2 — Shakespeare edition (2026-10-11)
**Decision:** Project Gutenberg #100 (*The Complete Works of William Shakespeare*); Hamlet, Macbeth and Romeo and Juliet extracted from it.
**Alternatives:** separate ebooks #1524, #1533, #1513.
**Why:** one consistent edition and transcription for all three plays, so spelling and lineation conventions match.

## D3 — Constitution text (2026-10-11)
**Decision:** U.S. National Archives transcriptions (Constitution, Bill of Rights, Amendments 11–27), original 1787 spelling and capitalisation kept.
**Alternatives:** a modernised-spelling text.
**Why:** authoritative and nameable in prompts. Capitalisation is removed by normalisation; modernised spellings (e.g. "chuse" → "choose") will be scored as MINOR rather than wrong. Stated as a limitation. (Superseded by D15: a different spelling is wrong, sorted as "spelling only".)

## D4 — Positioning after related-work scan (2026-10-11)
**Finding:** YouVersion's Bible Accuracy Benchmark (pre-release, Aug 2026) already measures
verse quotation by reference with nonexistent-reference traps — but for the Bible only.
**Decision:** QuoteBench is positioned as a **cross-genre verbatim-quotation benchmark**
(scripture, law, drama, novel, science), not a Bible benchmark and never a general
hallucination benchmark. YouVersion is cited prominently; the Bible slice is one genre among five.
**Why:** the cross-genre design, continuation/topic tasks, misattribution traps and the
baseline/cautious/lookup comparison are not covered by existing work (see notes/related_work_scan.md).
**Update (2026-11-24):** that reason claimed too much. A second check found BibleQuoteBench (strict
closed-book recall from three public-domain Bibles, first commit 2026-09-04), earlier next-verse
tests (Kaiser 2024) and earlier lookup designs (Yeung 2024). The parts exist elsewhere; what we did
not find elsewhere is the combination. README and PAPER say so. The decision itself is unchanged.
See notes/related_work_check_2026-11-24.md.

## D5 — English only for v1 (2026-10-11)
**Decision:** drop the three Russian texts (`bible_synodal`, `onegin`, `crime_punishment`) from
v1. v1 texts: `bible_kjv`, `shakespeare`, `us_constitution`, `pride_prejudice`, `origin_species`.
Russian to be added in a later version.
**Supersedes:** D1 (all eight texts).
**Consequences:** no parallel KJV/Synodal set, no English-vs-Russian comparison or McNemar test
in v1; question counts in SPEC §5 need re-planning at milestone 3. Code stays language-aware
(normaliser handles ё, prompts keyed by language) so Russian can be added without redesign.
Adding Russian after v1 results are published means a new test-set version.
Research on Russian sources is kept in notes/russian_sources.md.

## D6 — Who writes the questions (2026-10-11)
**Decision:** Maksim delegated the hand-written inputs (famous-passage lists, topic themes,
trap questions) to Claude Code. They are still kept as editable CSVs in `data/handwritten/`
so Maksim can review and change them.
**Supersedes:** SPEC §2 items 2–3 ("Maksim writes these by hand").
**Consequence:** must be stated in README/PAPER limitations: traps and famous lists were
drafted by an AI model (Claude), which could make them systematically easier or harder for
some model families.

## D7 — Test set v1.0 design (2026-10-11, drafted by Claude Code under D6; not reviewed line by line, see D18)
**Composition (700 questions, seed 20261011):**
- Task 1 reference (200): KJV 50 famous + 100 random; Constitution 15 famous + 35 random.
- Task 2 continuation (250): 5 texts × (15 famous + 35 random).
- Task 3 topic (150): 30 themes per text (Shakespeare: 10 per play).
- Task 4 traps (100): KJV 30, Shakespeare 20, Constitution 20, Pride and Prejudice 15, Origin 15;
  types: nonexistent reference, misattribution, absent topic.
**Rules beyond SPEC §4:** random Task 1 passages have ≥ 6 words (one wrong word in a shorter
verse would already be FABRICATED); Constitution passages ≤ 150 words and only clauses with a
conventional citation; Darwin's run-in section headings ("X.—") never used as given or answer;
Task 2 pairs stay inside one chapter / scene and speech / Constitution run.
**Trap verification:** a misattribution is rejected if it matches its source at ≥ 0.80 (the
scorer's ALTERED level, SPEC §4); 0.50–0.80 near misses and non-machine-checkable traps were
checked by hand (`hand_checked` column). Near-miss sayings whose real counterpart a model
could fairly quote ("the love of money…", "pride goeth…") were left out on purpose.
**Lookup condition:** only for `bible_kjv` and `us_constitution`. In the other texts a reference
(act/scene, chapter) points to a whole scene or chapter, not to a quotable passage, so the
system could not "fetch the text" (SPEC §7).
**Template adaptations (config/prompts.yaml):** Task 1 names the full source ("from the King
James Version of the Bible"); Task 2 says verse / line / clause / sentence instead of always
"sentence"; the lookup template states the location format and adds "If no such passage
exists, set cannot_locate to true" (without it, a model has no instruction for traps);
misattribution traps use the Task 1 template with "the verse/line/passage that says “…”".
**Metadata:** seed, counts, repeat sample and checksums live in `data/questions.meta.json`
(a JSONL file has no header line).
**Repeat sample:** 70 questions (10 %), to be run 3 times in the baseline condition.

## D8 — Models (2026-10-11)
**Decision:** 10 models (config/models.yaml), cost-conscious: mid-priced flagships from OpenAI
(GPT-6.1 Sol), Anthropic (Claude Sonnet 5.5), Google (Gemini 3.1 Pro preview) and xAI (Grok 4.7);
small models Claude Haiku 5.5, GPT-6 Luna and Gemini 3.1 Flash Lite (the model Selah uses);
open-weights DeepSeek V4 Pro, Qwen 3.8 (2.4T) and Llama 4 Maverick.
**Alternatives:** adding Claude Opus 5.5; an ultra-cheap lineup without flagships.
**Why:** keeps all 700 questions (precision) while controlling cost through model choice. The
top-priced tiers (Claude Fable/Opus, GPT-6 Astra) are left out; state this in the limitations
("flagship" here means each provider's main mid-priced model, not its most expensive one).
Gemini 3.1 Flash Lite took the small-Google slot planned for Gemini 3.8 Flash, keeping 10 models.
**Note:** OpenAI GPT-6.x and Anthropic 5.x models do not accept a temperature parameter on
OpenRouter, so they run at their default sampling; the repeat sample measures the variation.
**Later changes:** D13 (6 models run), D17 (3 Claude models added), D18 (9 models in v1.0).

## D9 — Budget cap (2026-10-11)
**Decision:** hard cap of $25 for the full run (`--max-cost 25`).
**Context:** estimated ~$9 if models answer directly, up to ~$40 if every answer used the full
400-token limit (heavy reasoning). If the cap is hit, the run stops and can resume after a decision.

## D10 — Claude models via the Anthropic API (2026-10-11)
**Decision:** Claude Sonnet 5.5 (`claude-sonnet-5-5`) and Claude Haiku 5.5 (`claude-haiku-5-5`)
are called through the Anthropic Messages API (official `anthropic` Python SDK, ANTHROPIC_API_KEY)
instead of OpenRouter. All other models stay on OpenRouter.
**Supersedes:** SPEC §6 "OpenRouter API" for these two models.
**Why:** Maksim's choice (uses his Anthropic key/credit). Same models and same per-token prices
as on OpenRouter; requests are equivalent (one user message, max_tokens 400, no system prompt,
no tools, default thinking, no temperature — these models reject non-default sampling values
on either route).
**Differences to note in the paper:** cost is computed from token counts × list price (the
Anthropic API does not return a cost); thinking tokens are included in output tokens but not
reported separately; retries are done by the SDK (exponential backoff on 408/409/429/5xx).
The $25 cap covers spend on both routes.

## D11 — Output token limit 2,000 (2026-10-11)
**Finding (dry run, Claude Haiku 5.5 + Sonnet 5.5, 52 calls):** with the spec's 400-token limit,
12/52 answers were cut off (`stop_reason: max_tokens`) because default thinking used most of the
budget before the JSON answer — mostly long passages, so the loss would bias results. Re-asking
those 12 with 2,000 tokens: all finished (290–1,426 tokens), several were EXACT.
Evidence kept in `results/archive/`.
**Decision:** `max_tokens` = 2,000 for every model (default reasoning unchanged).
**Supersedes:** SPEC §6 "Max output tokens 400".
**Consequence:** higher cost (thinking is billed); the 400-token dry-run answers were removed
from the cache so the whole benchmark uses one setting (the runner now refuses to mix settings).
Budget cap stays $25 for now; to be revisited before the OpenRouter models with measured costs.

## D12 — Pin each OpenRouter model to one host (2026-10-11)
**Finding (OpenRouter dry run):** DeepSeek V4 Pro answers came from 13 different hosts, some
running fp4/fp8-quantised weights; Llama 4 Maverick from 2 hosts. Mixed hosts make results
irreproducible and can mix model errors with host errors.
**Decision (Claude Code, Maksim informed):** every OpenRouter model is restricted to its maker's
own API where one exists, with no fallback: OpenAI → openai; Google → google-ai-studio /
google-vertex; xAI → xai; Qwen → alibaba. DeepSeek V4 Pro and Llama 4 Maverick → novita (fp8,
as stated by OpenRouter): DeepSeek's own API was unavailable under the account's data-privacy
setting (providers that may train on prompts are excluded — left unchanged), and Llama's Google endpoint requires a
Google key; Novita states its quantisation and serves both open models. The 52 mixed-host dry-run answers (DeepSeek, Llama) were deleted and re-run.
The serving provider of every call is recorded in results.

## D13 — Final lineup: 6 models; expensive flagships not run (2026-10-11)
**Decision:** GPT-6.1 Sol, Gemini 3.1 Pro (preview), Grok 4.7 and Qwen 3.8 (2.4T) are not run.
v1 results cover 6 models: Claude Sonnet 5.5, Claude Haiku 5.5, GPT-6 Luna, Gemini 3.1 Flash
Lite (Selah's model), DeepSeek V4 Pro, Llama 4 Maverick.
**Why:** measured thinking made them cost ~$30 together, more than the remaining budget.
**Consequence (limitation to state):** SPEC §6 asked for flagships from ≥ 3 providers; v1 has
one (Claude Sonnet 5.5). OpenAI and Google appear only through their small models. Open-weights
(2) and small models (≥ 2) are covered. Total spend: $11.67 (incl. $0.10 dry-run/probe calls
archived in results/archive/).

## D14 — Strict accuracy column (2026-10-11)
**Finding:** DeepSeek V4 Pro (15 %) and GPT-6 Luna (7.5 %) often think until the 2,000-token
limit and never answer; SPEC §8 excludes UNPARSEABLE answers from rates, which favours them
(their hardest questions drop out).
**Decision (Maksim):** report, next to the SPEC "of answered" rates, an exact rate that counts
unreadable answers as not exact: (EXACT + MINOR) / (answered + UNPARSEABLE).
**Also (scorer fix, not a decision):** when a model returns several JSON answers (e.g. a
"self-correction"), the first one is scored, as SPEC §7 says; flagged MULTIPLE_ANSWERS.

## D15 — Headline metric: verbatim correctness; no human validation step (2026-10-11)
**Decision (Maksim):** every prompt asks for the passage "exactly, word for word" / "verbatim",
so a quote is **correct** only if every word matches the named edition letter for letter
(punctuation, capitals and whitespace ignored). Spelling differences (choose / 1787 "chuse",
honor / honour, washed / wash'd) and old-form swaps (has / hath) are **wrong**. A correct but
cut-short fragment is **wrong** (incomplete); a complete exact quote followed by extra text is
**correct** (flagged OVERLONG; extra text that matches nothing is flagged separately).
Wrong answers are reported in an *approximate* split: spelling only, incomplete, altered
(word similarity ≥ 0.80), real passage from the wrong place, made up.
**Why:** the benchmark measures verbatim quotation; an answer either reproduces the text or it
does not. The headline number is then fully mechanical and needs no judgement threshold.
**Supersedes:** SPEC §8 headline "Exact rate = (EXACT + MINOR)" and the human-validation step
(SPEC §8, milestone 5). The 0.97 / 0.80 thresholds now only shape the split of wrong answers,
which is labelled approximate; state in the paper that this split was not human-validated.

## D16 — Token limit 16,000; ranking by the strict score (2026-10-14)
**Finding:** at the 2,000-token limit (D11), 451 of 11,520 answers stopped before the model
answered: DeepSeek V4 Pro 281, GPT-6 Luna 144, Claude Sonnet 5.5 10, Claude Haiku 5.5 8, Llama 4
Maverick 8, Gemini 3.1 Flash Lite 0. The "of answered" rate left those questions out, so DeepSeek
ranked first (93.9 %) on 490 plain-prompt answers while its strict score was 76.7 %: the ranking
depended on our limit, not on quoting.
**Decision (Maksim):** raise `max_tokens` to 16,000 and ask every cut-off answer again; rank by
*Correct (strict)* everywhere (README table, leaderboard, figures).
**Method:** an answer that finished under 2,000 tokens is what the model would have written with
a higher limit, so it was kept; only cut-off answers were asked again (`quotebench run` now does
this whenever the limit is raised). The 451 old answers are kept in
`results/archive/cut_off_at_lower_limit/`. Llama 4 Maverick's host (Novita) allows at most 8,192
output tokens, so Llama uses 8,192 (`max_tokens` in `config/models.yaml`).
**Result:** all re-asked answers finished except DeepSeek 38 (still thinking at 16,000 tokens)
and Llama 1 (repeating one line until 8,192); these count as wrong in the strict score.
**Caveats (state in the paper):** a re-asked answer is a new sample, not a continuation of the
cut-off one: GPT-6 Luna and the Claude models do not accept temperature 0, and even at temperature
0 Llama's host gave a different, short answer to 7 of its 8 re-asked questions. Re-asking only the
cut-off questions therefore slightly favours short answers on those questions. GPT-6 Luna declined
to quote ("cannot_quote") in 73 of its 144 re-asked answers.
**Cost:** $5.66 more; total $17.33 of the $25 cap, including the replaced answers, which still
count towards the cap and the reported spend. Novita bills DeepSeek at ~$2.97 per million output
tokens, above OpenRouter's listed $1.98, so DeepSeek cost more than estimated.
**Supersedes:** D11 (2,000 tokens).

## D17 — Three more Claude models: Opus 5.5, Sonnet 4.6, Haiku 4.5 (2026-10-28)
**Decision (Maksim):** add Claude Opus 5.5 (`claude-opus-5-5`, Anthropic's top tier) and two
previous-generation models, Claude Sonnet 4.6 (`claude-sonnet-4-6`) and Claude Haiku 4.5
(`claude-haiku-4-5`), through the Anthropic API on Maksim's API credit. This is the first step
towards 10+ models spread from top to weak; OpenRouter models follow (planned: GPT-6.1 Sol,
Grok 4.7, Mistral Large 4, Qwen 3.8 Flash, Llama 3.1 8B, Ministral 3B).
**Why:** the older models show whether quoting improved between generations (Haiku 4.5 → 5.5,
Sonnet 4.6 → 5.5); Opus 5.5 adds a top-priced model, which D8 left out.
**Settings:** as for every model (SPEC §6, D16). No thinking parameter is sent, so each model
uses its default: Opus 5.5 thinks (adaptive, default effort `medium`); Sonnet 4.6 and Haiku 4.5
do not think unless asked. Sonnet 4.6 and Haiku 4.5 accept temperature, so they get
temperature 0; the 1.x Anthropic SDK has no temperature argument, so it is sent in `extra_body`.
The 5.x models do not accept temperature.
**Fix during the run:** the first attempt sent no temperature to any Claude model. The 515
calls for Sonnet 4.6 and Haiku 4.5 at the default temperature (463 answers, $0.28, and 52
rate-limit failures) are kept in
`results/archive/claude4_without_temperature/` and were asked again at temperature 0. The first
attempt also exceeded the account's limit on simultaneous requests (40 per model × 3); the
failed calls were retried at 25 per model.
**Consequence (state in the paper):** supersedes D8's note that top-priced tiers are left out:
Claude Opus 5.5 is in; Claude Fable 5.1 and GPT-6 Astra are not. Anthropic now supplies 5 of
the 9 models.
**Result:** all 5,760 calls answered (0 errors, 0 cut off at 16,000 tokens, 0 refusals). Plain
prompt, *Correct (strict)*: Opus 5.5 96.5 %, Sonnet 4.6 93.0 %, Haiku 4.5 69.6 %. Sonnet 4.6
declined 33 % of real questions ("cannot quote"), so its rate rests on 401 answers; Opus 5.5
declined 1 %, Sonnet 5.5 3 %.
**Cost:** $14.50 (Opus 5.5 $11.06, Sonnet 4.6 $2.21, Haiku 4.5 $0.94, archived answers $0.28);
project total $31.83.

## D18 — What v1.0 contains, and release (2026-11-24)
**Decisions (Maksim):**
1. **Models:** v1.0 is released with the 9 models already run. The six further models planned in
   D17 (GPT-6.1 Sol, Grok 4.7, Mistral Large 4, Qwen 3.8 Flash, Llama 3.1 8B, Ministral 3B) are
   left for a later version. Five of the nine models are Anthropic's; this stays a stated limitation.
2. **Write-up:** Maksim asked Claude Code to draft all of `PAPER.md` and the headline findings,
   including the introduction, the interpretation and the conclusion. The paper discloses this.
   Supersedes SPEC §2 item 7 and SPEC §10 ("Maksim writes …").
3. **Review of the AI-drafted questions:** Maksim has *not* reviewed the famous-passage lists,
   topics and trick questions (D6, D7) line by line. Earlier README text said they were "reviewed
   by the author"; that was wrong and has been corrected. They were checked by script where a
   script can check them (`data/trap_verification.csv`). The `hand_checked` notes in
   `data/handwritten/traps.csv` (D7) come from the same AI-assisted drafting, not from a review
   by Maksim.
4. **`quotecheck`** (SPEC §9) ships in v1.0.
5. **Release:** push, tag `v1.0` and publish a GitHub release once all checks pass.

**Budget:** the runs of D17 took project spend to $31.83, above the $25 cap of D9. No new cap was
recorded at the time; this note records it.

## D19 — Scorer corrections before release (2026-11-24)
**Finding:** a pre-release audit (Claude subagents; every ground truth against the raw files, all
traps, all near-miss and wrong-place answers, and a sample of the rest) found scorer errors. Items
1–4 and 6 make the code follow SPEC or D15 as written; item 5 changes only how wrong answers are
sorted. The rules use no question ids or model names.
1. *Chapter and volume:* "Chapter 56 (Volume III, Chapter 14)" had the volume offset added twice.
   A location must now fit exactly one real chapter; contradictory numbers are wrong.
2. *Constitution text printed without sections* (e.g. the 19th Amendment): "Section N" is read as
   paragraph N and nothing else.
3. *Passages that occur more than once:* the stated location may be any verbatim occurrence.
4. *Word division* (D15: whitespace and punctuation are ignored): "anything" / "any thing",
   "Vice-President" / "Vice President" are no longer wrong. Flag `WORD_DIVISION`.
5. *Made up:* a verbatim fragment of the passage of at least 4 words (`fragment_min_words`,
   previously 6) is *incomplete*; a near-verbatim answer (≥ 0.80) is *altered*. No effect on
   correctness.
6. *Host errors* (finish reason "error"; 2 Gemini answers) are ERROR and excluded (SPEC §6).
**Added metrics:** (a) trick questions are split: any quote given (unchanged) and quote given
*with no correction*, because 38 of 101 plain-prompt trap "failures" themselves say that the line is
from another work (flag `SOURCE_CORRECTED`) and 10 say that the passage does not exist or,
outside the stated location, that the line is not in the named text, or add a second answer that
declines (flag `SELF_RETRACTED`; 2 do both). The rules were written after reading these answers
and bring three Claude models to 0;
(b) *Correct of all asked*, which counts declining as not correct, because declining ranges from
0 % to 33 %. The ranking stays *Correct (strict)* (D16).
**Effect (plain prompt, strict):** Opus 5.5 96.5 → 97.1 %, Sonnet 4.6 93.0 → 93.5, Sonnet 5.5
91.8 → 92.3, GPT-6 Luna 84.6 → 85.6, DeepSeek 83.3 → 84.3, Haiku 5.5 83.4 → 84.0, Gemini 76.0 →
77.1; Haiku 4.5 and Llama unchanged. DeepSeek passes Haiku 5.5 (well inside the intervals).
Lookup errors 5 → 1 of 2,300. 168 of 17,280 rows changed (123 labels); no answer went from correct
to wrong.
**Also recorded here:** SPEC §8 defined MINOR by similarity ≥ 0.97 alone; the code (since the first
run) also requires that every difference is a spelling variant (`config/scoring.yaml`).
`config/scoring.yaml` is frozen from the v1.0 release on; D19 came before it.
**Second round:** three independent reviews (numbers, code, fresh clone) led to further fixes that
change no label: `SELF_RETRACTED`; topic quotes must come from the play asked about; more location
forms are read; an interrupted import of `results/raw` can no longer lead to a report on partial
data (`quotebench report` refuses incomplete models). 14 rows changed, in `flags` only.
**Caveat:** found, fixed and checked with Claude models, which are also under test.
