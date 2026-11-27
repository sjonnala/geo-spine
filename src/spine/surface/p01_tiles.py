"""Product 01 map export (Surface context): GeoJSON for the static MapLibre viewer and the
newline-delimited GeoJSON that tippecanoe turns into PMTiles (ADR-003, G-103 section 1.5).

Layer ``cells``: one res-8 hexagon per populated cell, with only the properties the spec lists.
Layer ``centers``: child care **centers** at rooftop precision, with capacity only. Family child
care homes are never drawn as points (H&SC section 1596.86, G-101 Q5); no names or licensee fields.

Rendered tiles are a Produced Work (G-101 Q4). The per-cell table itself blends OSM drive times
with CDSS and ACS, so it is not published unless the Director chooses ODbL (G-103 open item 3).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import h3

from spine.decision.childcare_gap import RegionAllocation, cell_verdict

ATTRIBUTION = (
    "© OpenStreetMap contributors (ODbL) · CA Dept. of Social Services licensing data · "
    "U.S. Census Bureau ACS 5-year"
)
CELL_PROPERTIES = (
    "h3_r8",
    "children_0_5",
    "seats_per_child_2sfca",
    "gap_2sfca",
    "verdict",
    "abstain_reason",
    "release_ids",
    "build_id",
)
CENTER_PROPERTIES = ("licensed_capacity",)


def _hexagon(cell: str) -> dict[str, Any]:
    ring = [[round(lon, 6), round(lat, 6)] for lat, lon in h3.cell_to_boundary(cell)]
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def cells_feature_collection(
    region: RegionAllocation, release_ids: Sequence[str], build_id: str
) -> dict[str, Any]:
    rels = sorted(release_ids)
    feats = []
    for c in sorted(region.cells):
        cell = region.cells[c]
        verdict, reason = cell_verdict(cell)
        props = {
            "h3_r8": c,
            "children_0_5": cell.children_0_5,
            "seats_per_child_2sfca": round(cell.seats_per_child, 6),
            "gap_2sfca": round(cell.gap_seats, 2),
            "verdict": verdict,
            "abstain_reason": reason,
            "release_ids": rels,
            "build_id": build_id,
        }
        feats.append({"type": "Feature", "properties": props, "geometry": _hexagon(c)})
    return {"type": "FeatureCollection", "attribution": ATTRIBUTION, "features": feats}


def centers_feature_collection(
    facilities: Iterable[tuple[str, str, int, float | None, float | None]],
) -> dict[str, Any]:
    """``facilities``: (kind, location_precision, licensed_capacity, lat, lon). Keeps rooftop
    child care centers only."""
    feats = [
        {
            "type": "Feature",
            "properties": {"licensed_capacity": cap},
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
        }
        for kind, precision, cap, lat, lon in facilities
        if kind == "childcare_center" and precision == "rooftop" and lat is not None and lon is not None
    ]
    return {"type": "FeatureCollection", "attribution": ATTRIBUTION, "features": feats}


def write_geojson(fc: dict[str, Any], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fc, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    return p


def write_geojsonseq(fc: dict[str, Any], path: str | Path) -> Path:
    """One feature per line, the input tippecanoe reads for ``make tiles``."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(f, separators=(",", ":"), sort_keys=True) for f in fc["features"]]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p
