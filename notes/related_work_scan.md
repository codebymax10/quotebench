# Related-work scan (2026-10-11)

Working notes for PAPER.md §Related work. Every item was opened (abstract at minimum; for most,
method section / README / code) by a research subagent on 2026-10-11. Items marked ✔ were
additionally re-opened and checked by hand in the main session. Before citing anything in the
paper, re-open it and confirm the claim.

## Closest

1. ✔ **YouVersion — Bible Accuracy Benchmark** (GitHub, pre-release, repo created 2026-08-11,
   "All rights reserved", open licence under review). <https://github.com/youversion/biblelab-bibleaccuracybenchmark>
   "Quote John 3:16 in the NIV" across 18 editions / 11 languages (incl. Russian Synodal),
   famous vs obscure tiers, deterministic fuzzy-match scoring (rapidfuzz), graded labels incl.
   wrong_verse / wrong_version / fabricated; paired hallucination track with nonexistent
   references (Psalm 153:1, "Judas 5:12", deuterocanon from a Protestant edition) where
   declining is not penalised. Ground truth fetched from YouVersion's API (not reproducible
   without credentials); no verse text in repo; sample redrawn each refresh.
   **Overlap:** QuoteBench Task 1 (Bible) + nonexistent-reference traps + fame strata.
   **Not covered there:** non-Bible genres, continuation / topic tasks, misattribution traps,
   cautious vs lookup conditions, open reproducible ground truth.
2. ✔ **Kaiser, "Can LLMs Accurately Recall the Bible"** (blog + code, Dec 2024).
   <https://benkaiser.dev/can-llms-accurately-recall-the-bible/> — six tests incl. next verse,
   ~11 models, pass/partial/fail, English only.
3. **BibleBench** (nwp, GitHub, MIT, 2025) <https://github.com/nwp/biblebench> — 49 exact-match
   verse cases in 4 English translations inside a theology suite.
4. **IslamicEval 2025** (Mubarak et al., ArabicNLP 2025 shared task)
   <https://aclanthology.org/2025.arabicnlp-sharedtasks.67/> — expert-annotated Quran/Hadith
   quotation correctness in free-form answers, Arabic only.
5. **D'Souza & Mimno, "The Chatbot and the Canon: Poetry Memorization in LLMs"** (CHR 2023)
   <https://ceur-ws.org/Vol-3558/paper5712.pdf> — poems by title/author, Levenshtein ≤30%
   threshold, fame proxies predict recall; English only, binary label.
6. **Dahl, Magesh, Suzgun & Ho, "Large Legal Fictions"** (J. Legal Analysis 2024)
   <https://arxiv.org/html/2401.01301v2> — includes a quote-the-opinion task scored by fuzzy
   match; false-premise probes with abstention.
7. **Nikolic, "Inferring the Size of LLMs From Popular Text Memorization"** (arXiv 2026)
   <https://arxiv.org/abs/2605.29223> — next-word accuracy on 37 popular texts incl. Bible,
   Constitution, Hamlet, Pride and Prejudice; 56 models; goal is size estimation.
8. **Галеев, «Галлюцинации языковых моделей в зеркале прецедентных выражений»** (Вестник БГУ.
   Филология, 2025) <https://journals.bsu.ru/content/articles/4960.pdf> — 125 famous Russian
   phrases, manual analysis, YandexGPT vs GPT-4. Only Russian-language study found.

## Adjacent

9. **OWL** (Srivastava et al., EMNLP 2025) <https://arxiv.org/abs/2505.22945> — cross-lingual
   book memorisation, 10 languages (no Russian), ChrF++.
10. **QUILL** (Xiao et al., 2024) <https://arxiv.org/html/2411.03675v2> — quote generation,
    authenticity vs quote KB, EN/ZH.
11. **AttriBench** (Berman et al., COLM 2026) <https://arxiv.org/abs/2604.05224> — quote → author attribution bias.
12. **Speak, Memory** (Chang et al., EMNLP 2023) <https://arxiv.org/abs/2305.00118>;
    **Remember to Forget** (Zhang, Seminck & Amsili, CHR 2024) <https://ceur-ws.org/Vol-3834/paper96.pdf> — name-cloze book memorisation.
13. Memorisation/extraction: Carlini et al. 2020 <https://arxiv.org/abs/2012.07805>, 2022
    <https://arxiv.org/abs/2202.07646>; Ippolito et al. <https://arxiv.org/html/2210.17546>;
    L2M2 2025 <https://arxiv.org/abs/2504.12549>; Cooper et al. <https://arxiv.org/abs/2505.12546>;
    Ahmed et al. <https://arxiv.org/abs/2601.02671>; CopyBench <https://arxiv.org/abs/2407.07087>.
14. "According to…" prompting (Weller et al., EACL 2024) <https://arxiv.org/abs/2305.13252>;
    Quote-Tuning (Zhang et al., NAACL 2025) <https://arxiv.org/abs/2404.03862>.
15. **Who Checks the Citations?** (Liu, Stammbach & Henderson, 2026)
    <https://arxiv.org/html/2606.21155> — legal citation-error detectors incl. verbatim misquotes.
16. **Do LLMs Fabricate Legal Citations?** (Alrajeh, 2026) <https://arxiv.org/abs/2607.11127>
    — Arabic vs English, trap questions; fabrication driven by fame, not language.
17. **citebench** (GitHub 2026) <https://github.com/Gwonk1/citebench> — legal citations, bare vs lookup tool.
18. Fabricated references: Walters & Wilder, Sci. Reports 2023 (PMC10484980); ALCE (Gao et al., EMNLP 2023) <https://arxiv.org/abs/2305.14627>.
19. Abstention: HalluLens <https://arxiv.org/html/2504.17550>; AbstentionBench
    <https://arxiv.org/abs/2506.09038>; Sacred or Synthetic? (AIES 2025) <https://arxiv.org/abs/2508.08287>.
20. Tow Center / CJR, "AI Search Has a Citation Problem" (2025).
21. ✔ **verbatimeter** 0.1.3 (PyPI 2026) <https://github.com/pierreolivierbonin/verbatimeter> —
    deterministic offline checker of quoted spans vs source. **Overlaps with `quotecheck`.**
22. Smaller: Rushdi et al. (ICML 2026 workshop); Mushtaq et al. <https://arxiv.org/abs/2510.24438>;
    Aljaji et al. (NeurIPS 2025 workshop); Aion-BibleQA (Zenodo 2026).
