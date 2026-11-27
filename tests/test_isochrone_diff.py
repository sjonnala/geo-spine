"""Kernel #1 Isochrone Diff on the SYNTHETIC hand-built Valhalla fixture."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import h3
import pyarrow.parquet as pq
import pytest

from conftest import ORIGIN
from spine.compute.isochrone_diff import (
    METHOD_VER,
    build_isochrone_request,
    isochrone_diff,
    jaccard,
    origin_request,
    parse_valhalla_isochrone,
    polyfill,
    radius_cells,
    run_kernel,
)
from spine.compute.models import Catchment

REL = ["fixture_valhalla_iso_sc_2026-11-27"]


def test_request_body_matches_adr003_contract() -> None:
    body = build_isochrone_request(37.35, -121.95)
    assert body["contours"] == [{"time": 5}, {"time": 10}, {"time": 15}]
    assert body["polygons"] is True and body["costing"] == "auto"
    lat, lon = h3.cell_to_latlng(ORIGIN)
    assert origin_request(ORIGIN)["locations"] == [{"lat": lat, "lon": lon}]


def test_parse_sorts_contours_and_rejects_lines(iso_payload: dict[str, Any]) -> None:
    assert [c.minutes for c in parse_valhalla_isochrone(iso_payload)] == [5, 10, 15]
    bad = {
        "type": "FeatureCollection",
        "features": [
            {
                "properties": {"contour": 5},
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            }
        ],
    }
    with pytest.raises(ValueError, match="polygons=true"):
        parse_valhalla_isochrone(bad)


def test_polyfill_keeps_cells_whose_centroid_is_inside() -> None:
    lat, lon = h3.cell_to_latlng(ORIGIN)
    d = 0.0005  # tiny square around the origin centroid: only the origin cell's centroid is inside
    square = {
        "type": "Polygon",
        "coordinates": [
            [
                (lon - d, lat - d),
                (lon + d, lat - d),
                (lon + d, lat + d),
                (lon - d, lat + d),
                (lon - d, lat - d),
            ]
        ],
    }
    assert polyfill(square) == frozenset({ORIGIN})


def test_radius_cells_are_within_radius() -> None:
    o = h3.cell_to_latlng(ORIGIN)
    disc = radius_cells(ORIGIN, 3218.688)
    assert ORIGIN in disc
    assert all(h3.great_circle_distance(o, h3.cell_to_latlng(c), unit="m") <= 3218.688 for c in disc)
    ring = h3.grid_disk(ORIGIN, 8)
    outside = set(ring) - disc
    assert all(h3.great_circle_distance(o, h3.cell_to_latlng(c), unit="m") > 3218.688 for c in outside)


def test_jaccard_edges() -> None:
    assert jaccard(frozenset(), frozenset()) == 1.0
    assert jaccard(frozenset("ab"), frozenset("bc")) == pytest.approx(1 / 3)


def test_nested_contours_and_barrier_diagnostic(iso_payload: dict[str, Any]) -> None:
    diffs = isochrone_diff(ORIGIN, parse_valhalla_isochrone(iso_payload), radius_mi=2.0)
    by_min = {d.minutes: d for d in diffs}
    assert by_min[5].iso_cells <= by_min[10].iso_cells <= by_min[15].iso_cells
    d15 = by_min[15]
    # The synthetic barrier makes the radius overcount north and undercount east-west.
    assert d15.radius_only > 0 and d15.iso_only > 0
    assert 0 < d15.jaccard < 1
    assert d15.both + d15.iso_only + d15.radius_only == len(d15.iso_cells | d15.radius_cells)
    o_lat = h3.cell_to_latlng(ORIGIN)[0]
    north_missed = [c for c in d15.radius_cells - d15.iso_cells if h3.cell_to_latlng(c)[0] > o_lat]
    assert north_missed, "radius should include cells north of the barrier that drive-time can't reach"


def test_run_kernel_writes_adr002_tables(iso_payload: dict[str, Any], tmp_path: Path) -> None:
    diffs, cat_path, diag_path = run_kernel(
        ORIGIN, iso_payload, radius_mi=2.0, out_dir=tmp_path, release_ids=REL, build_id="t1"
    )
    assert cat_path == tmp_path / "features/isochrone" / METHOD_VER / "catchment_cells.parquet"
    cat = pq.read_table(cat_path)
    assert cat.column_names == [
        "catchment_id",
        "origin_h3_r8",
        "mode",
        "minutes",
        "member_h3_r8",
        "release_ids",
        "method_ver",
        "build_id",
        "license_class",
    ]
    assert cat.num_rows == sum(len(d.iso_cells) for d in diffs)
    diag = pq.read_table(diag_path).to_pylist()
    assert [r["minutes"] for r in diag] == [5, 10, 15]
    assert diag[2]["radius_vs_isochrone_jaccard"] == pytest.approx(diffs[2].jaccard)
    # Rows validate as ADR-002 Catchment entities.
    from spine.catalog.models import LicenseClass, Provenance

    d15 = diffs[2]
    Catchment(
        catchment_id=f"{ORIGIN}:auto:15",
        origin_h3_r8=ORIGIN,
        mode="auto",
        minutes=15,
        member_cells_r8=tuple(sorted(d15.iso_cells)),
        prov=Provenance(
            release_id=REL[0], method_ver=METHOD_VER, build_id="t1", license_class=LicenseClass.SHARE_ALIKE
        ),
    )
