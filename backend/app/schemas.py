from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class RootCreate(BaseModel):
    path: str


class RootPatch(BaseModel):
    enabled: bool


class AlbumSearchRequest(BaseModel):
    album: str | None = Field(default=None, max_length=256)
    artist: str | None = Field(default=None, max_length=256)
    year_from: int | None = Field(default=None, ge=1900, le=2100)
    year_to: int | None = Field(default=None, ge=1900, le=2100)

    @model_validator(mode="after")
    def _validate_criteria(self) -> "AlbumSearchRequest":
        if self.album is not None:
            self.album = self.album.strip() or None
        if self.artist is not None:
            self.artist = self.artist.strip() or None
        if not any((self.album, self.artist, self.year_from, self.year_to)):
            raise ValueError("至少需要填写一个检索条件")
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("年代起始不能晚于结束")
        return self


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
