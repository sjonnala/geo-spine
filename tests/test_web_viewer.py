"""web/p01-access-gap: static checks on the viewer and its synthetic GeoJSON export (G-103 1.5)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from conftest import FIXTURE_RELEASES, WEB
from spine.surface.p01_memo import FFN_DISCLAIMER
from spine.surface.p01_tiles import ATTRIBUTION, CELL_PROPERTIES, CENTER_PROPERTIES

HTML = (WEB / "index.html").read_text(encoding="utf-8")
JS = (WEB / "app.js").read_text(encoding="utf-8")


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))


def test_copy_rules_on_page() -> None:
    page = _text(HTML)
    assert "licensed-capacity gap" in page.lower()
    assert re.sub(r"\*\*", "", FFN_DISCLAIMER) in page  # same FFN disclaimer as the memo
    assert "desert" not in (HTML + JS).lower()
    assert "Synthetic fixture data" in page


def test_attribution_present() -> None:
    assert ATTRIBUTION in _text(HTML) and ATTRIBUTION in JS
    for src in ("OpenStreetMap", "Social Services", "ACS"):
        assert src in ATTRIBUTION


def test_pmtiles_protocol_and_layers() -> None:
    assert 'maplibregl.addProtocol("pmtiles", protocol.tile)' in JS
    assert '"pmtiles://" + tilesUrl' in JS
    for layer in ("cells-gap", "cells-abstain", "cells-outline", "centers", "catchment-selected"):
        assert f'id: "{layer}"' in JS


def test_cdn_versions_pinned() -> None:
    for url in re.findall(r'(?:src|href)="(https://[^"]+)"', HTML):
        assert re.search(r"@\d+\.\d+\.\d+/", url), url
        assert "latest" not in url


def test_cells_export_contract() -> None:
    fc = json.loads((WEB / "data/cells.geojson").read_text())
    assert fc["attribution"] == ATTRIBUTION and fc["features"]
    for f in fc["features"]:
        assert tuple(sorted(f["properties"])) == tuple(sorted(CELL_PROPERTIES))
        assert f["geometry"]["type"] == "Polygon"
        assert set(f["properties"]["release_ids"]) == set(FIXTURE_RELEASES.values())
    assert {f["properties"]["verdict"] for f in fc["features"]} <= {
        "recommend",
        "do_not_recommend",
        "abstain",
    }


def test_centers_export_has_no_family_homes_or_names() -> None:
    fc = json.loads((WEB / "data/centers.geojson").read_text())
    blob = json.dumps(fc).lower()
    assert "licensee" not in blob and "synthetic home" not in blob and "name" not in blob
    assert all(tuple(f["properties"]) == CENTER_PROPERTIES for f in fc["features"])
    assert all(f["geometry"]["type"] == "Point" for f in fc["features"])


def test_sharing_index_is_anonymous() -> None:
    s = json.loads((WEB / "data/sharing.json").read_text())
    assert s["minutes"] == 15 and isinstance(s["facilities"], int)
    assert all(isinstance(k, int) for ks in s["reach"].values() for k in ks)
    assert "SYN-" not in json.dumps(s)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_app_js_parses() -> None:
    subprocess.run(["node", "--check", str(WEB / "app.js")], check=True)
