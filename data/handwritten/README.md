# Hand-written inputs (Maksim edits these)

The build script (`quotebench questions`) reads these CSVs and merges them into
`data/questions.jsonl`. Edit them in any spreadsheet app; keep the header row.
Rows whose `text_id` starts with `#` are ignored (use that to keep notes).

## famous.csv — famous passages (SPEC §5, fame stratification)

One row per passage you consider famous. Target: ~50 for `bible_kjv`, ~15 for each other text.

| column | meaning |
|---|---|
| `text_id` | `bible_kjv`, `shakespeare`, `us_constitution`, `pride_prejudice`, `origin_species` |
| `task` | `reference` (Task 1: Bible and Constitution only) or `continuation` (Task 2: the passage is the line you are given) |
| `play` | Shakespeare only |
| `passage` | Bible: a reference like `John 3:16`. Constitution: `Preamble`, `Article I, Section 8, Clause 1`, `Amendment 1` or `Amendment 14, Section 1`. Shakespeare / Austen / Darwin: the opening words of the line or sentence, exactly as you remember them (the script finds it in the source and tells you if it's missing or ambiguous). |
| `note` | optional: why it's famous |

## themes.csv — topic questions (SPEC §4, Task 3)

One row per theme: `text_id`, `play` (Shakespeare only), `theme`. Target: 30 per text.

## traps.csv — trap questions (SPEC §4, Task 4)

Questions where the right answer is "this doesn't exist". Target: ~100 across the five texts.
The script checks every misattribution against the source and rejects any that actually match.

| column | meaning |
|---|---|
| `text_id` | as above |
| `play` | Shakespeare only: which play the trap names |
| `trap_type` | `nonexistent_reference` (a book/chapter/verse/act/scene/article/amendment that isn't there), `misattribution` (a saying people wrongly believe is in this text) or `absent_topic` (a topic the text never covers) |
| `content` | the fake reference (e.g. a chapter number past the end) or the misattributed saying |
| `note` | optional: where the saying really comes from / why it's a trap |
| `hand_checked` | filled in after a person checked a trap the script could not verify (a near miss, or a reference/topic it cannot parse); starts with `yes:` and gives the reason |

Format examples (placeholders — write your own):

```
text_id,trap_type,content,note
bible_kjv,nonexistent_reference,Hezekiah 3:5,no book of Hezekiah
bible_kjv,misattribution,<a saying people think is in the Bible>,<where it is really from>
```
