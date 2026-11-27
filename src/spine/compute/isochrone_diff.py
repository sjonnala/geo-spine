"""Kernel #1, Isochrone Diff (ADR-003 isochrone kernel contract).

1. Take a Valhalla ``/isochrone`` response (``polygons=true``) for an origin cell centroid: a live
   call or a recorded fixture. CI never calls Valhalla; tests use tests/fixtures/valhalla/.
2. Polyfill each contour polygon to H3 res 8, keeping a cell when its centroid falls inside.
3. Emit ``catchment_cells`` rows (one per origin x minutes x member cell, ADR-002 contract).
4. Emit a ``radius_vs_isochrone_jaccard`` diagnostic per origin and contour: how far a naive
   straight-line radius disagrees with the drive-time catchment.

Outputs are ODbL derivative data when the routing graph is OSM (ADR-005 L1).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h3

METHOD_VER = "0.1.0"
RES = 8
METERS_PER_MILE = 1609.344


@dataclass(frozen=True)
class IsochroneContour:
    minutes: int
    geometry: dict[str, Any]  # GeoJSON Polygon or MultiPolygon, [lon, lat] order


@dataclass(frozen=True)
class DiffResult:
    origin_h3_r8: str
    minutes: int
    radius_mi: float
    iso_cells: frozenset[str]
    radius_cells: frozenset[str]

    @property
    def both(self) -> int:
        return len(self.iso_cells & self.radius_cells)

    @property
    def iso_only(self) -> int:
        """Reachable by road but outside the radius: a radius undercounts these."""
        return len(self.iso_cells - self.radius_cells)

    @property
    def radius_only(self) -> int:
        """Inside the radius but not reachable in time: a radius overcounts these."""
        return len(self.radius_cells - self.iso_cells)

    @property
    def jaccard(self) -> float:
        return jaccard(self.iso_cells, self.radius_cells)


def build_isochrone_request(
    lat: float, lon: float, minutes: Sequence[int] = (5, 10, 15), costing: str = "auto"
) -> dict[str, Any]:
    """Body for ``POST /isochrone`` on a Valhalla server (ADR-003 compose template)."""
    return {
        "locations": [{"lat": lat, "lon": lon}],
        "costing": costing,
        "contours": [{"time": m} for m in minutes],
        "polygons": True,
    }


def origin_request(origin_h3_r8: str, **kw: Any) -> dict[str, Any]:
    lat, lon = h3.cell_to_latlng(origin_h3_r8)
    return build_isochrone_request(lat, lon, **kw)


def parse_valhalla_isochrone(payload: dict[str, Any]) -> list[IsochroneContour]:
    """Parse a Valhalla isochrone FeatureCollection into contours, smallest first."""
    if payload.get("type") != "FeatureCollection":
        raise ValueError("expected a GeoJSON FeatureCollection from /isochrone")
    out: list[IsochroneContour] = []
    for feat in payload["features"]:
        props = feat.get("properties", {})
        if props.get("metric", "time") != "time":
            raise ValueError("only time contours are supported by Kernel #1")
        geom = feat["geometry"]
        if geom["type"] not in ("Polygon", "MultiPolygon"):
            raise ValueError(f"request isochrones with polygons=true (got {geom['type']})")
        out.append(IsochroneContour(minutes=int(props["contour"]), geometry=geom))
    return sorted(out, key=lambda c: c.minutes)


def polyfill(geometry: dict[str, Any], res: int = RES) -> frozenset[str]:
    """Cells whose centroid lies inside the polygon (h3 polygon_to_cells semantics)."""
    return frozenset(h3.geo_to_cells(geometry, res))


def radius_cells(origin_h3_r8: str, radius_m: float) -> frozenset[str]:
    """Cells whose centroid lies within ``radius_m`` (great-circle) of the origin centroid."""
    res = h3.get_resolution(origin_h3_r8)
    o = h3.cell_to_latlng(origin_h3_r8)
    spacing = h3.average_hexagon_edge_length(res, unit="m") * math.sqrt(3)
    k = math.ceil(radius_m / spacing) + 2
    return frozenset(
        c
        for c in h3.grid_disk(origin_h3_r8, k)
        if h3.great_circle_distance(o, h3.cell_to_latlng(c), unit="m") <= radius_m
    )


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    union = a | b
    return 1.0 if not union else len(a & b) / len(union)


def isochrone_diff(
    origin_h3_r8: str, contours: Iterable[IsochroneContour], radius_mi: float
) -> list[DiffResult]:
    disc = radius_cells(origin_h3_r8, radius_mi * METERS_PER_MILE)
    return [DiffResult(origin_h3_r8, c.minutes, radius_mi, polyfill(c.geometry), disc) for c in contours]


def catchment_rows(
    diffs: Iterable[DiffResult],
    *,
    mode: str,
    release_ids: Sequence[str],
    build_id: str,
    license_class: str = "share_alike",
) -> list[dict[str, Any]]:
    """`features.catchment_cells` rows in ADR-002 column order."""
    rels = sorted(release_ids)
    rows: list[dict[str, Any]] = []
    for d in diffs:
        cid = f"{d.origin_h3_r8}:{mode}:{d.minutes}"
        for cell in sorted(d.iso_cells):
            rows.append(
                {
                    "catchment_id": cid,
                    "origin_h3_r8": d.origin_h3_r8,
                    "mode": mode,
                    "minutes": d.minutes,
                    "member_h3_r8": cell,
                    "release_ids": rels,
                    "method_ver": METHOD_VER,
                    "build_id": build_id,
                    "license_class": license_class,
                }
            )
    return rows


def diagnostic_rows(
    diffs: Iterable[DiffResult], *, release_ids: Sequence[str], build_id: str
) -> list[dict[str, Any]]:
    rels = sorted(release_ids)
    return [
        {
            "origin_h3_r8": d.origin_h3_r8,
            "minutes": d.minutes,
            "radius_mi": d.radius_mi,
            "iso_cells": len(d.iso_cells),
            "radius_cells": len(d.radius_cells),
            "both_cells": d.both,
            "iso_only_cells": d.iso_only,
            "radius_only_cells": d.radius_only,
            "radius_vs_isochrone_jaccard": d.jaccard,
            "release_ids": rels,
            "method_ver": METHOD_VER,
            "build_id": build_id,
            "license_class": "share_alike",
        }
        for d in diffs
    ]


def write_rows(rows: list[dict[str, Any]], path: str | Path) -> Path:
    import pyarrow as pa
    import pyarrow.parquet as pq

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), p)
    return p


def run_kernel(
    origin_h3_r8: str,
    payload: dict[str, Any],
    *,
    radius_mi: float,
    out_dir: str | Path,
    release_ids: Sequence[str],
    build_id: str,
    mode: str = "auto",
) -> tuple[list[DiffResult], Path, Path]:
    """Run Kernel #1 end to end and write both feature tables under
    ``<out_dir>/features/isochrone/<METHOD_VER>/``."""
    diffs = isochrone_diff(origin_h3_r8, parse_valhalla_isochrone(payload), radius_mi)
    base = Path(out_dir) / "features" / "isochrone" / METHOD_VER
    cat = write_rows(
        catchment_rows(diffs, mode=mode, release_ids=release_ids, build_id=build_id),
        base / "catchment_cells.parquet",
    )
    diag = write_rows(
        diagnostic_rows(diffs, release_ids=release_ids, build_id=build_id),
        base / "radius_vs_isochrone_jaccard.parquet",
    )
    return diffs, cat, diag
