import pytest

from quotebench.validate import _normalise_label, cohen_kappa, describe_units
from quotebench.sources import load_units


def test_kappa():
    assert cohen_kappa(["A", "B", "A", "B"], ["A", "B", "A", "B"]) == 1.0
    assert cohen_kappa(["A", "A", "B", "B"], ["A", "B", "A", "B"]) == pytest.approx(0.0)
    # textbook example: po = 0.7, pe = 0.5 -> kappa 0.4
    a = ["Y"] * 20 + ["Y"] * 5 + ["N"] * 10 + ["N"] * 15
    b = ["Y"] * 20 + ["N"] * 5 + ["Y"] * 10 + ["N"] * 15
    assert cohen_kappa(a, b) == pytest.approx(0.4)


def test_label_aliases():
    assert _normalise_label(" wrong place ") == "WRONG_PLACE"
    assert _normalise_label("exact") == "EXACT"
    assert _normalise_label("trap") == "TRAP_FABRICATED"


def test_describe_units():
    kjv = load_units("bible_kjv")
    idx = [u["idx"] for u in kjv if u["book"] == "John" and u["chapter"] == 3 and u["verse"] in (16, 17)]
    assert describe_units("bible_kjv", idx, kjv) == "John 3:16-17"
    con = load_units("us_constitution")
    assert describe_units("us_constitution", [0], con) == "Preamble"
