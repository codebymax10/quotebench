"""The ``quotecheck`` command line.

Exit code: 0 every checked quote is EXACT (or there was nothing to check), 1 at least one is not,
2 usage error (bad option, unreadable or empty source, unreadable input), 141 the program that
reads the output closed it early (``quotecheck ... | head``): no verdict.

Positions in the report refer to the decoded files as they are: a byte order mark is not counted,
line ends are not translated.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import unicodedata
from pathlib import Path

from . import __version__
from .core import Report, Source, _floor, _line_of, check

BROKEN_PIPE = 141  # what the shell reports for a program ended by SIGPIPE (128 + 13)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="quotecheck",
        description="Check the quotations in a text word for word against a source.",
        epilog="Exit code: 0 all checked quotes exact, 1 some are not, 2 usage error.",
    )
    p.add_argument("--source", required=True, metavar="FILE", help="text file the quotes should come from (UTF-8)")
    p.add_argument("--input", required=True, metavar="FILE", help='text to check (UTF-8); "-" reads standard input')
    p.add_argument("--json", action="store_true", help="print a JSON report")
    p.add_argument("--min-words", type=int, default=5, metavar="N", help="skip quotes with fewer words (default 5)")
    p.add_argument("--language", default="en", metavar="CODE", help="language of the source, e.g. en or ru (default en)")
    p.add_argument("--upper", type=float, metavar="X", help="similarity from which spelling-only differences are MINOR (default 0.97)")
    p.add_argument("--lower", type=float, metavar="X", help="similarity below which a quote is FABRICATED (default 0.80)")
    p.add_argument("--ignore-numbers", action="store_true", help="do not compare digits (texts with verse, page or footnote numbers)")
    p.add_argument("--version", action="version", version=f"quotecheck {__version__}")
    return p


def _read(name: str, what: str) -> str:
    try:
        data = sys.stdin.buffer.read() if name == "-" else Path(name).read_bytes()
        return data.decode("utf-8-sig")
    except OSError as e:
        raise ValueError(f"cannot read {what} {name}: {e.strerror or e}") from None
    except UnicodeDecodeError:
        raise ValueError(f"{what} {name} is not UTF-8 text") from None


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")  # a terminal that cannot print «ё»
    try:
        try:
            return _run(argv)
        finally:
            sys.stdout.flush()
    except BrokenPipeError:
        # Nobody reads any more: end quietly, also when Python flushes the streams at exit.
        devnull = os.open(os.devnull, os.O_WRONLY)
        for stream in (sys.stdout, sys.stderr):
            try:
                os.dup2(devnull, stream.fileno())
            except (OSError, ValueError):  # not a real file
                pass
        os.close(devnull)
        return BROKEN_PIPE


def _run(argv: list[str] | None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.source == "-":
            raise ValueError('--source must be a file ("-" works for --input only)')
        source = Source.from_text(_read(args.source, "source"), language=args.language)
        text = _read(args.input, "input")
        if not any(c.isalnum() for c in source.text):
            raise ValueError(f"source {args.source} contains no words")
        report = check(text, source, min_words=args.min_words, upper=args.upper, lower=args.lower,
                       compare_numbers=not args.ignore_numbers)
    except ValueError as e:
        print(f"quotecheck: error: {e}", file=sys.stderr)
        return 2
    if args.json:
        out = {"source": args.source, "input": args.input, **report.to_dict()}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(render(report, source, text, args.source))
    return 0 if report.all_exact else 1


def render(report: Report, source: Source, text: str, source_name: str) -> str:
    lines = [f"{_n(len(report.quotes), 'quote')} checked against {source_name}"]
    if report.skipped:
        lines[0] += f"; {len(report.skipped)} shorter than {report.min_words} words skipped"
    for i, q in enumerate(report.quotes, 1):
        flags = f"  ({', '.join(q.flags)})" if q.flags else ""
        lines += ["", f"[{i}] {q.label}  similarity {_show(q.similarity)}{flags}"]
        lines += _field(f"quote, line {_line_of(text, q.start)}", q.text)
        if q.label != "EXACT" and len(q.parts) > 1:
            for p in q.parts:
                lines += _field(f"part {p.label} {_show(p.similarity)}", p.text)
        if q.source_start is None:
            lines += ["    source: no similar passage"]
        else:
            where = f"line {source.line_of(q.source_start)}, characters {q.source_start}-{q.source_end}"
            if q.label == "EXACT":
                lines += [f"    source: {where}"]
            else:
                lines += _field(f"closest in source, {where}", q.best_match)
    for w in report.warnings:
        lines += ["", f"warning: {w}"]
    counts = ", ".join(f"{n} {label}" for label, n in report.counts.items() if n)
    lines += ["", f"Result: {counts or 'no quotes to check'}"]
    return "\n".join(lines)


def _show(x: float) -> str:
    return f"{int(_floor(x) * 1000 + 1e-9) / 1000:.3f}"


def _n(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _field(name: str, value: str, limit: int = 600) -> list[str]:
    # Control characters could drive the terminal; show them as spaces.
    value = "".join(" " if unicodedata.category(c)[0] == "C" else c for c in value)
    value = " ".join(value.split())
    if len(value) > limit:
        value = value[: limit - 2].rstrip() + " …"
    return [f"    {name}:", *textwrap.wrap(value, 92, initial_indent="      ", subsequent_indent="      ")]


if __name__ == "__main__":
    sys.exit(main())
