# Related-work verification log

All pages opened 2026-11-24. "abs" = arXiv abstract page; "html/pdf" = full text opened and searched for the specific claim (not read end to end). Methods: curl with text extraction, GitHub API, one WebFetch.

## Works in notes/related_work_scan.md

| # | Work | URL opened | Confirmed | Wrong or missing in old notes |
|---|---|---|---|---|
| 1 | YouVersion Bible Accuracy Benchmark | repo README, docs/METHODOLOGY.md, docs/FINDINGS.md, dataset/spec-v1.json, scoring.py | 18 editions, 11 languages; named edition; famous/obscure/body tiers; nonexistent references; deterministic (rapidfuzz); grades incl. wrong_verse, wrong_version, fabricated; no verse text in repo; API credentials needed; all rights reserved; last push 2026-08-11 | "Repo created 2026-08-11" is a re-creation: an earlier public copy dates from 2026-07-21 and its versions file says first release 2026-07. Declining earns no credit either (not just "not penalised"). Also holds an unranked Nicene-creed track. |
| 2 | Kaiser, Can LLMs Accurately Recall the Bible | blog post | 29 Dec 2024; six tests; 11 models; pass/partial/fail; next-verse test; NIV and KJV | Each test appears to be a single prompt; matching ignores only case and whitespace. Title has no question mark. |
| 3 | BibleBench (nwp) | repo README | 49 cases, 16 verses, KJV/NIV/ESV/NASB; exact match including punctuation; created 2025-12-27; MIT | Nothing material |
| 4 | IslamicEval 2025 | ACL Anthology page, pdf | Authors, pp. 480-493; expert-annotated Arabic answers; detection + correction + QA | It is a shared task for detection systems, not a benchmark ranking generators; second subtask is QA. Authors: 9. |
| 5 | D'Souza & Mimno | CEUR pdf | pp. 475-489; edit distance <= 30% of length; GPT-3.5, PaLM, Pythia, GPT-2; Norton anthology best predictor | "Fame proxies" is mainly anthology inclusion; one of several predictors |
| 6 | Dahl et al. | arXiv abs + html | JLA 16(1):64-93, 2024; Quotation task: any quotation from named opinion; fuzzy match; false-premise (contra-factual) queries; abstentions counted as non-hallucination | Any quotation is accepted, so it is closer to QuoteBench task 3 than to quoting a requested passage |
| 7 | Nikolic | arXiv abs + html (v3, 5 June 2026) | 37 texts; 19 + 16 + 21 = 56 models; next-word prediction; size estimation | Notes omitted that the list ALSO contains On the Origin of Species, Macbeth and Romeo and Juliet: all QuoteBench works are in it |
| 8 | Galeev | journal pdf | Vestnik BGU Filologiya 2025/4, pp. 12-21, DOI 10.18101/2686-7095-2025-4-12-21; 125 expressions; YandexGPT 4 Pro RC vs ChatGPT 4 via Copilot | Task is fill-in-the-missing-word plus naming the source; material is film lines, idioms and advertising slogans as well as literary quotations. Not cited (Russian, not in v1). |
| 9 | OWL | abs + html | EMNLP 2025; 20 books; 10 languages; ChrF++ for prefix probing | Notes: also direct probing and name cloze |
| 10 | QUILL | abs + html | authenticity checked against a quote database, then search engines; arXiv 2024 | Notes said database only. Venue beyond arXiv not confirmed |
| 11 | AttriBench | abs | COLM 2026 | Paper title is "Attribution Bias in Large Language Models" |
| 12a | Speak, Memory | abs | EMNLP 2023; name cloze; web frequency | - |
| 12b | Remember to Forget | CEUR pdf | CHR 2024, pp. 961-981; caution about name cloze | - |
| 13a | Carlini et al. 2020 | abs | title, authors | Not cited |
| 13b | Carlini et al. 2022 | abs | size, duplication, context length | Cited as arXiv 2022; venue not confirmed on page |
| 13c | Ippolito et al. | abs | title, authors | Not cited |
| 13d | "L2M2 2025" | abs + html | It is Ma et al., "Memorization: A Close Look at Books" | L2M2 is the workshop, not the paper name |
| 13e | Cooper et al. | abs | 200 books, 14 open-weight LLMs | Now COLM 2026 |
| 13f | Ahmed et al. | abs + html | four production LLMs; some public-domain books; some jailbreaking | - |
| 13g | CopyBench | abs | title, authors | Not cited |
| 14a | According to... | abs | EACL 2024; QUIP-Score | - |
| 14b | Quote-Tuning | abs | NAACL 2025 | Paper title is "Verifiable by Design: Aligning Language Models to Quote from Pre-Training Data" |
| 15 | Who Checks the Citations? | abs + html | Liu, Stammbach, Henderson, 2026; injected errors incl. verbatim misquote | Citable but not used |
| 16 | Alrajeh | abs | 120 questions, GDPR vs Saudi PDPL | Notes said "driven by fame, not language"; the abstract says jurisdiction, not language. Not cited |
| 17 | citebench | README, SCHEMA, METHODOLOGY, report.md, questions.jsonl | 300 questions; bare vs mcp arms; quotes looked up in cited cases | The tool being tested is the author's own, which the repository says; figures called preliminary. Questions ask for an authority, not for a quotation. Repo created 2026-09-23 and active to 2026-11-10 |
| 18a | Walters & Wilder | Europe PMC record | Sci. Reports 2023, DOI 10.1038/s41598-023-41032-5 (abstract) | Not cited |
| 18b | ALCE (Gao et al.) | abs | EMNLP 2023 | Not cited |
| 19a | HalluLens | abs + html | NonExistentRefusal task | - |
| 19b | AbstentionBench | abs | 20 datasets, 20 models, false premises | - |
| 19c | Sacred or Synthetic? | abs | AIES 2025 | Not cited: rulings, not quotation |
| 20 | Tow Center / CJR | cjr.org | **COULD NOT OPEN (blocked by site). Not citable.** | - |
| 21 | verbatimeter | README, PyPI record | 0.1.3 (2026-07-12), MIT; deterministic, offline; quote checking | Also measures grounding, not only quoted spans; repo active to 2026-10-26 |
| 22a | Mushtaq et al. | abs | NeurIPS 2025 workshop | Not cited |
| 22b | Rushdi et al.; Aljaji et al.; Aion-BibleQA | **not re-opened. Not citable on this check.** | - | - |

