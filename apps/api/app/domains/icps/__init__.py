"""ICP domain — the per-client persona profiles (CRUD in `router.py`).

`icp_docs` is the ONE construction of an ICP's LLM-facing document: the stored `data` bag plus
`id`/`name`/`tag`. Both halves of the loop read it through this helper so they can never diverge —
B (brief scoping, `briefs/structuring.py` + `briefs/router.py`) feeds the WHOLE ICP set to the
scoping model, and C (fit scoring, `prospects/router.py`) feeds the SAME docs as the rubric's
targeting context (the rubric grades maturity/department/tech/economic-buyer straight off these
fields — see docs/prompts/fit-scoring-rubric-v1.md §2/§3). `icp_id` narrows to one profile when a
find/enrich run is ICP-scoped; omit it for the union of all profiles.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Icp


def icp_docs(
    db: Session, tenant_id: uuid.UUID, icp_id: uuid.UUID | None = None
) -> list[dict]:
    """The tenant's ICP documents (one per profile), oldest first. `icp_id` narrows to one."""
    q = select(Icp).where(Icp.tenant_id == tenant_id)
    if icp_id is not None:
        q = q.where(Icp.id == icp_id)
    return [
        {**i.data, "id": str(i.id), "name": i.name, "tag": i.tag}
        for i in db.execute(q.order_by(Icp.created_at)).scalars()
    ]
