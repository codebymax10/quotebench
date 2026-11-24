"""quotecheck: check the quotations in a text (for example an AI answer) against a source.

    from quotecheck import Source, check

    source = Source.from_text(open("contract.txt").read(), language="en")
    report = check(ai_output_text, source)
    for q in report.quotes:
        print(q.text, q.label, q.similarity, q.best_match, q.source_start, q.source_end)

Labels (D15: only EXACT is a correct quotation):

    EXACT       every word is in the source, in this order (capitals, punctuation, quotation
                marks, dashes, line breaks and ё/е do not matter; numbers do)
    MINOR       not exact: only spelling differs (honour/honor), similarity >= upper (0.97)
    ALTERED     not exact: a real passage with words changed, added or dropped (>= lower, 0.80)
    FABRICATED  nothing similar enough in the source (below lower)

The similarity is 1 only for EXACT. An EXACT quote with flags needs reading: see README.md.

What it does not do: it does not check paraphrases, or quotations from texts it was not given;
it does not say whether a quotation is used fairly or attributed correctly. The split between
MINOR, ALTERED and FABRICATED is approximate and was not checked against human labels.
See README.md in this package.
"""

from .core import LABELS, QuotePart, QuoteResult, Report, Source, check
from .extract import ExtractedQuote, extract_quotes

__version__ = "1.0.0"
__all__ = ["LABELS", "ExtractedQuote", "QuotePart", "QuoteResult", "Report", "Source", "check", "extract_quotes"]
