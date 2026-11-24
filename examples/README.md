# quotecheck example

`lease.txt` is a short lease written for this example (a fictional document). `answer.md` is an
"AI answer" about it with two exact quotes, one altered quote (24 hours became 48), one invented
quote, and one quote too short to check. From the repository root:

```
quotecheck --source examples/lease.txt --input examples/answer.md
```

Output (exit code 1, because not every quote is exact):

```
4 quotes checked against examples/lease.txt; 1 shorter than 5 words skipped

[1] EXACT  similarity 1.000
    quote, line 3:
      The Landlord shall return the deposit within 30 days after the Tenant has moved out
    source: line 10, characters 378-461

[2] EXACT  similarity 1.000
    quote, line 4:
      a written list of every deduction
    source: line 12, characters 548-581

[3] ALTERED  similarity 0.909  (NUMBERS_DIFFER)
    quote, line 8:
      only after giving the Tenant at least 48 hours' written notice.
    closest in source, line 16, characters 712-774:
      only after giving the Tenant at least 24 hours' written notice

[4] FABRICATED  similarity 0.200
    quote, line 10:
      no guest may stay in the apartment for more than fourteen nights in any calendar year
      without the Landlord's consent.
    closest in source, line 15, characters 647-698:
      but only between nine in the morning and six in the

Result: 2 EXACT, 1 ALTERED, 1 FABRICATED
```

Add `--json` for a machine-readable report. `tests/test_quotecheck.py` checks that the output
above is what the command really prints.
