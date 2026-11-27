"""Surface entities (ADR-002), Pydantic v2."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from spine.catalog.models import Frozen, LicenseClass


class Tileset(Frozen):
    product: str
    build_id: str
    path: str = Field(pattern=r"^tiles/[a-z0-9_-]+/[A-Za-z0-9_.-]+\.pmtiles$")
    releases: tuple[str, ...]
    license_classes: tuple[LicenseClass, ...]


class Memo(Frozen):
    memo_id: str
    subject_id: str
    body_md: str
    cited_releases: tuple[str, ...]
    grounding_passed: bool
    model_id: str
    generated_at: datetime


class ApiResource(Frozen):
    path: str
    method: Literal["GET"] = "GET"
    response_schema: str
    releases: tuple[str, ...]
