from __future__ import annotations

from pydantic import BaseModel, Field


class BriefIn(BaseModel):
    """The brief form document — an opaque key→value bag (churn-proof; no per-field schema)."""

    data: dict = Field(default_factory=dict)


class BriefOut(BaseModel):
    """The stored brief plus the server-computed completeness (single source of truth)."""

    data: dict
    completeness: int
    missing: list[str]
    updated_at: str | None = None


class ResearchSpecOut(BaseModel):
    """A persisted ResearchSpec version, traceable to the LLM call that produced it."""

    version: int
    spec: dict
    gaps: list[dict]
    model: str | None = None
    llm_call_id: str | None = None
    created_at: str | None = None


class ResearchSpecList(BaseModel):
    """The latest spec plus the version history (newest first) for the review panel."""

    latest: ResearchSpecOut | None = None
    versions: list[int] = []
