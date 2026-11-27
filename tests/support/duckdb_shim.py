"""TEST-ONLY stand-ins for the DuckDB spatial + h3 extension functions ADR-003's SQL uses.

Used only when the real extensions can't be downloaded (for example, a sandbox whose proxy blocks
extensions.duckdb.org). Each function is a Python UDF backed by the h3 / shapely libraries, so the
ADR-003 SQL text runs unchanged in DuckDB core. Results from this path prove the SQL's logic and
joins, NOT the extensions' behaviour; the native-extension test is the one that proves that.
"""

from __future__ import annotations

from typing import Any

import duckdb
import h3
import shapely

try:  # DuckDB >= 2.0
    from duckdb.sqltypes import BLOB, DOUBLE, INTEGER, UBIGINT, VARCHAR
except ImportError:  # DuckDB 1.x
    from duckdb.typing import BLOB, DOUBLE, INTEGER, UBIGINT, VARCHAR  # type: ignore[no-redef]


def connect_shim() -> Any:
    con = duckdb.connect()

    def latlng_to_cell(lat: float, lng: float, res: int) -> int:
        return int(h3.str_to_int(h3.latlng_to_cell(lat, lng, res)))

    def cell_to_parent(cell: int, res: int) -> int:
        return int(h3.str_to_int(h3.cell_to_parent(h3.int_to_str(cell), res)))

    def h3_to_string(cell: int) -> str:
        return str(h3.int_to_str(cell))

    def st_x(wkb: bytes) -> float:
        return float(shapely.from_wkb(wkb).x)

    def st_y(wkb: bytes) -> float:
        return float(shapely.from_wkb(wkb).y)

    con.create_function("h3_latlng_to_cell", latlng_to_cell, [DOUBLE, DOUBLE, INTEGER], UBIGINT)
    con.create_function("h3_cell_to_parent", cell_to_parent, [UBIGINT, INTEGER], UBIGINT)
    con.create_function("h3_h3_to_string", h3_to_string, [UBIGINT], VARCHAR)
    con.create_function("_shim_st_x", st_x, [BLOB], DOUBLE)
    con.create_function("_shim_st_y", st_y, [BLOB], DOUBLE)
    # DuckDB >= 2.0 reads GeoParquet into a core GEOMETRY type (with ST_AsWKB but no ST_X/ST_Y);
    # DuckDB 1.x without `spatial` reads the same column as WKB BLOB.
    has_core_geometry = con.execute(
        "SELECT count(*) FROM duckdb_functions() WHERE function_name = 'st_aswkb'"
    ).fetchone()[0]
    to_wkb = "ST_AsWKB(g)::BLOB" if has_core_geometry else "g"
    con.execute(f"CREATE MACRO ST_X(g) AS _shim_st_x({to_wkb})")
    con.execute(f"CREATE MACRO ST_Y(g) AS _shim_st_y({to_wkb})")
    return con
