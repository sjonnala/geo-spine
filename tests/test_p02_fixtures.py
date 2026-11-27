"""Product 02 fixtures: pinned, synthetic, PII-free, reproducible, and guarded by ADR-005."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

import pytest
from license_guard import PII_COLS, check, load_catalog_releases

from spine.catalog.releases import assert_publishable
from support.p02 import P02_CATALOG, P02_MANIFEST, P02_WEB, ROOT, catalog, gen

FORBIDDEN_KEYS = re.compile(r"^(lat|lon|lng|latitude|longitude|h3.*|address|street|apn|parcel.*|zip)$", re.I)


def _keys(obj: Any) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _keys(v)}
    return set()


def test_catalog_pins_every_fixture_by_checksum() -> None:
    cat = catalog()
    assert_publishable(cat, cat)
    assert set(cat) >= set(gen().REL.__dict__.values())
    for r in cat.values():
        assert r.url.startswith("fixture://") and "SYNTHETIC" in (r.notes or ""), r.release_id
        path = ROOT / r.url.removeprefix("fixture://")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == r.sha256, r.release_id


def test_sources_are_labelled_synthetic_and_carry_no_person_fields() -> None:
    for rel_path in gen().source_files():
        data = json.loads((ROOT / rel_path).read_text(encoding="utf-8"))
        note = data["_fixture_note"]
        if rel_path.endswith("_synthetic.json"):  # data about places; the regulation copy and rubric are not
            assert note.startswith("SYNTHETIC fixture for CI."), rel_path
            assert [k for k in _keys(data) if PII_COLS.search(k)] == [], rel_path


def test_viewer_cards_export_no_location_or_parcel_keys() -> None:
    cards = json.loads((P02_WEB / "data" / "cards.json").read_text(encoding="utf-8"))
    keys = _keys(cards)
    assert [k for k in keys if FORBIDDEN_KEYS.match(k) or PII_COLS.search(k)] == []
    assert not re.search(r"\b8[0-9a-f]{14}\b", json.dumps(cards))  # no H3 cell ids anywhere


def _committed(files: dict[str, str]) -> dict[str, str]:
    return {k: (ROOT / k).read_text(encoding="utf-8") for k in files}


def test_fake_grid_build_reproduces_committed_files() -> None:
    files = gen().build_all(gen().fake_grid)
    assert files == _committed(files)


def test_real_h3_build_reproduces_committed_files() -> None:
    pytest.importorskip("h3")
    files = gen().build_all(gen().h3_r9)
    assert files == _committed(files)


# --- the ADR-005 guard over the Product 02 manifest -------------------------------------------------
def _manifest() -> dict[str, Any]:
    m: dict[str, Any] = json.loads(P02_MANIFEST.read_text(encoding="utf-8"))
    m["releases"] = load_catalog_releases(str(P02_CATALOG))
    return m


def _art(m: dict[str, Any], name: str) -> dict[str, Any]:
    return next(a for a in m["artifacts"] if a["name"] == name)


def test_manifest_passes_guard() -> None:
    assert check(_manifest()) == []


def test_guard_l1_footprints_mixed_without_produced_work() -> None:
    m = copy.deepcopy(_manifest())
    del _art(m, "p02_assessments")["produced_work"]
    assert any("ODbL input mixed" in e for e in check(m))


def test_guard_l2_non_commercial_input() -> None:
    m = copy.deepcopy(_manifest())
    _art(m, "p02_assessments")["inputs"].append(gen().NC_MODEL)
    assert any("quarantine/nc" in e for e in check(m))


def test_guard_l4_restricted_community_lists_in_commercial_build() -> None:
    m = copy.deepcopy(_manifest())
    _art(m, "p02_viewer_cards")["commercial"] = True
    assert any("restricted input" in e for e in check(m))


def test_guard_p1_person_column() -> None:
    m = copy.deepcopy(_manifest())
    _art(m, "p02_assessments")["columns"].append("owner_name")
    assert any("PII-like" in e for e in check(m))


def test_guard_p2_public_structure_cards() -> None:
    m = copy.deepcopy(_manifest())
    _art(m, "p02_viewer_cards")["public"] = True
    assert any("k_anon_min" in e for e in check(m))
