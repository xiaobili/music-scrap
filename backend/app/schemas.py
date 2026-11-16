from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RootCreate(BaseModel):
    path: str


class RootPatch(BaseModel):
    enabled: bool


class AlbumSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=256)


class SelectCandidateRequest(BaseModel):
    candidate_id: int
    policy: str | None = None


class PlanItemUpdate(BaseModel):
    id: int
    selected: bool | None = None
    new_value: str | None = None


class PlanItemsPatch(BaseModel):
    items: list[PlanItemUpdate] = Field(default_factory=list)


class ApplyPlanRequest(BaseModel):
    cover_url: str | None = None


class CoverSelectRequest(BaseModel):
    url: str
    plan_id: int | None = None


class SettingsUpdate(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class JobCreated(BaseModel):
    job_id: int
    status: str
