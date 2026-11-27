"""ADR-003 DuckDB query patterns, executable.

The SQL is ADR-003's, with input paths as parameters and the hex-string rule applied
(``h3_h3_to_string``) so published IDs round-trip through JSON. It needs DuckDB's ``spatial``
extension and the ``h3`` community extension:

    INSTALL spatial; LOAD spatial; INSTALL h3 FROM community; LOAD h3;
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

EXTENSION_SQL = "INSTALL spatial; LOAD spatial; INSTALL h3 FROM community; LOAD h3;"


class ExtensionUnavailable(RuntimeError):
    """Raised when the spatial / h3 extensions cannot be installed or loaded."""


def _lit(path: str | Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def index_facilities_sql(facility_parquet: str | Path) -> str:
    return (
        "CREATE OR REPLACE TABLE curated_facility AS "
        "SELECT *, h3_latlng_to_cell(ST_Y(geom), ST_X(geom), 8) AS h3_r8_int "
        f"FROM read_parquet({_lit(facility_parquet)})"
    )


# Index check: the integer the extension computes must equal the stored hex-string key.
HEX_ROUNDTRIP_SQL = (
    "SELECT facility_id, h3_r8, h3_h3_to_string(h3_r8_int) AS h3_r8_from_sql "
    "FROM curated_facility ORDER BY facility_id"
)

# Seats per res-7 parent: sum counts, never average rates (ADR-001 rollup rule).
SEATS_BY_R7_SQL = (
    "SELECT h3_h3_to_string(h3_cell_to_parent(h3_r8_int, 7)) AS h3_r7, "
    "SUM(licensed_capacity) AS seats FROM curated_facility GROUP BY 1 ORDER BY 1"
)


def catchment_demand_sql(catchment_parquet: str | Path, children_parquet: str | Path) -> str:
    """Children within N minutes of each origin cell."""
    return (
        "SELECT c.origin_h3_r8, c.minutes, SUM(d.children_0_5) AS demand "
        f"FROM read_parquet({_lit(catchment_parquet)}) c "
        f"JOIN read_parquet({_lit(children_parquet)}) d ON d.h3_r8 = c.member_h3_r8 "
        "GROUP BY 1, 2 ORDER BY 1, 2"
    )


def connect_native() -> Any:
    """A DuckDB connection with the real spatial and h3 extensions, or ExtensionUnavailable."""
    import duckdb

    con = duckdb.connect()
    try:
        con.execute(EXTENSION_SQL)
    except Exception as e:  # duckdb raises IOException / HTTPException subclasses
        con.close()
        raise ExtensionUnavailable(str(e).splitlines()[0]) from e
    return con


def run_all(con: Any, facility: Path, catchment: Path, children: Path) -> dict[str, list[tuple[Any, ...]]]:
    con.execute(index_facilities_sql(facility))
    return {
        "hex_roundtrip": con.execute(HEX_ROUNDTRIP_SQL).fetchall(),
        "seats_by_r7": con.execute(SEATS_BY_R7_SQL).fetchall(),
        "catchment_demand": con.execute(catchment_demand_sql(catchment, children)).fetchall(),
    }
