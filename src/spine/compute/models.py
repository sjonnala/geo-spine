"""Compute entities (ADR-002), Pydantic v2."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from spine.catalog.models import H3_RE, Frozen, Provenance


class Catchment(Frozen):
    catchment_id: str
    origin_h3_r8: str = Field(pattern=H3_RE)
    mode: Literal["auto", "pedestrian", "bicycle"]
    minutes: int = Field(gt=0, le=120)
    member_cells_r8: tuple[str, ...]
    prov: Provenance


class HazardExposure(Frozen):
    h3_r8: str = Field(pattern=H3_RE)
    hazard: Literal["wildfire", "flood", "heat"]
    metric: str
    value: float
    prov: Provenance


class EmbeddingDelta(Frozen):
    h3_r9: str = Field(pattern=H3_RE)
    year_a: int
    year_b: int
    cosine_distance: float = Field(ge=0, le=2)
    dims: Literal[64] = 64
    prov: Provenance

    @model_validator(mode="after")
    def ordered(self) -> EmbeddingDelta:
        if self.year_b <= self.year_a:
            raise ValueError("year_b must be after year_a")
        return self
