"""ADR-003 DuckDB SQL executed against the SYNTHETIC Santa Clara GeoParquet fixtures.

Two paths, reported separately:
* native: DuckDB + the real `spatial` and `h3` extensions. Skipped (not faked) when the extensions
  can't be downloaded.
* shim: the same SQL text in DuckDB core with test-only Python UDFs standing in for the extension
  functions (tests/support/duckdb_shim.py). Proves the SQL's joins and rollups, not the extensions.

Both paths are checked against an independent pure-Python computation with the h3 library.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import h3
import pyarrow.parquet as pq
import pytest

from conftest import FX, ORIGIN
from spine.compute.adr003_sql import ExtensionUnavailable, connect_native, run_all
from spine.compute.isochrone_diff import run_kernel

FACILITY = FX / "santa_clara/facility.parquet"
CHILDREN = FX / "santa_clara/children.parquet"


@pytest.fixture(scope="module")
def catchment(tmp_path_factory: pytest.TempPathFactory, iso_payload: dict[str, Any]) -> Path:
    out = tmp_path_factory.mktemp("kernel")
    _, cat_path, _ = run_kernel(
        ORIGIN,
        iso_payload,
        radius_mi=2.0,
        out_dir=out,
        release_ids=["fixture_valhalla_iso_sc_2026-11-27"],
        build_id="t1",
    )
    return cat_path


def expected(catchment: Path) -> dict[str, Any]:
    fac = pq.read_table(FACILITY).to_pylist()
    seats: dict[str, int] = defaultdict(int)
    for f in fac:
        seats[h3.cell_to_parent(f["h3_r8"], 7)] += f["licensed_capacity"]
    kids = {r["h3_r8"]: r["children_0_5"] for r in pq.read_table(CHILDREN).to_pylist()}
    demand: dict[tuple[str, int], int] = defaultdict(int)
    for r in pq.read_table(catchment).to_pylist():
        demand[(r["origin_h3_r8"], r["minutes"])] += kids.get(r["member_h3_r8"], 0)
    return {
        "hex_roundtrip": sorted((f["facility_id"], f["h3_r8"], f["h3_r8"]) for f in fac),
        "seats_by_r7": sorted(seats.items()),
        "catchment_demand": sorted((o, m, d) for (o, m), d in demand.items()),
    }


def check(results: dict[str, list[tuple[Any, ...]]], catchment: Path) -> None:
    exp = expected(catchment)
    assert [tuple(r) for r in results["hex_roundtrip"]] == exp["hex_roundtrip"]
    assert [(r[0], int(r[1])) for r in results["seats_by_r7"]] == exp["seats_by_r7"]
    assert [(r[0], r[1], int(r[2])) for r in results["catchment_demand"]] == exp["catchment_demand"]
    assert [r[1] for r in results["catchment_demand"]] == [5, 10, 15]


def test_adr003_sql_native_extensions(catchment: Path) -> None:
    try:
        con = connect_native()
    except ExtensionUnavailable as e:
        pytest.skip(f"NOT RUN: DuckDB spatial/h3 extensions unavailable here ({e})")
    try:
        check(run_all(con, FACILITY, catchment, CHILDREN), catchment)
    finally:
        con.close()


def test_adr003_sql_with_test_shim(catchment: Path) -> None:
    from support.duckdb_shim import connect_shim

    con = connect_shim()
    try:
        check(run_all(con, FACILITY, catchment, CHILDREN), catchment)
    finally:
        con.close()
