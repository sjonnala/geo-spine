"""Every fixture says it is synthetic, and the curated facility table is valid GeoParquet."""

from __future__ import annotations

import json

import pyarrow.parquet as pq

from conftest import FX, ISO_FIXTURE


def test_valhalla_fixture_is_labelled_synthetic_not_recorded() -> None:
    data = json.loads(ISO_FIXTURE.read_text())
    note = data["_fixture_note"]
    assert "SYNTHETIC" in note and "Not recorded from a Valhalla server" in note
    assert all(f["properties"]["fixture"] == "synthetic" for f in data["features"])


def test_memo_fixture_is_labelled() -> None:
    assert "Synthetic fixture data" in (FX / "memos/p01_santa_clara_memo.md").read_text()


def test_cdss_raw_names_are_synthetic() -> None:
    lines = (FX / "santa_clara/cdss_raw_synthetic.csv").read_text().splitlines()[1:]
    assert lines and all("Synthetic" in ln for ln in lines)


def test_facility_geoparquet_contract() -> None:
    t = pq.read_table(FX / "santa_clara/facility.parquet")
    geo = json.loads(t.schema.metadata[b"geo"])
    assert geo["primary_column"] == "geom" and geo["columns"]["geom"]["encoding"] == "WKB"
    assert t.column_names == [
        "facility_id",
        "gers_id",
        "kind",
        "licensed_capacity",
        "status",
        "location_precision",
        "h3_r8",
        "geom",
        "release_id",
        "method_ver",
        "build_id",
        "license_class",
    ]
    assert "licensee_name" not in t.column_names
    assert set(t.column("status").to_pylist()) == {"LICENSED"}