## New works found 2026-11-24

| Work | URL opened | What it is | Overlap |
|---|---|---|---|
| **BibleQuoteBench** (x4g4p3x) | README, SCORING, DATASET, trial README, file tree | Closed-book exact Bible quotation; ASV, BSB, WEB; 100 public references x 3 = 300 cases, plus committed hidden set; results for three models, 8-9 Oct 2026; first commit 2026-09-04 | HIGH for the Bible slice and for strict scoring. Predates QuoteBench (2026-10-11); missed by old scan. No traps, topic task, non-Bible text or lookup found. |
| **Hadith recall** (Nadeem et al.) | abs + html | arXiv:2611.02587, 2 Nov 2026; reference-only recall; 5 open-weight models | Medium (task 1). "Correct" = BLEU > 0.4 and cosine > 0.8 |
| **CLASSICS-EMR** | README | 15 Gutenberg novels incl. Pride and Prejudice; planned continuation and "memorable paragraph" prompts; no results; repo created 2025-07-22 | Medium by design; no results |
| **Deterministic Quoting** (Yeung) | blog (WebFetch) | April 2024; model cites a chunk, code inserts its text | Prior art for lookup |
| **Lease Clause Checker** | README, docs/details.md | Nov 2026; 38 clauses, one statute, four models; closed-book vs statute in prompt; word-for-word check | Medium; law only, postdates QuoteBench |
| CLaw | abs + html | content retrieval = recite article by index | Task 1 analogue, Chinese statutes |
| LawBench | abs + html | article recitation, ROUGE-L | as above |
| LegalCiteBench | abs | closed-book citation recovery; prompt-only abstention experiment | cautious-condition analogue |
| RECAP / EchoTrace | abs + html | 35 books, 15 public domain | extraction |
| EBU-BBC News Integrity | report pdf | 12% of 1,053 responses containing a direct quote had significant quote-accuracy issues | human-judged, news |
| BBC Representation of BBC News content in AI Assistants | report pdf | 13% of quotes sourced from BBC articles altered or absent (cover date not on the opened text; the EBU-BBC report dates it Feb 2025) | Not cited |
| Alignment Whack-a-Mole (2603.20957), Hubble (2510.19811), LabourLawBench (2601.09972), Sonnet or Not, Bot? (2406.18906), Fuxi (2503.15837) | abs only | opened, titles and authors confirmed | Not cited |

## Searches run 2026-11-24

About 16 web searches (verbatim quotation / misquotation / public-domain recall / Bible / Quran / statutes / poetry / misattributed quotes / lookup / edition fidelity / the name "QuoteBench") and 13 GitHub repository searches. Not a systematic review: no Google Scholar, ACL Anthology or Semantic Scholar sweep.

Name collisions seen on GitHub: LeonardNJU/quoteBench (shell quoting, 2026-07-12) and 7ucina/quoteBench (LLM self-knowledge, 2026-07-29) both predate this project; several price-quote projects share the name.
