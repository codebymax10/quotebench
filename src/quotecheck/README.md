# quotecheck

Finds the quotations in a text (for example an AI answer) and checks each one, word for word,
against a source you supply. No network, no model calls. It uses the scoring code of QuoteBench
(`quotebench.scoring`) with the same frozen settings.

```python
from quotecheck import Source, check

source = Source.from_file("contract.txt", language="en")   # or Source.from_text(text)
report = check(ai_output_text, source, min_words=5)
for q in report.quotes:
    print(q.label, q.similarity, q.text, q.best_match, q.source_start, q.source_end)
```

```
quotecheck --source contract.txt --input answer.txt     # "-" reads standard input; --json; --help
```

Exit code: 0 every checked quote is exact (also if there was nothing to check), 1 at least one is
not, 2 usage error (bad option, unreadable or empty source).

## Labels

Only `EXACT` is a correct quotation (DECISIONS.md, D15). It does not depend on any threshold.

| Label | Meaning |
|---|---|
| `EXACT` | Every word is in the source, in this order. Capitals, punctuation, quotation marks, dashes, line breaks and ё/е do not matter; numbers do. |
| `MINOR` | Not exact: only spelling differs (honour/honor), similarity >= 0.97. English only. |
| `ALTERED` | Not exact: a passage of the source with words changed, added or dropped, similarity >= 0.80. |
| `FABRICATED` | Nothing similar enough in the source (below 0.80). A heavily reworded real passage, or a quote of another document, also lands here. |

There is no requested passage, so the benchmark's `WRONG_PLACE`, `PARTIAL` and similar do not apply.

Flags: `ELLIPSIS`, `BRACKETS` (exact, apart from words the quote itself marks as left out or
[inserted]); `NUMBERS_DIFFER` (only numbers are wrong); `OUT_OF_ORDER`, `FAR_APART`,
`TOO_FRAGMENTED` (problems with the pieces around an ellipsis or bracket); `UNCLOSED` (no closing
mark; checked to the end of the paragraph); `ATTRIBUTION_IGNORED` (a last line "— Author" of a
block quote was not checked); `SHORT_QUOTE` (under 6 words, from the benchmark).

## Rules

- **Found:** "..." “...” „...“ «...» »...« '...' ‘...’ and Markdown block quotes. Only the
  outermost marks count. Quotes under `min_words` are not checked, only counted (`report.skipped`).
- **Positions:** `source.text[q.source_start:q.source_end] == q.best_match`, unless the quote was
  checked in parts (`q.parts`, each with its own position). `q.start:q.end` is the place in the
  checked text. If a passage occurs several times, the first one is given.
- **Ellipsis:** each part must be verbatim and in order. Parts under 5 words must lie within 50
  words of their neighbour.
- **Brackets:** a [bracketed] insertion may stand for up to 6 source words; `[T]he` is "The";
  `[12]` and `[sic]` are dropped.
- **Numbers:** compared by default, unlike in the benchmark, which drops digits because they are
  verse numbers there. `compare_numbers=False` / `--ignore-numbers` gives the benchmark's behaviour,
  for texts with verse, page or footnote numbers.

## What it does not do

- It does not check paraphrases, summaries or claims, only text marked as a quotation.
- It knows only the source you give it. A true quotation from another text is `FABRICATED` here.
- It does not judge whether a quote is fair, in context, or attributed to the right person. With an
  ellipsis or brackets a quote can be `EXACT` and still misleading ("shall ... pay"): read the flags.
- The split between `MINOR`, `ALTERED` and `FABRICATED` (similarity 0.97 and 0.80) is approximate
  and was not checked against human labels.
- Symbols are not words: "$500" and "€500", "5%" and "5", "-5" and "5" count as the same. Spacing
  and hyphenation do count ("30-day" is not "30 day").
- Not found: indented or HTML block quotes, `&quot;`, ``` ``LaTeX'' ```, ″primes″, 「CJK」 marks,
  italics used as quotation, and the lines of a block quote that lack the ">". Single quotes and
  apostrophes are told apart by rules of thumb. A quote split by "he said" is two quotes.
- Decode JSON answers before checking them (an escaped `\n` would glue words together).
- Languages written without spaces (Chinese, Japanese, Thai) are not supported.
