# QuoteBench: How often do language models misquote famous texts?

Maksim · Version 1.0 · November 2026

*Solo student project, not peer reviewed. The text of this paper was drafted by an AI model (Claude); see [Disclosure](#disclosure).*

## Abstract

QuoteBench measures how often a language model misquotes a well-known text when asked to quote it word for word. It covers five public-domain English texts: the King James Bible, three Shakespeare plays, the U.S. Constitution, *Pride and Prejudice*, and the first edition of *On the Origin of Species*. There are 600 questions with a real answer and 100 trick questions. A quotation is correct only if every word matches a fixed edition, which is checked automatically. Nine models were tested, five of them from Anthropic.

Under a plain prompt, the share of attempted quotations that were correct ranged from 21.4% (Llama 4 Maverick, 125/585, 95% interval 18.2–24.9) to 97.1% (Claude Opus 5.5, 575/592, 95.4–98.2). Models decline at very different rates, so this share compares them on different questions. Over all 600, Claude Sonnet 4.6 falls from second to seventh, because it declined 199. All nine models were less accurate on the two prose works than on the Bible, and six were clearly more accurate on famous passages than on random ones.

The results describe verbatim quotation of famous texts only, not hallucination in general. The questions, code and paper were drafted with Claude, and Claude models rank highest. Readers should weigh that conflict.

## Introduction

A quotation claims that these exact words appear in that source. The claim matters wherever documents are cited, as in law, scholarship, journalism or religion. It can be checked mechanically: the words are in the source or they are not.

QuoteBench asks how often a requested quotation is exact, altered, misplaced or not in the source at all. It asks whether this depends on the text and on how famous the passage is. And it asks whether it helps to tell the model to quote only if certain, or to have the model name a passage while a program supplies the words.

The benchmark does not test paraphrase, interpretation or factual claims, and it is not a general hallucination benchmark. The texts are famous and probably common in training data; one study of memorisation uses all of them [20]. Results should be read as an upper bound on quoting obscure or private documents.

## Related work

**Scripture quotation.** The nearest neighbours of QuoteBench test quotation of religious text. YouVersion's Bible Accuracy Benchmark [1] asks models for verses by reference in a named edition, across 18 editions and 11 languages, scores the wording deterministically, and repeats the prompt with references that do not exist; its ground truth comes from an API that needs credentials. BibleQuoteBench [2] is closest in method: closed-book, edition-pinned recall of single verses from three public-domain English Bibles, with exact-match scoring and published results for three models; we found no nonexistent-reference questions in its documentation. Kaiser [3] ran six tests on eleven models, including a next-verse test, and BibleBench [4] contains 49 strict verse-matching cases. For Islamic texts, Nadeem et al. [5] give five open-weight models only a Hadith reference and report no correct responses among 30,000, although "correct" there is a BLEU and similarity threshold, not word identity. IslamicEval 2025 [6] is a shared task on detecting and correcting misquoted Quran verses and Hadith in Arabic answers.

**Law and poetry.** D'Souza and Mimno [7] prompt models for named poems, counting a poem as memorised when edit distance is at most 30% of its length, and find that inclusion of the poet in a well-known anthology predicts recall better than several demographic and temporal variables. In law, Dahl et al. [8] include a task that asks for any verbatim quotation from a named opinion, scored by fuzzy match, as well as questions with false premises. LawBench [9] and CLaw [10] ask models to recite Chinese statutes from an article number, and CLaw reports that most models struggle to do so faithfully. LegalCiteBench [11] measures closed-book citation recovery rather than wording; an uncertainty instruction reduced some fabrication without improving correctness.

**Memorisation and extraction.** Carlini et al. [12] relate emitted training text to model size, duplication and prompt length. Later work reconstructs some whole books, nearly verbatim, from open-weight [13, 14] and production [15] models, and RECAP [16] includes 15 public-domain books. Name-cloze studies link memorisation to how often a book appears on the web [17], though Zhang et al. [18] caution that a model may recognise a book without having memorised its text verbatim. OWL [19] extends probing across ten languages. Nikolić [20] uses 37 popular texts, among them all the works used here, but scores next-word prediction in order to estimate model size. CLASSICS-EMR [21] proposes verbatim recall of 15 public-domain novels; its repository reported no results when we read it. These studies ask what can be extracted; QuoteBench asks whether an ordinary request yields the right words.

**Producing, checking and declining quotations.** "According to" prompting [22] and Quote-Tuning [23] increase how much models quote from pre-training data. QUILL [24] evaluates whether generated quotations are authentic, and AttriBench [25] tests attribution of a quotation to its author. An EBU–BBC study [26] found significant quotation problems in 12% of assistant answers about news that contained a direct quote. Yeung [27] describes deterministic quoting, in which the model selects a passage and ordinary code supplies the text; our *lookup* condition applies the same idea without retrieved context. citebench [28] compares models with and without legal tools, and a small check of Ontario tenancy law [29] compares quotations with and without the statute in the prompt. AbstentionBench [30] and HalluLens [31] evaluate declining unanswerable questions in general. Tools such as verbatimeter [32] check quotations against a supplied source.

**How QuoteBench differs.** No single ingredient of QuoteBench is new: quotation by reference, continuation, nonexistent-reference traps, strict matching and lookup all appear above. Its contribution is their combination in one open test set. It covers five English public-domain works from different genres (scripture, drama, law, a novel and science), with one pinned edition each and strict word-level scoring; adds quotation by theme and traps built on famous misattributions and absent topics; and compares plain, cautious and, for two of the texts, lookup prompting on the same questions. Source texts, questions and raw answers are published. We found no existing benchmark with this combination, but our search was not systematic, several works cited are unreviewed repositories or preprints, and QuoteBench is English-only and limited to heavily memorised texts.

## Benchmark design

**Texts.** Each text has one fixed edition, named in every prompt. The Constitution, in the original spelling, comes from the National Archives; the others come from Project Gutenberg (see `sources/PROVENANCE.md`). Version 1.0 is in English only; planned Russian texts were left out (D5; such labels refer to `DECISIONS.md`).

**Tasks.** There are 700 questions.

1. *Reference* (200): quote a given verse or clause (Bible 150, Constitution 50).
2. *Continuation* (250, 50 per text): given a sentence, line, verse or clause, quote the next one.
3. *Topic* (150, 30 per text): give a verbatim quotation on a theme and say where it is from.
4. *Trick questions* (100): nonexistent references (38), sayings wrongly attributed to the text (60), and topics it never mentions (2). The right response is to decline.

Of the 450 reference and continuation questions, 140 are passages listed as famous and 310 were drawn at random (seed 20261011). The famous passages, themes and trick questions were drafted by Claude Code (D6, D7) and were not reviewed line by line by the author (D18). Where possible, a script checked that trick questions have no match in the source.

**Conditions.** *Plain* is the bare request. *Cautious* adds an instruction to quote only if certain of the exact wording. *Lookup* asks only for a reference, and a program fetches the text. It is run on 310 Bible and Constitution questions (200 reference, 60 topic, 50 trick), since in the other texts a chapter or scene number does not identify a quotable passage. All prompts ask for a JSON answer and allow the model to decline.

**Models.** Nine models were run on 11, 14 and 28 October 2026: Claude Opus 5.5, Sonnet 5.5, Haiku 5.5, Sonnet 4.6 and Haiku 4.5 (Anthropic API), and GPT-6 Luna, Gemini 3.1 Flash Lite, DeepSeek V4 Pro and Llama 4 Maverick (OpenRouter). OpenRouter models were restricted to named hosts, because an early test found one model served by 13 hosts, some with reduced numerical precision (D12). Fifty earlier calls without this rule are kept (24 for GPT-6 Luna, 26 for Gemini). DeepSeek and Llama were served by a third party (Novita) in fp8 and may behave differently elsewhere.

**Settings.** Each call had one user message, no system prompt, no tools and no search, with the model's default reasoning. Temperature 0 was requested where the model accepts it: Sonnet 4.6, Haiku 4.5, Gemini, DeepSeek and Llama, but not GPT-6 Luna or the Claude 5.5 models. The output limit was 16,000 tokens (8,192 for Llama, its host's maximum); the first six models were first run at 2,000, and only the answers cut off there were asked again (Limitations). Each question was asked once per condition, and 70 questions were run three more times with the plain prompt. This gives 17,280 recorded calls; two of them ended in a host error and are in no rate.

