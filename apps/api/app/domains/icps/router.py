"""ICP routes — multi-profile CRUD per client (same thin JSON-document pattern as briefs).

Tenant scope × role is enforced by the A4 central guard; every row carries `tenant_id`, so
list/get/update/delete are always scoped to the caller's client. `icp_limit` is plan-derived
in the spec but unenforced at dogfood volume (tenant #0 runs effectively unlimited).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AccessContext, get_db, require_membership
from app.domains.icps.schemas import IcpIn, IcpOut
from app.models import Icp

router = APIRouter(tags=["icps"])


def _out(icp: Icp) -> IcpOut:
    return IcpOut(
        id=str(icp.id),
        name=icp.name,
        tag=icp.tag,
        data=icp.data,
        updated_at=icp.updated_at.isoformat() if icp.updated_at else None,
    )


def _load(db: Session, tenant_id: uuid.UUID, icp_id: str) -> Icp:
    try:
        pk = uuid.UUID(icp_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such icp") from e
    icp = db.execute(
        select(Icp).where(Icp.id == pk, Icp.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if icp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such icp")
    return icp


@router.get("/{client}/icps", response_model=list[IcpOut])
def list_icps(
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> list[IcpOut]:
    rows = db.execute(
        select(Icp).where(Icp.tenant_id == ctx.tenant.id).order_by(Icp.created_at)
    ).scalars()
    return [_out(i) for i in rows]


@router.post("/{client}/icps", response_model=IcpOut, status_code=status.HTTP_201_CREATED)
def create_icp(
    body: IcpIn,
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> IcpOut:
    icp = Icp(tenant_id=ctx.tenant.id, name=body.name, tag=body.tag, data=body.data)
    db.add(icp)
    db.commit()
    db.refresh(icp)
    return _out(icp)


@router.put("/{client}/icps/{icp_id}", response_model=IcpOut)
def update_icp(
    icp_id: str,
    body: IcpIn,
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> IcpOut:
    icp = _load(db, ctx.tenant.id, icp_id)
    icp.name, icp.tag, icp.data = body.name, body.tag, body.data
    db.commit()
    db.refresh(icp)
    return _out(icp)


@router.delete("/{client}/icps/{icp_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_icp(
    icp_id: str,
    ctx: AccessContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> None:
    icp = _load(db, ctx.tenant.id, icp_id)
    db.delete(icp)
    db.commit()
