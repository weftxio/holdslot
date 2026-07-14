"""U1 — per-ICP scope-override resolution (pure, no DB).

Covers the three helpers the Find precedence rests on: reading one ICP's block out of the per-ICP
map (`_scope_override_block`), merging a save/clear into that map without touching other ICPs
(`_merge_scope_map`), and the empty-payload-is-a-revert check (`_has_scope_value`). The end-to-end
endpoint path is exercised by the Aurora integration suite; this pins the logic that decides which
scope a find uses.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.domains.prospects.router import (
    _has_scope_value,
    _merge_scope_map,
    _scope_override_block,
)

A = "11111111-1111-1111-1111-111111111111"
B = "22222222-2222-2222-2222-222222222222"
PSP = {"people_search_params": {"person_seniorities": ["vp"]}}
PSP_B = {"people_search_params": {"person_seniorities": ["director"]}}


def _row(params):
    return SimpleNamespace(params=params)


# --------------------------------------------------------------- _scope_override_block (read)


def test_block_none_row_is_ai_scope():
    assert _scope_override_block(None, A) is None


def test_block_resolves_per_icp():
    row = _row({"by_icp": {A: PSP, B: PSP_B}})
    assert _scope_override_block(row, A) == PSP
    assert _scope_override_block(row, B) == PSP_B


def test_block_unknown_icp_falls_to_ai():
    row = _row({"by_icp": {A: PSP}})
    assert _scope_override_block(row, B) is None


def test_block_global_entry_is_fallback():
    # An ICP-less ("*") save applies to any ICP that has no per-ICP override of its own...
    row = _row({"by_icp": {"*": PSP}})
    assert _scope_override_block(row, A) == PSP
    assert _scope_override_block(row, B) == PSP


def test_block_per_icp_wins_over_global():
    # ...but a per-ICP override takes precedence for that ICP.
    row = _row({"by_icp": {A: PSP_B, "*": PSP}})
    assert _scope_override_block(row, A) == PSP_B
    assert _scope_override_block(row, B) == PSP


def test_block_legacy_flat_is_ignored():
    # The legacy-flat fallback was removed in Wave 5 (S23) — pre-flight confirmed no live override
    # lacks a `by_icp` map. A payload without `by_icp` now yields None (→ AI scope), not a global.
    row = _row(PSP)
    assert _scope_override_block(row, A) is None
    assert _scope_override_block(row, B) is None


# --------------------------------------------------------------- _merge_scope_map (write)


def test_merge_first_save():
    assert _merge_scope_map(None, A, PSP) == {"by_icp": {A: PSP}}


def test_merge_second_icp_leaves_first_untouched():
    # Saving ICP-B's personas must not clobber ICP-A's saved override (the core U1 fix).
    existing = {"by_icp": {A: PSP}}
    assert _merge_scope_map(existing, B, PSP_B) == {"by_icp": {A: PSP, B: PSP_B}}


def test_merge_clear_one_icp_keeps_others():
    existing = {"by_icp": {A: PSP, B: PSP_B}}
    assert _merge_scope_map(existing, A, None) == {"by_icp": {B: PSP_B}}


def test_merge_clear_last_icp_deletes_row():
    assert _merge_scope_map({"by_icp": {A: PSP}}, A, None) is None


def test_merge_discards_legacy_flat_on_first_per_icp_write():
    assert _merge_scope_map(PSP, A, PSP_B) == {"by_icp": {A: PSP_B}}


# --------------------------------------------------------------- _has_scope_value (empty = revert)


def test_empty_people_block_is_revert():
    assert not _has_scope_value(
        {
            "people_search_params": {
                "person_seniorities": [],
                "person_department_or_subdepartments": [],
            }
        }
    )


def test_nonempty_people_block():
    assert _has_scope_value({"people_search_params": {"person_seniorities": ["vp"]}})


def test_empty_company_block_is_revert():
    assert not _has_scope_value(
        {
            "company_search_params": {
                "q_organization_keyword_tags": [],
                "organization_locations": [],
                "revenue_range": {"min": None, "max": None},
            },
            "intent_filters": {"company": {"q_organization_job_titles": []}},
        }
    )


def test_nonempty_company_block():
    assert _has_scope_value(
        {"company_search_params": {"organization_locations": ["United States"]}}
    )
