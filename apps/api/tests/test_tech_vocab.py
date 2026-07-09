"""D+ Stage 4 — the pure tech→UID resolver (`prospects/tech_vocab`).

Runs against a fixture CSV in the `auth/supported_technologies_csv` shape (name,uid,category), so
parse + fuzzy-match are verified without a network call. The three-valued outcome (hit / ambiguous /
miss) is the guard that we never hand Apollo a guessed UID.
"""

from __future__ import annotations

from pathlib import Path

from app.domains.prospects import tech_vocab

_FIX = Path(__file__).resolve().parent / "fixtures" / "apollo"
_CSV = (_FIX / "supported_technologies.csv").read_text()


def _vocab() -> tech_vocab.Vocab:
    return tech_vocab.parse_vocab(_CSV)


def test_parse_skips_header_and_indexes_by_normalized_name():
    v = _vocab()
    # Header row ("cleaned_name,uid,category") is not an entry.
    assert "cleaned_name" not in v.by_norm
    assert v.by_norm["salesforce"] == "salesforce"
    assert v.by_norm["hubspot crm"] == "hubspot_crm"
    # ".NET" normalizes with the leading dot stripped.
    assert v.by_norm["net"] == "net"


def test_resolve_exact_hit_is_case_and_dot_insensitive():
    v = _vocab()
    r = tech_vocab.resolve(["Salesforce", "MARKETO", ".net"], v)
    assert r.uids == ["salesforce", "marketo", "net"]
    assert r.hits == {"Salesforce": "salesforce", "MARKETO": "marketo", ".net": "net"}
    assert not r.ambiguous and not r.misses


def test_resolve_fuzzy_token_hit_when_unique():
    v = _vocab()
    # "commerce" is a token only of "Salesforce Commerce Cloud" → one distinct UID → fuzzy hit.
    r = tech_vocab.resolve(["commerce"], v)
    assert r.uids == ["salesforce_commerce_cloud"]
    assert r.hits == {"commerce": "salesforce_commerce_cloud"}


def test_resolve_ambiguous_token_is_dropped_not_guessed():
    v = _vocab()
    # "analytics" tokenizes into both Google Analytics + Adobe Analytics → ≥2 UIDs → ambiguous.
    r = tech_vocab.resolve(["analytics"], v)
    assert r.uids == []
    assert r.ambiguous == ["analytics"]
    assert not r.hits


def test_resolve_miss_is_surfaced():
    v = _vocab()
    r = tech_vocab.resolve(["totally-made-up-tech-9000"], v)
    assert r.uids == [] and r.misses == ["totally-made-up-tech-9000"]


def test_resolve_dedupes_uids_and_ignores_blanks():
    v = _vocab()
    r = tech_vocab.resolve(["Salesforce", "salesforce", "", "  "], v)
    assert r.uids == ["salesforce"]  # de-duped, blanks skipped


def test_parse_name_only_csv_slugs_the_uid():
    # A name-only CSV (no uid column) derives a best-effort slug.
    v = tech_vocab.parse_vocab("name\nApache Kafka\n.GIS\n")
    assert v.by_norm["apache kafka"] == "apache_kafka"
    assert v.by_norm["gis"] == "gis"


def test_parse_empty_csv_is_safe():
    assert tech_vocab.parse_vocab("").by_norm == {}
    assert tech_vocab.resolve(["x"], tech_vocab.parse_vocab("")).misses == ["x"]
