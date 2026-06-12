from __future__ import annotations

from pydantic import BaseModel, Field


class IcpIn(BaseModel):
    """An ICP profile — `name`/`tag` are the card header; `data` the opaque form document."""

    name: str = ""
    tag: str = ""
    data: dict = Field(default_factory=dict)


class IcpOut(BaseModel):
    id: str
    name: str
    tag: str
    data: dict
    updated_at: str | None = None
