"""ADR-005 guard: the 4 G-102 tests plus the Director audit fixes (unknown release, licensee)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from license_guard import PII_COLS, check, main

ROOT = Path(__file__).resolve().parents[1]
R = [
    {"release_id": "osm_ca", "license_class": "share_alike"},
    {"release_id": "acs", "license_class": "public_domain"},
    {"release_id": "cm", "license_class": "non_commercial"},
]


def M(**a: Any) -> dict[str, Any]:
    art = {"name": "x", "path": "data/features/x.parquet", "inputs": ["osm_ca", "acs"], "columns": ["h3_r8"]}
    art.update(a)
    return {"releases": R, "artifacts": [art]}


def test_odbl_mix_fails() -> None:
    assert check(M())


def test_produced_work_ok() -> None:
    assert check(M(produced_work=True)) == []


def test_odbl_licensed_artifact_ok() -> None:
    assert check(M(license="ODbL-1.0")) == []


def test_nc() -> None:
    assert len(check(M(inputs=["cm"], commercial=True))) == 2
    assert check(M(inputs=["cm"], path="quarantine/nc/s.parquet")) == []


def test_pii() -> None:
    assert check(M(produced_work=True, columns=["h3_r8", "owner_name"]))


# --- Director audit fix 1: unknown release_id is an L3 error, not a KeyError ---
def test_unknown_release_id_reported_not_keyerror() -> None:
    errs = check(M(inputs=["acs", "does_not_exist_2026"]))
    assert errs == ["x: inputs not in releases.yaml: ['does_not_exist_2026']"]


def test_unknown_release_only_input() -> None:
    assert check(M(inputs=["ghost_2026"])) == ["x: inputs not in releases.yaml: ['ghost_2026']"]


# --- Director audit fix 2: CDSS licensee names never leak ---
@pytest.mark.parametrize("col", ["licensee", "licensee_name", "LICENSEE_NAME", "facility_licensee"])
def test_licensee_columns_blocked(col: str) -> None:
    errs = check(M(produced_work=True, columns=["h3_r8", col]))
    assert errs and "PII-like columns" in errs[0]


def test_licensed_capacity_is_not_pii() -> None:
    assert not PII_COLS.search("licensed_capacity")


def test_public_structure_grain_needs_k_anon() -> None:
    assert check(M(produced_work=True, grain="structure", public=True))
    assert check(M(produced_work=True, grain="structure", public=True, k_anon_min=10)) == []


def test_p01_fixture_manifest_passes() -> None:
    rc = main(
        [
            str(ROOT / "data/manifests/p01_santa_clara_fixture.json"),
            "--catalog",
            str(ROOT / "tests/fixtures/releases.fixture.yaml"),
        ]
    )
    assert rc == 0


def test_p01_gap_scores_fail_without_produced_work_boundary() -> None:
    import json

    from spine.catalog.releases import as_guard_releases, load_catalog

    m = json.loads((ROOT / "data/manifests/p01_santa_clara_fixture.json").read_text())
    m["releases"] = as_guard_releases(load_catalog(ROOT / "tests/fixtures/releases.fixture.yaml"))
    gap = next(a for a in m["artifacts"] if a["name"] == "p01_gap_scores")
    gap.pop("produced_work")
    errs = check(m)
    assert len(errs) == 1 and "p01_gap_scores: ODbL input mixed" in errs[0]


# --- G-301 rule L4: restricted inputs (e.g. CDSS) stay out of commercial artifacts ---
R4 = [*R, {"release_id": "cdss", "license_class": "restricted"}]


def M4(**a: Any) -> dict[str, Any]:
    art = {"name": "p", "path": "data/decisions/p.parquet", "inputs": ["acs", "cdss"], "columns": ["h3_r8"]}
    art.update(a)
    return {"releases": R4, "artifacts": [art]}


def test_l4_restricted_in_commercial_artifact_fails() -> None:
    assert check(M4(commercial=True)) == [
        "p: restricted input ['cdss'] in a commercial artifact without approval"
    ]


def test_l4_restricted_noncommercial_ok() -> None:
    assert check(M4()) == [] and check(M4(commercial=False)) == []


def test_l4_bare_true_flag_is_not_an_approval() -> None:
    assert check(M4(commercial=True, restricted_approvals=True))  # type: ignore[arg-type]
    assert check(M4(commercial=True, restricted_approved=True))


def test_l4_approval_needs_release_id_and_reference() -> None:
    assert check(M4(commercial=True, restricted_approvals=["cdss"])) == [
        "p: restricted_approvals given without a restricted_approval_ref"
    ]
    ok = M4(
        commercial=True, restricted_approvals=["cdss"], restricted_approval_ref="CHHS approval 2027-01-05"
    )
    assert check(ok) == []


def test_l4_approval_for_other_release_does_not_cover_cdss() -> None:
    errs = check(M4(commercial=True, restricted_approvals=["acs"], restricted_approval_ref="x"))
    assert errs == ["p: restricted input ['cdss'] in a commercial artifact without approval"]


def test_l4_public_domain_commercial_ok() -> None:
    assert check(M4(inputs=["acs"], commercial=True)) == []


def test_p01_memo_flagged_commercial_fails_l4() -> None:
    import json

    from spine.catalog.releases import as_guard_releases, load_catalog

    m = json.loads((ROOT / "data/manifests/p01_santa_clara_fixture.json").read_text())
    m["releases"] = as_guard_releases(load_catalog(ROOT / "tests/fixtures/releases.fixture.yaml"))
    memo = next(a for a in m["artifacts"] if a["name"] == "p01_memo")
    memo["commercial"] = True
    errs = check(m)
    assert len(errs) == 1 and errs[0].startswith(
        "p01_memo: restricted input ['fixture_cdss_ccl_sc_2026-11-02']"
    )
