"""B2 unit tests — the completeness rubric (pure logic, no I/O).

Proves the ring math and the churn-proof guarantee: the rubric is data, so adding a key
to the required list re-scores a previously-complete brief with no code change.
"""

from __future__ import annotations

from app.domains.briefs import completeness as C


def _full_brief() -> dict:
    # Every required field filled (strings non-blank, lists non-empty).
    return {
        k: (["x"] if k in ("valueProps", "languages") else "x") for k in C.REQUIRED_BRIEF_FIELDS
    }


def test_empty_brief_scores_zero_and_lists_all_required():
    assert C.completeness({}) == 0
    assert C.missing_fields({}) == list(C.REQUIRED_BRIEF_FIELDS)


def test_full_brief_scores_100_no_missing():
    data = _full_brief()
    assert C.completeness(data) == 100
    assert C.missing_fields(data) == []


def test_optionals_do_not_affect_score():
    data = _full_brief()
    # Optional fields blank → still 100.
    for opt in (
        "objections",
        "competitors",
        "languageOther",
        "doNotContact",
        "compliance",
        "first90",
    ):
        data[opt] = ""
    assert C.completeness(data) == 100


def test_blank_and_whitespace_count_as_unfilled():
    data = _full_brief()
    data["companyName"] = "   "  # whitespace only
    data["valueProps"] = ["", "  "]  # all-blank list
    miss = C.missing_fields(data)
    assert "companyName" in miss and "valueProps" in miss
    assert C.completeness(data) < 100


def test_partial_is_monotonic():
    data: dict = {}
    last = C.completeness(data)
    for k in C.REQUIRED_BRIEF_FIELDS:
        data[k] = ["x"] if k in ("valueProps", "languages") else "x"
        now = C.completeness(data)
        assert now >= last
        last = now
    assert last == 100


def test_rubric_is_data_adding_a_key_lowers_a_full_brief(monkeypatch):
    """The churn-proof property: editing the required list re-scores with no code change."""
    data = _full_brief()
    assert C.completeness(data) == 100
    monkeypatch.setattr(C, "REQUIRED_BRIEF_FIELDS", C.REQUIRED_BRIEF_FIELDS + ("brandNewField",))
    assert C.completeness(data) < 100
    assert "brandNewField" in C.missing_fields(data)
