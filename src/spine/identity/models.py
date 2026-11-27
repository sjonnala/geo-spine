"""Spatial Identity entities (ADR-002), Pydantic v2."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from spine.catalog.models import H3_RE, Frozen, Provenance


class Parcel(Frozen):
    parcel_id: str
    apn: str | None = None
    county_fips: str = Field(pattern=r"^\d{5}$")
    h3_r8: str = Field(pattern=H3_RE)
    geom_wkb_ref: str
    prov: Provenance


class Structure(Frozen):
    structure_id: str
    parcel_id: str | None = None
    h3_r9: str = Field(pattern=H3_RE)
    year_built: int | None = None
    prov: Provenance


class AddressAlias(Frozen):
    alias_id: str
    normalized_address: str
    parcel_id: str | None = None
    match_confidence: float = Field(ge=0, le=1)
    prov: Provenance


class Place(Frozen):
    gers_id: str  # Overture Global Entity Reference System id
    name: str
    category: str
    h3_r8: str = Field(pattern=H3_RE)
    prov: Provenance


class Facility(Frozen):
    facility_id: str
    gers_id: str | None = None
    kind: Literal["childcare_center", "family_childcare_home", "other"]
    licensed_capacity: int | None = Field(default=None, ge=0)
    status: str
    h3_r8: str = Field(pattern=H3_RE)
    location_precision: Literal["rooftop", "street", "zip_centroid", "suppressed"]
    prov: Provenance
