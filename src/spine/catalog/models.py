"""Source Catalog entities (ADR-001 / ADR-002), Pydantic v2."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

H3_RE = r"^8[0-9a-f]{14}$"  # H3 v4 cell index as a 15-hex-char string (mode 1)
RELEASE_ID_RE = r"^[a-z0-9_]+_\d{4}(-\d{2}){0,2}[a-z0-9_.-]*$"


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LicenseClass(StrEnum):
    PUBLIC_DOMAIN = "public_domain"
    PERMISSIVE = "permissive"  # CC0, CC-BY, CDLA-Permissive-2.0, Apache-2.0
    SHARE_ALIKE = "share_alike"  # ODbL
    NON_COMMERCIAL = "non_commercial"  # any NC licence, incl. Carbon Mapper's custom terms
    RESTRICTED = "restricted"  # e.g. CHHS terms: commercial use needs approval


class DatasetRelease(Frozen):
    """One pinned input. `status=pending_download` is a seed row from the G-101 catalog whose
    dated file URL and sha256 are filled on first download; it can never feed a published build."""

    release_id: str = Field(pattern=RELEASE_ID_RE)
    source_id: str
    vintage: str  # e.g. "2023" (ACS 5-yr end year) or "2026-11-20"
    url: str
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    license_spdx: str  # "ODbL-1.0", "CC-BY-4.0", "LicenseRef-..." for custom terms
    license_class: LicenseClass
    commercial_ok: bool
    retrieved_at: datetime | None = None
    status: Literal["pinned", "pending_download"] = "pinned"
    notes: str | None = None

    @field_validator("release_id", "vintage", "url")
    @classmethod
    def no_latest(cls, v: str) -> str:
        if "latest" in v.lower():
            raise ValueError("unpinned 'latest' reference is forbidden (ADR-001)")
        return v

    @model_validator(mode="after")
    def pinned_needs_checksum(self) -> DatasetRelease:
        if self.status == "pinned" and (self.sha256 is None or self.retrieved_at is None):
            raise ValueError("a pinned release needs sha256 and retrieved_at (ADR-001)")
        return self


class Provenance(Frozen):
    """Row-level provenance columns carried on every curated/feature table (ADR-001 #4)."""

    release_id: str
    method_ver: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    build_id: str
    license_class: LicenseClass
