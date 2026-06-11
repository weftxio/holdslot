from __future__ import annotations

import re

from pydantic import BaseModel, field_validator


class ClientOut(BaseModel):
    slug: str
    name: str
    role: str


class MeOut(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    clients: list[ClientOut]


class ClientCreateIn(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name is required")
        return v


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "client"
