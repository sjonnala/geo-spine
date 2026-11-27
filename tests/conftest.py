from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "tests" / "fixtures"
ISO_FIXTURE = FX / "valhalla" / "isochrone_santa_clara_synthetic.json"
ORIGIN = "8828347029fffff"  # res 8 cell at the synthetic Santa Clara origin


@pytest.fixture(scope="session")
def iso_payload() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(ISO_FIXTURE.read_text(encoding="utf-8"))
    return data


CASSETTES = FX / "valhalla" / "cassettes"
WEB = ROOT / "web" / "p01-access-gap"
FIXTURE_RELEASES = {
    "acs": "fixture_acs5_sc_2023",
    "cdss": "fixture_cdss_ccl_sc_2026-11-02",
    "routing": "fixture_valhalla_iso_sc_2026-11-27",
    "matrix": "fixture_valhalla_matrix_sc_2026-11-27",
}


def load_p01_region_inputs() -> tuple[dict[str, int], list[Any], list[tuple[float, float]], list[str]]:
    """Children per cell, FacilitySeat list, facility (lat, lon) and the sorted demand cells, read
    from the synthetic Santa Clara fixtures exactly as `make fixtures` built the OD cassette."""
    import pyarrow.parquet as pq
    import shapely

    from spine.decision.childcare_gap import FacilitySeat

    kids = {
        r["h3_r8"]: int(r["children_0_5"])
        for r in pq.read_table(FX / "santa_clara/children.parquet").to_pylist()
    }
    seats: list[Any] = []
    coords: list[tuple[float, float]] = []
    for r in pq.read_table(FX / "santa_clara/facility.parquet").to_pylist():
        if r["location_precision"] == "suppressed":
            continue
        pt = shapely.from_wkb(r["geom"])
        seats.append(
            FacilitySeat(r["facility_id"], r["h3_r8"], r["licensed_capacity"], r["location_precision"])
        )
        coords.append((pt.y, pt.x))
    return kids, seats, coords, sorted(kids)
