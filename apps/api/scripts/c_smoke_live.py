"""C live smoke — drive the DEPLOYED API through find→select→find→enrich for ~1 row.

Sets up an ephemeral tenant + owner + ResearchSpec directly in dev Aurora, logs in against the
deployed API Gateway, runs the four real endpoints (real Apollo + real LLM; ~1 enrich credit), then
tears the tenant down. Run: AWS_PROFILE=holdslot python scripts/c_smoke_live.py
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("API_BASE", "https://ooqe40p813.execute-api.us-east-1.amazonaws.com")
PW = "tryholdslot1!"


def call(method: str, path: str, token: str | None = None, body: dict | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def main() -> None:
    from app.core.db import get_session
    from app.core.security import hash_password
    from app.models import AppUser, Membership, MembershipRole, ResearchSpec, Tenant

    db = get_session()
    suffix = uuid.uuid4().hex[:8]
    slug, email = f"csmoke-{suffix}", f"csmoke-{suffix}@example.com"
    tenant = Tenant(slug=slug, name=f"C Smoke {suffix}")
    db.add(tenant)
    db.flush()
    user = AppUser(email=email, password_hash=hash_password(PW), full_name="Smoke")
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, tenant_id=tenant.id, role=MembershipRole.owner))
    db.add(
        ResearchSpec(
            tenant_id=tenant.id,
            version=1,
            spec={
                "spec_version": 3,
                "company_search_params": {
                    "q_organization_keyword_tags": ["saas", "b2b software"],
                    "organization_num_employees_ranges": ["201,1000"],
                    "organization_locations": ["united states"],
                    "revenue_range": {"min": None, "max": None},
                },
                "people_search_params": {
                    "person_titles": [
                        "Account Executive",
                        "Sales Manager",
                        "Head of Sales",
                        "VP Sales",
                    ],
                    "include_similar_titles": True,
                    "q_keywords": "saas",
                    "person_seniorities": ["manager", "director", "vp", "head"],
                    "organization_locations": ["united states"],
                    "organization_num_employees_ranges": ["201,1000"],
                },
                "intent_filters": {},
                "credit_policy": {"max_companies": 500},
            },
        )
    )
    db.commit()
    print(f"[setup] tenant={slug} user={email}")

    try:
        s, r = call("POST", "/auth/login", body={"email": email, "password": PW})
        assert s == 200, f"login {s}: {r}"
        token = r["access_token"]
        print("[1/5] login OK")

        s, r = call("POST", f"/{slug}/companies/find-company", token, {"limit": 8})
        print(f"[2/5] find-company -> {s} found={r.get('found') if isinstance(r, dict) else r}")
        assert s == 200 and r["found"] >= 1, r
        comp_ids = [c["id"] for c in r["companies"]]
        print("        sample:", [(c["domain"], c["fit_score"]) for c in r["companies"][:3]])

        s, r = call(
            "PATCH", f"/{slug}/companies/select", token, {"ids": comp_ids, "selected": True}
        )
        assert s == 200, r
        print(f"[3/5] selected {len(comp_ids)} companies")

        s, r = call("POST", f"/{slug}/people/find-people", token, {"per_company": 3})
        print(f"[4/5] find-people -> {s} found={r.get('found') if isinstance(r, dict) else r}")
        assert s == 200, r
        people = r.get("prospects", [])
        if not people:
            print("        (no people returned for these orgs — enrich step skipped)")
            return
        key = people[0]["identity_key"]
        print("        sample:", [(p["full_name"], p["title"], p["company"]) for p in people[:3]])

        s, r = call("POST", f"/{slug}/prospects/enrich", token, {"identity_keys": [key]})
        print(f"[5/5] enrich -> {s} {r}")
        assert s == 200, r
        s, r = call("GET", f"/{slug}/prospects", token)
        enriched = next((p for p in r if p["identity_key"] == key), None)
        fields = ("full_name", "email", "email_valid", "status")
        print("        enriched row:", {k: enriched.get(k) for k in fields} if enriched else None)
        print("✅ live end-to-end smoke complete")
    finally:
        db.delete(user)
        db.delete(tenant)
        db.commit()
        db.close()
        print(f"[teardown] removed {slug}")


if __name__ == "__main__":
    main()
