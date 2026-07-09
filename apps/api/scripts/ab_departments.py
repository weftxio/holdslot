"""One-time live A/B — does Apollo's `person_department_or_subdepartments` facet actually filter?

D+ Stage 1b verification. The facet is NOT in Apollo's documented API (§initial-build-plan), yet the
research-spec maps every ICP's persona onto it (Management Level × Department). Before trusting it
as a scoping lever we prove it live: run the SAME broad people scope with and without a department,
compare `total_entries`. People search is FREE (0 credits), so this spends nothing — just a handful
of count-only (`per_page=1`) calls.

Read it like this:
  * A real department count that is clearly BELOW the no-department baseline, and DIFFERS across
    departments, means the facet filters → keep using it.
  * Every department returning ~the baseline (and the nonsense control also returning the baseline)
    means Apollo silently ignores the param → it's a no-op; fall back to titles/keywords (Stage 2).
  * The nonsense control returning ~0 is the strongest positive signal (the param is honored).

Run (needs the Apollo key — env or Secrets Manager via the profile):
    AWS_PROFILE=holdslot python scripts/ab_departments.py
    # or, with an explicit key and no AWS:
    HOLDSLOT_APOLLO_KEY=... python scripts/ab_departments.py
"""

from __future__ import annotations

# A broad baseline so the facet has room to bite (no department set). Kept generic on purpose.
BASELINE = {
    "person_seniorities": ["manager", "director", "vp", "head"],
    "organization_locations": ["united states"],
}

# Apollo's master department enums (from research_spec.py) + a nonsense control. If the param is
# honored, the control collapses to ~0; if ignored, it returns the baseline.
DEPARTMENTS = [
    "master_sales",
    "master_marketing",
    "master_information_technology",
    "master_finance",
    "master_engineering_technical",
    "master_operations",
    "__nonsense_control__",
]


def main() -> None:
    from app.integrations.apollo import client as apollo

    print("Apollo departments A/B — count-only (FREE). Baseline (no department):")
    print(f"  {BASELINE}")
    baseline = apollo.count_people(BASELINE)
    print(f"  baseline total_entries = {baseline:,}\n")
    if not baseline:
        print("Baseline is 0 — widen BASELINE and re-run; nothing to compare against.")
        return

    print(f"{'department':32} {'total_entries':>14} {'% of baseline':>14}")
    print("-" * 62)
    results: dict[str, int] = {}
    for dept in DEPARTMENTS:
        body = {**BASELINE, "person_department_or_subdepartments": [dept]}
        try:
            n = apollo.count_people(body)
        except apollo.ApolloError as e:  # a rejected enum is itself a signal the param is parsed
            print(f"{dept:32} {'ERROR':>14}   {e}")
            continue
        results[dept] = n
        print(f"{dept:32} {n:>14,} {(100 * n / baseline):>13.1f}%")

    print("\nVerdict:")
    real = {d: n for d, n in results.items() if d != "__nonsense_control__"}
    control = results.get("__nonsense_control__")
    distinct = len(set(real.values()))
    all_near_baseline = all(abs(n - baseline) <= baseline * 0.02 for n in real.values())
    if control is not None and control <= baseline * 0.02:
        print("  ✅ FILTERS — the nonsense control collapsed to ~0; the facet is honored. Keep it.")
    elif all_near_baseline and (control is None or abs(control - baseline) <= baseline * 0.02):
        print("  ❌ NO-OP — every department (incl. control) ≈ baseline; Apollo ignores the param.")
        print("     Fall back to titles/keywords for the persona (D+ Stage 2).")
    elif distinct > 1 and all(n < baseline for n in real.values()):
        print("  ✅ FILTERS — department counts are below baseline and vary by dept. Keep it.")
    else:
        print("  ⚠ INCONCLUSIVE — mixed signal; inspect the table above and re-run")
        print("     with a different BASELINE (geo/seniority) before deciding.")


if __name__ == "__main__":
    main()
