"""tech_vocab — the Apollo technology → UID resolver (D+ Stage 4, vocabulary grounding).

Apollo's two tech filters (`currently_using_any_of_technology_uids` /
`currently_not_using_any_of_technology_uids`) take **UIDs**, not display names — a raw name like
".NET" or "Salesforce" is silently ignored. The canonical vocabulary lives at Apollo's
`auth/supported_technologies_csv` endpoint; this module is the PURE half that parses that CSV and
fuzzy-matches free-text tech names (operator-entered ICP `technologies`, or names harvested from
enrich `technology_names`) to their UIDs. No I/O — the CSV text is fetched by the transport layer
(`integrations/apollo/client.supported_technologies_csv`) and passed in, so every rule is
unit-tested against a fixture.

Match outcomes are deliberately three-valued so we never guess a UID:
  * **hit**       — the name resolves to exactly one UID (exact-normalized, or unique token match).
  * **ambiguous** — the name matches ≥2 distinct UIDs (e.g. "crm") → dropped, not guessed.
  * **miss**      — no vocabulary entry matches → dropped (and surfaced for telemetry).

CSV shape is defensive: a UID-bearing column (any header containing "uid") is authoritative; a
name-only CSV falls back to a slug derived from the display name (the observed Apollo convention —
lowercase, leading dots stripped, non-alphanumerics → single underscore). The slug is best-effort;
the live-dev smoke step confirms the real column layout before this ships.
"""

from __future__ import annotations

import csv
import io
import re
from typing import NamedTuple

# Collapse any run of characters that are not [a-z0-9] into a single underscore, after lowercasing
# and dropping leading dots (".NET" → "net", "24-7 Media" → "24_7_media"). Best-effort UID slug for
# a name-only CSV; a UID column in the CSV always wins over this.
_SLUG_SPLIT = re.compile(r"[^a-z0-9]+")
_WS = re.compile(r"\s+")


class Vocab(NamedTuple):
    """Parsed technology vocabulary. `by_norm` = normalized-name → UID (exact index); `entries`
    carries each row's normalized name + token set for the fuzzy fallback."""

    by_norm: dict[str, str]
    entries: tuple[tuple[str, str, frozenset[str]], ...]  # (norm_name, uid, tokens)


class TechResolution(NamedTuple):
    """The outcome of resolving a batch of tech names. `uids` is the ordered, de-duped hit list to
    hand Apollo; `hits`/`ambiguous`/`misses` are for telemetry + tests."""

    uids: list[str]
    hits: dict[str, str]  # input name → resolved UID
    ambiguous: list[str]  # input names matching ≥2 distinct UIDs (not guessed)
    misses: list[str]  # input names with no vocabulary match


def _norm(s: str) -> str:
    """Lowercase, strip, collapse whitespace, drop leading dots — the exact-match key."""
    return _WS.sub(" ", (s or "").strip().lower()).lstrip(".").strip()


def _tokens(norm: str) -> frozenset[str]:
    """Whitespace-split tokens of a normalized name — the fuzzy membership set."""
    return frozenset(t for t in norm.split(" ") if t)


def _slug(name: str) -> str:
    """Derive a best-effort Apollo UID from a display name (name-only CSV fallback)."""
    base = (name or "").strip().lower().lstrip(".")
    return _SLUG_SPLIT.sub("_", base).strip("_")


def _uid_col(header: list[str]) -> int | None:
    """Index of the first header cell that names a UID column, or None (name-only CSV)."""
    for i, h in enumerate(header):
        if "uid" in (h or "").strip().lower():
            return i
    return None


def parse_vocab(csv_text: str) -> Vocab:
    """Parse an `auth/supported_technologies_csv` body → a `Vocab`. Tolerant of a UID column (any
    header containing "uid" is authoritative) or a name-only CSV (UID slugged from the name). Blank
    lines and rows with no name are skipped; the first non-empty column is the display name."""
    reader = csv.reader(io.StringIO(csv_text or ""))
    rows = [r for r in reader if any((c or "").strip() for c in r)]
    if not rows:
        return Vocab({}, ())
    header = [c.strip() for c in rows[0]]
    uid_idx = _uid_col(header)
    # Treat row 0 as a header only when it actually looks like one (a "uid"/"name" column); a
    # header-less CSV keeps row 0 as data.
    has_header = uid_idx is not None or any(
        h.lower() in ("name", "technology", "cleaned_name", "display_name") for h in header
    )
    body = rows[1:] if has_header else rows

    by_norm: dict[str, str] = {}
    entries: list[tuple[str, str, frozenset[str]]] = []
    for row in body:
        name = next((c.strip() for c in row if (c or "").strip()), "")
        if not name:
            continue
        uid = ""
        if uid_idx is not None and uid_idx < len(row):
            uid = (row[uid_idx] or "").strip()
        uid = uid or _slug(name)
        if not uid:
            continue
        norm = _norm(name)
        if not norm:
            continue
        by_norm.setdefault(norm, uid)
        entries.append((norm, uid, _tokens(norm)))
    return Vocab(by_norm, tuple(entries))


def resolve(names: list[str], vocab: Vocab) -> TechResolution:
    """Resolve free-text tech names to Apollo UIDs against `vocab`, three-valued (see module doc).

    Exact-normalized match wins. Otherwise the name is a single token that must appear in exactly
    one distinct UID's token set to be a fuzzy hit; a token common to ≥2 UIDs is ambiguous (dropped,
    never guessed). Order-preserving + de-duped so the emitted UID list is stable."""
    uids: list[str] = []
    seen_uid: set[str] = set()
    hits: dict[str, str] = {}
    ambiguous: list[str] = []
    misses: list[str] = []
    for raw in names:
        norm = _norm(raw)
        if not norm:
            continue
        uid = vocab.by_norm.get(norm)
        if uid is None:
            # Fuzzy: the input (single token) must be a token of exactly one distinct UID.
            matched = {u for _n, u, toks in vocab.entries if norm in toks}
            if len(matched) == 1:
                uid = next(iter(matched))
            elif len(matched) >= 2:
                ambiguous.append(raw)
                continue
            else:
                misses.append(raw)
                continue
        hits[raw] = uid
        if uid not in seen_uid:
            seen_uid.add(uid)
            uids.append(uid)
    return TechResolution(uids=uids, hits=hits, ambiguous=ambiguous, misses=misses)
