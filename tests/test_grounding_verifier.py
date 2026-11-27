"""ADR-004 verifier: the 7 G-102 tests (ported to pytest) plus number words and the CLI."""

from __future__ import annotations

import json
from decimal import Decimal as D
from pathlib import Path

from spine.decision.grounding_verifier import FeatureRow, main, verify

ROWS = [
    FeatureRow("seats_gap_882830", D("1240"), "", "cdss_ccl_2026-11-01"),
    FeatureRow("pct_children_beyond_15min", D("37.5"), "%", "acs5_2023"),
    FeatureRow("median_drive_min", D("14.2"), "", "osm_ca_2026-11-20"),
]
ALLOWED = {"cdss_ccl_2026-11-01", "acs5_2023", "osm_ca_2026-11-20"}


def test_pass() -> None:
    memo = (
        "Gap is 1,240 seats [src:cdss_ccl_2026-11-01]; 37.5% of children live beyond 15-min "
        "[src:acs5_2023]... median drive 14.2 min [src:osm_ca_2026-11-20]."
    )
    rows = [*ROWS, FeatureRow("param_isochrone_min", D("15"), "", "osm_ca_2026-11-20")]
    assert verify(memo, rows, ALLOWED) == []


def test_parameter_must_be_a_row() -> None:
    memo = "37.5% of children live beyond 15-min [src:acs5_2023]"
    assert [f.token for f in verify(memo, ROWS, ALLOWED)] == ["15"]


def test_hallucinated_number() -> None:
    f = verify("Gap is 1,900 seats [src:cdss_ccl_2026-11-01]", ROWS, ALLOWED)
    assert f[0].reason == "no deterministic feature row matches"


def test_uncited_release() -> None:
    f = verify("37.5% of children are far away.", ROWS, ALLOWED)
    assert "not cited" in f[0].reason


def test_unpinned_citation() -> None:
    f = verify("Gap is 1,240 [src:cdss_latest] [src:cdss_ccl_2026-11-01]", ROWS, ALLOWED)
    assert any("not in pinned" in x.reason for x in f)


def test_rounding_tolerance() -> None:
    assert verify("about 14.25 min [src:osm_ca_2026-11-20]", ROWS, ALLOWED) == []


def test_unit_mismatch() -> None:
    rows = [FeatureRow("x", D("37.5"), "%", "acs5_2023")]
    assert verify("37.5 seats [src:acs5_2023]", rows, ALLOWED) == []  # unitless prose tolerated
    assert len(verify("$37.5 [src:acs5_2023]", rows, ALLOWED)) == 1  # '$' vs '%' is not


def test_year_vintage() -> None:
    assert verify("ACS 2023 [src:acs5_2023]", [], ALLOWED) == []
    assert len(verify("in 2019 [src:acs5_2023]", [], ALLOWED)) == 1


def test_number_words_flagged() -> None:
    f = verify("Twelve centers closed [src:acs5_2023]", [], ALLOWED)
    assert [x.token for x in f] == ["Twelve"]
    assert verify("Twelve centers closed", [], ALLOWED, flag_number_words=False) == []


def test_list_ordinals_ignored() -> None:
    assert verify("1. Gap is 1,240 seats [src:cdss_ccl_2026-11-01]", ROWS, ALLOWED) == []


def test_cli_exit_codes(tmp_path: Path) -> None:
    payload = {
        "allowed_releases": sorted(ALLOWED),
        "rows": [{"feature_id": "g", "value": 1240, "release_id": "cdss_ccl_2026-11-01"}],
    }
    feats = tmp_path / "f.json"
    feats.write_text(json.dumps(payload))
    ok, bad = tmp_path / "ok.md", tmp_path / "bad.md"
    ok.write_text("Gap is 1,240 seats [src:cdss_ccl_2026-11-01]\n")
    bad.write_text("Gap is 1,300 seats [src:cdss_ccl_2026-11-01]\n")
    assert main(["x", str(ok), str(feats)]) == 0
    assert main(["x", str(bad), str(feats)]) == 1
