"""ADR-001 catalog gate over data/catalog/releases.yaml (the G-101 seed) and the fixture catalog."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from spine.catalog.models import LicenseClass
from spine.catalog.releases import CatalogError, assert_publishable, load_catalog, main

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "data/catalog/releases.yaml"
FIXTURE = ROOT / "tests/fixtures/releases.fixture.yaml"
G101_SOURCES = {
    "calfire_dins",
    "cdss_ccl",
    "google_aef",
    "osm_geofabrik_ca",
    "overture_transportation",
    "overture_places",
    "usda_naip",
    "usgs_3dep",
    "landfire",
    "carbon_mapper",
    "cfp_stats",
}


def test_real_catalog_covers_g101_seed() -> None:
    cat = load_catalog(REAL)
    assert {r.source_id for r in cat.values()} >= G101_SOURCES
    assert all(r.status == "pending_download" for r in cat.values())


def test_g101_corrections_carried() -> None:
    cat = load_catalog(REAL)
    cm = cat["carbon_mapper_2026-01-13"]
    assert cm.license_class is LicenseClass.NON_COMMERCIAL and not cm.commercial_ok
    assert "CC" not in cm.license_spdx  # custom licence, not CC BY-NC
    cdss = cat["cdss_ccl_2026-11-02"]
    assert cdss.license_class is LicenseClass.RESTRICTED and not cdss.commercial_ok
    assert "2 OCPU / 12 GB" in (cat["osm_geofabrik_ca_2026-11-20"].notes or "")


def test_pending_release_cannot_feed_a_build() -> None:
    with pytest.raises(CatalogError, match="sha256 not pinned"):
        assert_publishable(load_catalog(REAL), ["cdss_ccl_2026-11-02"])
    with pytest.raises(CatalogError, match="not in releases.yaml"):
        assert_publishable(load_catalog(REAL), ["nope_2026"])


def test_latest_row_fails_catalog(tmp_path: Path) -> None:
    bad = tmp_path / "r.yaml"
    bad.write_text(REAL.read_text().replace('vintage: "2026-11-20"', 'vintage: "latest"', 1))
    with pytest.raises(CatalogError, match="latest"):
        load_catalog(bad)
    assert main(["x", str(bad)]) == 1


def test_duplicate_release_id_fails(tmp_path: Path) -> None:
    text = FIXTURE.read_text()
    body = text.split("releases:\n", 1)[1]
    dup = tmp_path / "d.yaml"
    dup.write_text("releases:\n" + body + body)
    with pytest.raises(CatalogError, match="duplicate"):
        load_catalog(dup)


def test_fixture_catalog_checksums_match_committed_files() -> None:
    cat = load_catalog(FIXTURE)
    assert_publishable(cat, cat)
    for r in cat.values():
        assert r.url.startswith("fixture://") and "SYNTHETIC" in (r.notes or "")
        path = ROOT / r.url.removeprefix("fixture://")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == r.sha256, r.release_id