## Scoring

**What counts as correct.** Case, punctuation, verse numbers and the division of letters into words are ignored ("any thing" matches "anything"). In reference and continuation questions, the answer must contain the whole requested passage; extra text is allowed. In topic questions, the quotation must occur verbatim in the source, and the stated location must not be wrong. Its fit to the theme is not checked.

**Kinds of error.** Other answers are sorted by word-level edit distance and a search of the source: *spelling only*, *incomplete*, *altered* (at least 80% similar), *wrong place*, or *made up* (below 80% everywhere). The split is approximate. Spelling-only errors are undercounted, because one variant in a passage of eight words or fewer falls below the 97% line for that label. Minimum-length rules affect what counts as made up.

**Why there is no human validation.** The plan was for a person to label 150 answers and set thresholds. Once the headline metric became exact equality (D15), it no longer depended on a threshold, and that step was dropped. So the split of errors has not been checked against human judgement. Nor does exact matching protect against mistakes in the code or the parsed sources; several were found during this write-up (see [Limitations](#limitations)).

**Rates.**

- *Correct, strict*: correct / (answered + unfinished). Unfinished answers, with no readable response, count as wrong. Declined questions are left out. The leaderboard ranks by this rate (D14, D16).
- *Correct of all*: correct / all questions with a real answer. Declining counts as not correct.
- *Trick-question failure rate*: the share of readable answers to trick questions that gave any quotation.

One plain-prompt Gemini answer ended in an error at its host and is in no rate, so Gemini has 599 questions. Intervals are 95% Wilson intervals. Paired comparisons use the exact two-sided McNemar test. Version (a) uses all questions and counts an abstention or an unfinished answer as not correct. Version (b) uses only questions that neither model declined and counts an unfinished answer as not correct. The host error is dropped. The p-values are Holm-adjusted over all 36 pairs, separately for each version. Results are for the plain prompt and the first run unless stated otherwise.

## Results

### Ranking

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

The strict rate says how often a model is right when it does quote. But each model chooses what to attempt. Table 1 gives the outcomes over all questions.

**Table 1.** Outcomes on questions with a real answer, plain prompt, sorted by correct of all.

| Model | Correct, strict | Strict rank | Correct of all | Rank of all | Wrong quotation | Declined | Unfinished |
|---|---|---|---|---|---|---|---|
| Claude Opus 5.5 | 97.1% (95.4–98.2), n = 592 | 1 | 95.8%, 575/600 | 1 | 17 (2.8%) | 8 (1.3%) | 0 |
| Claude Sonnet 5.5 | 92.3% (89.8–94.2), n = 582 | 3 | 89.5%, 537/600 | 2 | 45 (7.5%) | 18 (3.0%) | 0 |
| DeepSeek V4 Pro | 84.3% (81.2–87.0), n = 600 | 5 | 84.3%, 506/600 | 3 | 76 (12.7%) | 0 (0.0%) | 18 |
| GPT-6 Luna | 85.6% (82.5–88.3), n = 564 | 4 | 80.5%, 483/600 | 4 | 81 (13.5%) | 36 (6.0%) | 0 |
| Gemini 3.1 Flash Lite | 77.1% (73.6–80.3), n = 595 | 7 | 76.6%, 459/599 | 5 | 136 (22.7%) | 4 (0.7%) | 0 |
| Claude Haiku 5.5 | 84.0% (80.6–87.0), n = 501 | 6 | 70.2%, 421/600 | 6 | 80 (13.3%) | 99 (16.5%) | 0 |
| Claude Sonnet 4.6 | 93.5% (90.7–95.5), n = 401 | 2 | 62.5%, 375/600 | 7 | 26 (4.3%) | 199 (33.2%) | 0 |
| Claude Haiku 4.5 | 69.6% (65.4–73.5), n = 494 | 8 | 57.3%, 344/600 | 8 | 150 (25.0%) | 106 (17.7%) | 0 |
| Llama 4 Maverick | 21.4% (18.2–24.9), n = 585 | 9 | 20.8%, 125/600 | 9 | 460 (76.7%) | 15 (2.5%) | 0 |

The orders differ in the middle. Sonnet 4.6 moves from second to seventh, DeepSeek from fifth to third, and Gemini from seventh to fifth. Neither view is simply right. Declining is better than quoting wrongly, and Sonnet 4.6 gave 26 wrong quotations against 136 for Gemini. But a model that declines the hard questions is graded on the easy ones.

On questions that both attempted (Table 2), Sonnet 4.6 and Sonnet 5.5 were not clearly different (375 and 385 correct of 401; p = 0.087, adjusted 0.261). The second place of Sonnet 4.6 is therefore not supported, and over all questions the order is strongly reversed. On shared questions Sonnet 4.6 also cannot be separated from GPT-6 Luna, DeepSeek or Gemini. GPT-6 Luna ranks above DeepSeek, yet DeepSeek was correct more often over all questions, and on shared questions the two are not separated. Haiku 5.5 ranks above Gemini, but Gemini was correct more often in both tests.

**Table 2.** Paired exact McNemar tests (Holm-adjusted p). The first eight rows are neighbours in the strict ranking; the others are used in the text.

| Strict ranks | Pair | (a) All questions: only first / only second correct | p | (b) Neither declined: n, correct first / second | p |
|---|---|---|---|---|---|
| 1–2 | Claude Opus 5.5 vs Claude Sonnet 4.6 | 203 / 3 | <0.001 | 401: 396 / 375 | <0.001 |
| 2–3 | Claude Sonnet 4.6 vs Claude Sonnet 5.5 | 9 / 171 | <0.001 | 401: 375 / 385 | 0.261 |
| 3–4 | Claude Sonnet 5.5 vs GPT-6 Luna | 70 / 16 | <0.001 | 558: 521 / 482 | <0.001 |
| 4–5 | GPT-6 Luna vs DeepSeek V4 Pro | 20 / 43 | 0.010 | 564: 483 / 500 | 0.166 |
| 5–6 | DeepSeek V4 Pro vs Claude Haiku 5.5 | 96 / 11 | <0.001 | 501: 471 / 421 | <0.001 |
| 6–7 | Claude Haiku 5.5 vs Gemini 3.1 Flash Lite | 24 / 63 | <0.001 | 497: 418 / 443 | 0.025 |
| 7–8 | Gemini 3.1 Flash Lite vs Claude Haiku 4.5 | 134 / 18 | <0.001 | 493: 420 / 343 | <0.001 |
| 8–9 | Claude Haiku 4.5 vs Llama 4 Maverick | 223 / 4 | <0.001 | 486: 338 / 124 | <0.001 |
| 6–8 | Claude Haiku 5.5 vs Claude Haiku 4.5 | 111 / 34 | <0.001 | 457: 386 / 343 | <0.001 |
| 1–3 | Claude Opus 5.5 vs Claude Sonnet 5.5 | 42 / 4 | <0.001 | 582: 566 / 537 | <0.001 |
| 3–5 | Claude Sonnet 5.5 vs DeepSeek V4 Pro | 52 / 21 | 0.001 | 582: 537 / 503 | <0.001 |
| 5–4 | DeepSeek V4 Pro vs GPT-6 Luna | 43 / 20 | 0.010 | 564: 500 / 483 | 0.166 |
| 2–7 | Claude Sonnet 4.6 vs Gemini 3.1 Flash Lite | 16 / 101 | <0.001 | 397: 372 / 364 | 0.261 |

Opus 5.5 is first by both rates, and both tests separate it from every other model. Made-up quotations ranged from 2 of 592 answers for Opus 5.5 (0.3%, 0.1–1.2) to 373 of 585 for Llama (63.8%, 59.8–67.6).

### By text

<!-- by_text:start -->
| Model | KJV Bible | Shakespeare | Constitution | Pride and Prejudice | Origin of Species |
|---|---|---|---|---|---|
| Claude Opus 5.5 | 0.0% (0/230) | 2.5% (2/80) | 0.8% (1/130) | 7.8% (6/77) | 10.7% (8/75) |
| Claude Sonnet 4.6 | 1.4% (3/208) | 18.2% (6/33) | 3.9% (5/127) | 0.0% (0/2) | 38.7% (12/31) |
| Claude Sonnet 5.5 | 1.3% (3/230) | 6.3% (5/80) | 2.3% (3/130) | 14.3% (10/70) | 33.3% (24/72) |
| GPT-6 Luna | 0.4% (1/230) | 16.7% (13/78) | 3.1% (4/130) | 38.7% (24/62) | 60.9% (39/64) |
| DeepSeek V4 Pro | 1.7% (4/230) | 17.5% (14/80) | 0.0% (0/130) | 43.8% (35/80) | 51.3% (41/80) |
| Claude Haiku 5.5 | 8.3% (19/230) | 17.8% (13/73) | 6.3% (8/128) | 54.8% (17/31) | 59.0% (23/39) |
| Gemini 3.1 Flash Lite | 2.2% (5/229) | 15.0% (12/80) | 5.6% (7/126) | 65.0% (52/80) | 75.0% (60/80) |
| Claude Haiku 4.5 | 17.4% (40/230) | 27.5% (19/69) | 28.0% (30/107) | 65.2% (30/46) | 73.8% (31/42) |
| Llama 4 Maverick | 66.7% (152/228) | 77.2% (61/79) | 77.1% (91/118) | 95.0% (76/80) | 100.0% (80/80) |

Plain prompt. Share quoted wrong (not word for word), strict base: wrong / (answered + unfinished). Declined questions are not in the base, so n differs between models.
<!-- by_text:end -->

All nine models were less accurate on the two prose works than on the Bible. DeepSeek declined nothing, so its figures are free of the selection effect: 226/230 on the Bible (98.3%, 95.6–99.3) against 84/160 on prose (52.5%, 44.8–60.1). Opus 5.5 went from 230/230 (98.4–100.0) to 138/152 (90.8%, 85.1–94.4). Cells with much abstention mean little: Sonnet 4.6 attempted 2 of 80 questions on *Pride and Prejudice*.

Only the Bible and the Constitution have reference questions, but the continuation task is the same for all texts. Counted over all questions, every model was worse on prose there. DeepSeek was right on 50/50 Bible and 39/100 prose questions, GPT-6 Luna on 50/50 and 26/100, and Opus 5.5 on 50/50 and 82/100. The median answer has 24 words for the Bible, 18 for *Pride and Prejudice* and 29.5 for *Origin*, so length alone is an unlikely explanation. Differences between editions may explain a part.

### Famous and random passages

<!-- fame:start -->
| Model | Famous passages | Random passages |
|---|---|---|
| Claude Opus 5.5 | 95.7% (134/140) | 97.7% (295/302) |
| Claude Sonnet 4.6 | 97.1% (102/105) | 95.6% (175/183) |
| Claude Sonnet 5.5 | 93.6% (131/140) | 92.1% (269/292) |
| GPT-6 Luna | 93.4% (128/137) | 83.0% (230/277) |
| DeepSeek V4 Pro | 95.0% (133/140) | 78.4% (243/310) |
| Claude Haiku 5.5 | 94.7% (125/132) | 83.5% (197/236) |
| Gemini 3.1 Flash Lite | 90.6% (125/138) | 71.7% (220/307) |
| Claude Haiku 4.5 | 87.4% (104/119) | 60.5% (141/233) |
| Llama 4 Maverick | 47.4% (63/133) | 3.6% (11/303) |

Plain prompt, quote-a-reference and what-comes-next questions. *Correct (strict)*: correct / (answered + unfinished). Declined questions are not in the base.
<!-- fame:end -->

For six of the nine models the intervals do not overlap, and famous passages were quoted more accurately. The gap was largest for Llama: 63/133 (47.4%, 39.1–55.8) against 11/303 (3.6%, 2.0–6.4). For Opus 5.5, Sonnet 5.5 and Sonnet 4.6 they overlap. Sonnet 4.6, however, declined 35 of 140 famous and 127 of 310 random passages.

"Random" does not mean obscure. Five models were right on at least 130 of 135 random Bible passages. On *Origin*, by contrast, DeepSeek was right on 12 of 15 famous and 5 of 35 random passages.

### Topic quotations and locations

When models could choose a passage on a theme, strict rates ran from 34.2% (51/149) for Llama to 97.3% (146/150) for Opus 5.5. When the quotation was real or nearly so, the stated location was wrong in 0.7% (Opus 5.5, 1/149) to 13.9% (Llama, 10/72) of cases.

### Trick questions

<!-- traps:start -->
| Model | Plain: gave a quote | Plain: of which with no correction | Cautious: gave a quote | Cautious: of which with no correction |
|---|---|---|---|---|
| Claude Opus 5.5 | 2.0% (2/100), 0.6–7.0% | 0.0% (0/100), 0.0–3.7% | 0.0% (0/100), 0.0–3.7% | 0.0% (0/100), 0.0–3.7% |
| Claude Sonnet 4.6 | 4.0% (4/100), 1.6–9.8% | 0.0% (0/100), 0.0–3.7% | 0.0% (0/100), 0.0–3.7% | 0.0% (0/100), 0.0–3.7% |
| Claude Sonnet 5.5 | 8.0% (8/100), 4.1–15.0% | 0.0% (0/100), 0.0–3.7% | 0.0% (0/100), 0.0–3.7% | 0.0% (0/100), 0.0–3.7% |
| GPT-6 Luna | 25.0% (25/100), 17.5–34.3% | 5.0% (5/100), 2.2–11.2% | 5.0% (5/100), 2.2–11.2% | 5.0% (5/100), 2.2–11.2% |
| DeepSeek V4 Pro | 4.0% (4/99), 1.6–9.9% | 3.0% (3/99), 1.0–8.5% | 0.0% (0/99), 0.0–3.7% | 0.0% (0/99), 0.0–3.7% |
| Claude Haiku 5.5 | 6.0% (6/100), 2.8–12.5% | 4.0% (4/100), 1.6–9.8% | 0.0% (0/100), 0.0–3.7% | 0.0% (0/100), 0.0–3.7% |
| Gemini 3.1 Flash Lite | 17.0% (17/100), 10.9–25.5% | 15.0% (15/100), 9.3–23.3% | 12.2% (12/98), 7.1–20.2% | 11.2% (11/98), 6.4–19.0% |
| Claude Haiku 4.5 | 11.0% (11/100), 6.3–18.6% | 8.0% (8/100), 4.1–15.0% | 3.0% (3/100), 1.0–8.5% | 3.0% (3/100), 1.0–8.5% |
| Llama 4 Maverick | 24.0% (24/100), 16.7–33.2% | 20.0% (20/100), 13.3–28.9% | 13.0% (13/100), 7.8–21.0% | 13.0% (13/100), 7.8–21.0% |

Trick questions (readable answers), where the right answer is that there is nothing to quote. *Gave a quote on a trick question*: gave a quote although there is none to give; a failure, corrected or not. An answer marked `cannot_quote` counts as declining, even if it also contains a quote. *Of which with no correction*: nowhere in the answer does it say that the line is not from the named text or that the passage asked for does not exist, or take the quote back (found by word rules; naming another place in the same text without comment is not a correction). Both are shares of all trick questions; k/n and 95% Wilson intervals.
<!-- traps:end -->

Any quotation offered as an answer to a trick question counts as a failure; an answer that sets "cannot_quote" to true counts as declining even if it also contains a quotation (six plain-prompt answers: Haiku 4.5 three, Gemini two, Llama one). Table 3 shows that this mixes different behaviours. Many answers gave the misattributed saying and stated its true origin: for "All the world's a stage", requested from *Hamlet*, GPT-6 Luna gave the location "As You Like It, Act II, Scene VII (not Hamlet)".

**Table 3.** Failures on trick questions by type, plain prompt.

| Model | Nonexistent reference | Misattribution | Absent topic | All | Corrected the source | Took it back | No correction |
|---|---|---|---|---|---|---|---|
| Claude Opus 5.5 | 0/38 | 2/60 | 0/2 | 2/100, 2.0% (0.6–7.0) | 2 | 0 | 0/100, 0.0% (0.0–3.7) |
| Claude Sonnet 4.6 | 1/38 | 3/60 | 0/2 | 4/100, 4.0% (1.6–9.8) | 3 | 3 | 0/100, 0.0% (0.0–3.7) |
| Claude Sonnet 5.5 | 0/38 | 8/60 | 0/2 | 8/100, 8.0% (4.1–15.0) | 8 | 0 | 0/100, 0.0% (0.0–3.7) |
| GPT-6 Luna | 2/38 | 23/60 | 0/2 | 25/100, 25.0% (17.5–34.3) | 20 | 0 | 5/100, 5.0% (2.2–11.2) |
| DeepSeek V4 Pro | 2/38 | 2/59 | 0/2 | 4/99, 4.0% (1.6–9.9) | 1 | 0 | 3/99, 3.0% (1.0–8.5) |
| Claude Haiku 5.5 | 4/38 | 2/60 | 0/2 | 6/100, 6.0% (2.8–12.5) | 2 | 0 | 4/100, 4.0% (1.6–9.8) |
| Gemini 3.1 Flash Lite | 10/38 | 7/60 | 0/2 | 17/100, 17.0% (10.9–25.5) | 2 | 0 | 15/100, 15.0% (9.3–23.3) |
| Claude Haiku 4.5 | 10/38 | 1/60 | 0/2 | 11/100, 11.0% (6.3–18.6) | 0 | 3 | 8/100, 8.0% (4.1–15.0) |
| Llama 4 Maverick | 17/38 | 7/60 | 0/2 | 24/100, 24.0% (16.7–33.2) | 0 | 4 | 20/100, 20.0% (13.3–28.9) |

*Corrected the source* counts failures in which the answer itself denies that the quotation is from the named text, or gives another work as its origin. *Took it back* counts failures in which the answer says elsewhere that the passage asked for does not exist or, outside its stated location, that the line is not in the named text, or adds a second answer that declines. An answer can be in both groups; *no correction* means neither. The word rules that decide this were written after the answers had been read and checked by the same AI on the same answers, so they are in-sample and not validated by a person. Naming another place in the same text without comment is not a correction. Of 101 failures, 38 corrected the source, 10 took the quotation back (2 did both), and 55 did neither. The 38 include 20 of 25 for GPT-6 Luna and all failures of Opus 5.5 and Sonnet 5.5. To say that GPT-6 Luna "was fooled by a quarter of the trick questions" would be wrong.

Nor is such a quotation always invented: in 32 of 101 failures the words do occur in the source, at another place or in another of the three plays. One question, which six models failed, asks for Chapter XV of *Origin*, whose first edition has 14 chapters. Some models may have had another edition in mind; this was not checked.

### Prompting: plain, cautious, lookup

<!-- conditions:start -->
| Model | Plain | Cautious (only if sure) | Lookup |
|---|---|---|---|
| Claude Opus 5.5 | 0.0% (0/260) | 0.4% (1/260) | 0.0% (0/258) |
| Claude Sonnet 4.6 | 1.6% (4/248) | 1.1% (2/180) | 0.0% (0/258) |
| Claude Sonnet 5.5 | 1.9% (5/260) | 1.5% (4/260) | 0.0% (0/259) |
| GPT-6 Luna | 1.2% (3/260) | 0.8% (2/260) | 0.4% (1/260) |
| DeepSeek V4 Pro | 1.5% (4/260) | 1.9% (5/260) | 0.4% (1/259) |
| Claude Haiku 5.5 | 7.3% (19/259) | 7.4% (19/258) | 0.0% (0/237) |
| Gemini 3.1 Flash Lite | 1.6% (4/258) | 1.6% (4/258) | 0.0% (0/259) |
| Claude Haiku 4.5 | 15.3% (39/255) | 15.1% (38/251) | 0.0% (0/259) |
| Llama 4 Maverick | 65.6% (166/253) | 66.8% (167/250) | 0.0% (0/252) |

The same 310 Bible and Constitution questions in all three conditions; the trick questions among them are not in these rates. Share wrong: wrong / (answered + unfinished), unfinished counted as wrong, declined questions not in the base. Plain and cautious: not word for word. Lookup: the reference is nonexistent or not the one asked for.
<!-- conditions:end -->

On this subset caution changed little, except that Sonnet 4.6 went from 12 to 80 declined questions of 260. Over all 600 questions, caution reduced wrong quotations for Haiku 4.5 (150 to 98), Sonnet 4.6 (26 to 7), GPT-6 Luna (81 to 59), Haiku 5.5 (80 to 59) and, weakly, Llama (460 to 441); unadjusted McNemar p from <0.001 to 0.018 (after Holm adjustment over the nine models, Llama's change is not significant at 0.05). It made no detectable difference for the other four. Correct answers stayed level for GPT-6 Luna (483 to 484) and Haiku 5.5 (421 to 424) but fell for Haiku 4.5 (344 to 323) and Sonnet 4.6 (375 to 265). Trick-question failures fell for every model.

In lookup the quotation is correct by construction, because a program copies it. Only the reference is tested. On reference questions the prompt already contains the reference: 1,791 of 1,800 answers repeated it and 9 declined, which says almost nothing about knowledge of the text. On topic questions any existing reference counts. Over both tasks, 1 of 2,300 answers named a reference that does not exist (GPT-6 Luna's "Article VI, Section 2, Clause 2", arguably Article VI, Clause 2 with a spurious section number). On the 50 trick questions, all models together failed 4 of 450 times, against 21 with the plain prompt and 4 with the cautious prompt. Lookup can reduce coverage: Haiku 5.5 declined 23 of 60 topic questions. The design removes wording errors, and invalid references were rare for these two texts. That does not show that the passage found is the one a user needs.

### Stability

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

Stability measures consistency of the scorer's label, not accuracy. Gemini and Haiku 4.5 had the same label on all 70 questions (94.8–100.0). Temperature 0 did not guarantee this: Llama had it on 47/70 (67.1%, 55.5–77.0) and DeepSeek on 58/70 (82.9%, 72.4–89.9). Of the 62 repeated questions with a real answer, up to 8 (DeepSeek, Llama) were right in some runs only. The intervals in this paper do not include this variation.

### Two generations of Claude models

Haiku 5.5 was better than Haiku 4.5: 421 against 344 correct of 600, and 386 against 343 on the 457 questions that both attempted (both adjusted p < 0.001). Sonnet 5.5 was correct on 537 questions and Sonnet 4.6 on 375, but most of that difference is coverage: on the 401 shared questions the two were not clearly different. The newer Sonnet quotes more; it is not shown to quote more accurately where both try.

These comparisons do not isolate a model generation. The 4.x models ran at temperature 0 and, by default, do not think before answering; the 5.5 models ran at default sampling with default thinking. Mean output per call was 52 tokens for Sonnet 4.6, 292 for Sonnet 5.5, 75 for Haiku 4.5 and 366 for Haiku 5.5.

## Limitations

**Scope and models.** The numbers hold for five famous English texts and for the model versions, hosts and dates recorded. Only Anthropic is represented by its main and top models; OpenAI and Google appear through small ones. The larger models of other makers were left out for cost (D13), yet three more Claude models were added later (D17). Because of this asymmetry, the all-Claude top three says nothing about other makers' best models. The results do not compare companies.

**Selection through abstention.** The official ranking and the breakdowns leave out declined questions. An answer that sets `cannot_quote` but also gives a quotation counts as declined (20 by Haiku 4.5, 4 by other models).

**Metrics changed after results were seen.** The strict rate, the 16,000-token limit and the ranking rule came after early results (D14–D16); under the previous rule DeepSeek ranked first. The reasons are documented, but the choices were not fixed in advance.

**Scorer corrected before release (D19).** During the write-up, AI review of the answers led to changes in the scorer. Three mistakes had marked right locations as wrong. Word division is now ignored, following the D15 rule on whitespace; this reading was adopted after the results were seen. The split between made-up and other errors changed, and host errors became a label of their own. Of 17,280 answers, 123 changed label, and no correct answer became wrong. Table 4 shows the effect; DeepSeek moved ahead of Haiku 5.5. Other errors may remain.

**Table 4.** Correct answers and strict rate before and after the scorer changes, plain prompt.

| Model | Correct before | Correct after | Gain | Strict before | Strict after | Strict rank |
|---|---|---|---|---|---|---|
| Claude Opus 5.5 | 571 | 575 | +4 | 96.5% | 97.1% | 1 → 1 |
| Claude Sonnet 4.6 | 373 | 375 | +2 | 93.0% | 93.5% | 2 → 2 |
| Claude Sonnet 5.5 | 534 | 537 | +3 | 91.8% | 92.3% | 3 → 3 |
| GPT-6 Luna | 477 | 483 | +6 | 84.6% | 85.6% | 4 → 4 |
| DeepSeek V4 Pro | 500 | 506 | +6 | 83.3% | 84.3% | 6 → 5 |
| Claude Haiku 5.5 | 418 | 421 | +3 | 83.4% | 84.0% | 5 → 6 |
| Gemini 3.1 Flash Lite | 453 | 459 | +6 | 76.0% | 77.1% | 7 → 7 |
| Claude Haiku 4.5 | 344 | 344 | +0 | 69.6% | 69.6% | 8 → 8 |
| Llama 4 Maverick | 125 | 125 | +0 | 21.4% | 21.4% | 9 → 9 |

**Re-asked answers (D16).** The first run stopped 451 answers at 2,000 tokens. Only those were asked again, with a limit of 16,000 (8,192 for Llama), and a repeated answer is a new sample. Of 110 plain-prompt questions re-asked for DeepSeek, 42 were then right, 50 wrong and 18 unfinished; on its other 490 it was right on 464. Of 65 for GPT-6 Luna, 16 were right and 30 declined.

**One edition.** A correct quotation from another edition counts as wrong, and the Gutenberg file of *Pride and Prejudice* (#1342) may differ from the texts models know. For its second sentence, five of eight answers had "considered the rightful property" where this file has "considered as the rightful property"; whether that is another edition's wording was not checked. Spelling is strict: "livest" for "liv'st" is an error.

**Contestable items.** In `t2-shakespeare-0003` eight of nine models stopped at the end of the sentence, two words before the end of the printed line, and were marked incomplete.

**Format and sample size.** Requiring JSON may change behaviour. Each question was asked once, per-text cells are small, and stability rests on 70 questions. The questions are not a sample from a defined population, so the intervals describe uncertainty within this design only.

**Contamination.** The texts, and now the questions and answers, are public. Later models may be trained on them.

**No human check.** Neither the split of errors, nor the trick questions, nor the famous lists were validated by a person.

## Conclusion

On famous English texts, the models tested differed widely in how reliably they reproduce exact words: the best was right on 575 of 600 questions and the weakest on 125. The kind of text mattered as well. GPT-6 Luna and Gemini were right on more than 97% of the Bible questions but on at most 40% of those on the two prose works. Willingness to decline changes a model's apparent quality, and a single ranking hides this. Caution reduced wrong quotations for some models, at a cost in coverage that ranged from none to large. Lookup removes wording errors by design but leaves open whether the right passage was chosen.

Even the best model misquoted some passages from widely copied texts. A model's quotation should be checked against its source, and such a check can be automated.

## Reproducibility statement

The repository contains the source texts with checksums, the test set with its seed, the prompts, the scoring rules, all raw responses with dates and hosts, the scored table and the summary. Re-scoring needs no API key. `quotebench report` regenerates the tables between markers in this file, and `scripts/paper_numbers.py` prints the hand-written result figures. Re-running the models would not give identical answers. Code is under the MIT licence; the test set and results are under CC BY 4.0.

The repository also contains `quotecheck`, a tool that finds the quotations in a text and checks them against a given source with the benchmark's matching code. Unlike the benchmark, it compares numbers by default. It does not check paraphrases.

## Disclosure

**AI drafting.** All of this paper, including introduction, interpretation and conclusion, was drafted by Claude at the author's request; the original plan was that the author would write those parts. The code was written with Claude. The famous-passage lists, themes and trick questions were drafted by Claude and not reviewed line by line by the author; the `hand_checked` notes in the trick-question file come from the same drafting.

**Conflict of interest.** Five of the nine models are Anthropic's. Anthropic's Claude drafted the questions, helped write and correct the scorer, and drafted this interpretation. Claude models hold the first three places in the strict ranking and the first two over all questions. Mechanical scoring does not remove the room for bias: the choice of passages, trick questions, prompts and metrics could favour a model family without anyone intending it. Nothing in this study can rule that out. The scorer changes added 6 correct answers each for GPT-6 Luna, DeepSeek and Gemini, and 0 to 4 for the Claude models; Table 4 allows readers to undo them. The word rules behind *no correction* were also written by Claude and bring three Claude models (Opus 5.5, Sonnet 5.5, Sonnet 4.6) to zero.

**Selah.** Gemini 3.1 Flash Lite was included because it is the model used by Selah, which the project specification names but does not describe; the specification also says that lookup is the design Selah uses. A reader may treat this as a possible interest in those two results. Gemini was run and scored like the other models.

## References

1. YouVersion. *Bible Accuracy Benchmark*. GitHub repository, 2026 (not peer reviewed). https://github.com/youversion/biblelab-bibleaccuracybenchmark
2. x4g4p3x (GitHub username). *BibleQuoteBench*. GitHub repository, v0.2, 2026 (not peer reviewed). https://github.com/x4g4p3x/BibleQuoteBench
3. Benjamin Kaiser. *Can LLMs Accurately Recall the Bible*. Blog post, 29 December 2024. https://benkaiser.dev/can-llms-accurately-recall-the-bible/
4. nwp (GitHub username). *BibleBench*. GitHub repository, 2025 (not peer reviewed). https://github.com/nwp/biblebench
5. Dayam Nadeem, Safdar Mustafa, Ameen Ur Rehman, Shahab Saquib Sohail, Mohammad Nadeem, Usman Naseem. *They Know Where It Is, But Not What It Says: A Bilingual Hallucination Benchmark of Hadith Recall in Open LLMs*. arXiv:2611.02587, 2026. https://arxiv.org/abs/2611.02587
6. Hamdy Mubarak, Rana Malhas, Watheq Mansour, Abubakr Mohamed, Mahmoud Fawzi, Majd Hawasly, Tamer Elsayed, Kareem Darwish, Walid Magdy. *IslamicEval 2025: The First Shared Task of Capturing LLMs Hallucination in Islamic Content*. Proc. Third Arabic NLP Conference: Shared Tasks, 2025, pp. 480–493. https://aclanthology.org/2025.arabicnlp-sharedtasks.67/
7. Lyra D'Souza, David Mimno. *The Chatbot and the Canon: Poetry Memorization in LLMs*. CHR 2023, CEUR-WS vol. 3558, pp. 475–489. https://ceur-ws.org/Vol-3558/paper5712.pdf
8. Matthew Dahl, Varun Magesh, Mirac Suzgun, Daniel E. Ho. *Large Legal Fictions: Profiling Legal Hallucinations in Large Language Models*. Journal of Legal Analysis 16(1):64–93, 2024. https://arxiv.org/abs/2401.01301
9. Zhiwei Fei, Xiaoyu Shen, Dawei Zhu, Fengzhe Zhou, Zhuo Han, Songyang Zhang, Kai Chen, Zongwen Shen, Jidong Ge. *LawBench: Benchmarking Legal Knowledge of Large Language Models*. arXiv:2309.16289, 2023. https://arxiv.org/abs/2309.16289
10. Xinzhe Xu, Liang Zhao, Hongshen Xu, Chen Chen. *CLaw: Benchmarking Chinese Legal Knowledge in Large Language Models – A Fine-grained Corpus and Reasoning Analysis*. arXiv:2509.21208, 2025. https://arxiv.org/abs/2509.21208
11. Sijia Chen, Hang Yin, Shunfan Zhou. *LegalCiteBench: Evaluating Citation Reliability in Legal Language Models*. arXiv:2605.10186, 2026. https://arxiv.org/abs/2605.10186
12. Nicholas Carlini, Daphne Ippolito, Matthew Jagielski, Katherine Lee, Florian Tramèr, Chiyuan Zhang. *Quantifying Memorization Across Neural Language Models*. arXiv:2202.07646, 2022. https://arxiv.org/abs/2202.07646
13. Iris Ma, Ian Domingo, Alberto Krone-Martins, Pierre Baldi, Cristina V. Lopes. *Memorization: A Close Look at Books*. L2M2 Workshop at ACL 2025. https://arxiv.org/abs/2504.12549
14. A. Feder Cooper, Mark A. Lemley, Allison Casasola, Ahmed Ahmed, Aaron Gokaslan, Amy B. Cyphert, Christopher De Sa, Daniel E. Ho, Percy Liang. *Extracting memorized pieces of (copyrighted) books from open-weight language models*. COLM 2026 (arXiv 2025). https://arxiv.org/abs/2505.12546
15. Ahmed Ahmed, A. Feder Cooper, Sanmi Koyejo, Percy Liang. *Extracting books from production language models*. arXiv:2601.02671, 2026. https://arxiv.org/abs/2601.02671
16. André V. Duarte, Xuying Li, Bin Zeng, Arlindo L. Oliveira, Lei Li, Zhuo Li. *RECAP: Reproducing Copyrighted Data from LLMs Training with an Agentic Pipeline*. arXiv:2510.25941, 2025. https://arxiv.org/abs/2510.25941
17. Kent K. Chang, Mackenzie Cramer, Sandeep Soni, David Bamman. *Speak, Memory: An Archaeology of Books Known to ChatGPT/GPT-4*. EMNLP 2023. https://arxiv.org/abs/2305.00118
18. Xinhao Zhang, Olga Seminck, Pascal Amsili. *Remember to Forget: A Study on Verbatim Memorization of Literature in Large Language Models*. CHR 2024, CEUR-WS vol. 3834, pp. 961–981. https://ceur-ws.org/Vol-3834/paper96.pdf
19. Alisha Srivastava, Emir Korukluoglu, Minh Nhat Le, Duyen Tran, Chau Minh Pham, Marzena Karpinska, Mohit Iyyer. *OWL: Probing Cross-Lingual Recall of Memorized Texts via World Literature*. EMNLP 2025. https://arxiv.org/abs/2505.22945
20. Ivica Nikolić. *Inferring the Size of Large Language Models From Popular Text Memorization*. arXiv:2605.29223, 2026. https://arxiv.org/abs/2605.29223
21. sourabhmadur (GitHub username). *CLASSICS-EMR: Measuring Verbatim Recall of Public-Domain Classics in LLMs*. GitHub repository, 2025–2026 (no results published). https://github.com/sourabhmadur/classics-benchmark
22. Orion Weller, Marc Marone, Nathaniel Weir, Dawn Lawrie, Daniel Khashabi, Benjamin Van Durme. *"According to …": Prompting Language Models Improves Quoting from Pre-Training Data*. EACL 2024. https://arxiv.org/abs/2305.13252
23. Jingyu Zhang, Marc Marone, Tianjian Li, Benjamin Van Durme, Daniel Khashabi. *Verifiable by Design: Aligning Language Models to Quote from Pre-Training Data*. NAACL 2025. https://arxiv.org/abs/2404.03862
24. Jin Xiao, Bowei Zhang, Qianyu He, Jiaqing Liang, Feng Wei, Jinglei Chen, Zujie Liang, Deqing Yang, Yanghua Xiao. *QUILL: Quotation Generation Enhancement of Large Language Models*. arXiv:2411.03675, 2024. https://arxiv.org/abs/2411.03675
25. Eliza Berman, Bella Chang, Daniel B. Neill, Emily Black. *Attribution Bias in Large Language Models*. COLM 2026. https://arxiv.org/abs/2604.05224
26. European Broadcasting Union and BBC. *News Integrity in AI Assistants: An international PSM study*. Report, October 2025. https://www.bbc.co.uk/aboutthebbc/documents/news-integrity-in-ai-assistants-report.pdf
27. Matt Yeung. *Deterministic Quoting: Making LLMs Safer for Healthcare*. Blog post, April 2024. https://mattyyeung.github.io/deterministic-quoting
28. Graham Syfert (GitHub: Gwonk1). *citebench*. GitHub repository, 2026 (not peer reviewed). https://github.com/Gwonk1/citebench
29. present42 (GitHub username). *Lease Clause Checker*. GitHub repository, 2026 (not peer reviewed). https://github.com/present42/lease-clause-checker
30. Polina Kirichenko, Mark Ibrahim, Kamalika Chaudhuri, Samuel J. Bell. *AbstentionBench: Reasoning LLMs Fail on Unanswerable Questions*. arXiv:2506.09038, 2025. https://arxiv.org/abs/2506.09038
31. Yejin Bang, Ziwei Ji, Alan Schelten, Anthony Hartshorn, Tara Fowler, Cheng Zhang, Nicola Cancedda, Pascale Fung. *HalluLens: LLM Hallucination Benchmark*. arXiv:2504.17550, 2025. https://arxiv.org/abs/2504.17550
32. Pierre-Olivier Bonin. *verbatimeter*. Python package, v0.1.3, 2026. https://github.com/pierreolivierbonin/verbatimeter
