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
    icp_suggestions: list[dict] = []
    model: str | None = None
    llm_call_id: str | None = None
    created_at: str | None = None


class ResearchSpecList(BaseModel):
    """The latest spec plus the version history (newest first) for the review panel."""

    latest: ResearchSpecOut | None = None
    versions: list[int] = []


class ScopingPromptOut(BaseModel):
    """The exact LLM prompt that `POST /brief/structure` would send — for operator inspection.

    Built from the same `build_messages(brief, icps)` the live call uses (single source of
    truth), but without making (or billing) the completion. The prompt-preview popup renders it.
    `system` is the effective system prompt (operator override if saved, else the default);
    `system_is_custom` says which. `user` is read-only — it is always the client brief + ICPs.
    """

    system: str
    user: str
    system_is_custom: bool = False
    model: list[str]
    purpose: str
    prompt_version: str


class SystemPromptIn(BaseModel):
    """An operator-edited system prompt for the scoping call, saved per client (versioned)."""

    system: str


class SystemPromptOut(BaseModel):
    """The saved system prompt + its version after a save (or the effective one on read)."""

    system: str
    version: int
    is_custom: bool
