# Russian sources — research notes for a later version (2026-10-11)

Russian was dropped from v1 (DECISIONS.md D5). These are the candidate sources found, for when
it is added. Not yet verified by hand in the main session.

## Bible, Synodal
- **Recommended:** scrollmapper `RusSynodal` (conversion of CrossWire RusSynodal module v1.9.1,
  marked public domain). Pin commit `e1b254cef86d0e65b1a5d1a94b8b112d0f296a2c`.
  JSON: https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/RusSynodal.json
  77 books incl. deuterocanon, Psalm 151; Synodal order; keeps the Synodal square brackets.
- **Cross-check:** eBible `https://ebible.org/Scriptures/russyn_vpl.zip` (66 books, native Synodal
  versification, but drops some bracketed passages, modernises spellings, has typos; 816 verses
  differ from scrollmapper after normalisation).
- **Versification vs KJV:** Psalms follow Greek numbering (Syn 9 = KJV 9–10; Syn 10–112 = KJV
  11–113; Syn 113 = KJV 114–115; Syn 114–115 = KJV 116; Syn 116–145 = KJV 117–146; Syn 146–147 =
  KJV 147) and titles count as verse 1. Also Rom 16:25–27 = Syn 14:24–26; 3 John has 15 verses;
  2 Cor 13:12–14 = Syn 13:12–13; Song 6:13 = Syn 7:1; smaller shifts in Lev 14, Num 12/13, 29/30,
  Josh 5/6/24, 1 Sam 20, 23/24, Job 39–41, Prov 4, 13, Eccl 4:17, Dan 3, Hos 14, Jon 2, Acts 19:40.
- **Risks:** Psalm titles unreliable in all sources (exclude title verses); a few leftover
  `<note>`/`<title>` tags (Job 2:9, Job 9:9, Ps 143:15); ASCII dashes/quotes; ё almost never used.

## Eugene Onegin
- **Recommended:** rvb.ru, 10-vol. Collected Works (ГИХЛ 1959–62) vol. 4, final 1837 text.
  https://rvb.ru/pushkin/01text/04onegin/01onegin/0836-full.htm (per chapter `0836-01.htm`…`-08.htm`;
  `-09` notes, `-10` journey fragments, `-11` Chapter X). windows-1251.
  Lines carry ids `L<chapter>_<stanza>_<line>`; omitted stanzas are dotted placeholders.
  Strip `<sup>` note links, `div.footnote`, `div.page`.
- **Alternative:** Wikisource ПСС 1977 (СО), per-chapter `?action=raw`; omitted stanzas carry
  draft text in `<ref group="~">`, inconsistent ё.

## Crime and Punishment
- **Recommended:** rvb.ru, 15-vol. Collected Works (Наука 1989) vol. 5.
  `https://rvb.ru/dostoevski/01text/vol5/27-01.htm` … `27-41.htm`; Part I = 01–07, II = 08–14,
  III = 15–20, IV = 21–26, V = 27–31, VI = 32–39, Epilogue = 40–41 (TOC mislinks Part V ch. IV;
  real page is 27-30). windows-1251. Rejoin paragraphs split by `div.page` + `p.text-continuation`.
- **Alternative:** Wikisource per-chapter pages (from lib.ru; typographic spaces, small errors).

## Normalisation needs
Fold Unicode spaces, dashes, quote styles; ё→е; remove U+0301 stress and U+00AD soft hyphen;
strip `[ ]` brackets.
