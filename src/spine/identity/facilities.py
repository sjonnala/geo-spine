"""Curate raw CDSS-style facility rows into the `curated.facility` contract (ADR-002).

The raw CDSS file carries a licensee name. It is dropped here and never reaches a curated,
feature or published table (ADR-005 P1; tools/ci/license_guard.py fails any column like it).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import h3

from spine.catalog.models import LicenseClass, Provenance
from spine.identity.models import Facility

DROPPED_RAW_COLUMNS = frozenset({"licensee_name", "licensee", "facility_phone", "facility_address"})

_KIND = {"CHILD CARE CENTER": "childcare_center", "FAMILY CHILD CARE HOME": "family_childcare_home"}


def curate_cdss_rows(
    rows: list[dict[str, str]], prov: Provenance, res: int = 8
) -> list[tuple[Facility, float | None, float | None]]:
    """Return (Facility, lat, lon) for LICENSED rows only. FCCHs keep zip-centroid coordinates."""
    out: list[tuple[Facility, float | None, float | None]] = []
    for r in rows:
        if r["status"].strip().upper() != "LICENSED":
            continue
        kind = _KIND.get(r["facility_type"].strip().upper(), "other")
        lat, lon = float(r["latitude"]), float(r["longitude"])
        precision = r.get("location_precision") or (
            "zip_centroid" if kind == "family_childcare_home" else "rooftop"
        )
        fac = Facility(
            facility_id=r["facility_number"],
            kind=kind,
            licensed_capacity=int(r["capacity"]),
            status="LICENSED",
            h3_r8=h3.latlng_to_cell(lat, lon, res),
            location_precision=precision,
            prov=prov,
        )
        out.append((fac, lat, lon))
    return out


def read_cdss_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def facility_columns(fac: Facility) -> dict[str, Any]:
    """Flatten to the curated.facility column order (geometry handled by the writer)."""
    return {
        "facility_id": fac.facility_id,
        "gers_id": fac.gers_id,
        "kind": fac.kind,
        "licensed_capacity": fac.licensed_capacity,
        "status": fac.status,
        "location_precision": fac.location_precision,
        "h3_r8": fac.h3_r8,
        "release_id": fac.prov.release_id,
        "method_ver": fac.prov.method_ver,
        "build_id": fac.prov.build_id,
        "license_class": LicenseClass(fac.prov.license_class).value,
    }
