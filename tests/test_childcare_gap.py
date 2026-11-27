"""Product 01 scaffold: Santa Clara licensed-capacity gap, decision and ADR-004-checked memo."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pyarrow.parquet as pq
import pytest

from conftest import FX, ORIGIN
from spine.catalog.models import LicenseClass, Provenance
from spine.compute.isochrone_diff import isochrone_diff, parse_valhalla_isochrone
from spine.decision.childcare_gap import FacilitySeat, P01Releases, compute_gap, feature_rows, gap_decision
from spine.decision.grounding_verifier import FeatureRow, verify
from spine.identity.facilities import curate_cdss_rows, facility_columns, read_cdss_csv
from spine.surface.p01_memo import BANNED_TERMS, FFN_DISCLAIMER, GAP_TERM, build_memo, render_memo

REL = P01Releases(
    acs="fixture_acs5_sc_2023",
    cdss="fixture_cdss_ccl_sc_2026-11-02",
    routing="fixture_valhalla_iso_sc_2026-11-27",
)
ALLOWED = {REL.acs, REL.cdss, REL.routing}
WHEN = datetime(2026, 11, 27, tzinfo=UTC)


@pytest.fixture(scope="module")
def inputs(iso_payload: dict[str, Any]) -> tuple[Any, ...]:
    d15 = next(
        d for d in isochrone_diff(ORIGIN, parse_valhalla_isochrone(iso_payload), 2.0) if d.minutes == 15
    )
    kids = {
        r["h3_r8"]: r["children_0_5"] for r in pq.read_table(FX / "santa_clara/children.parquet").to_pylist()
    }
    fac = [
        FacilitySeat(r["h3_r8"], r["licensed_capacity"], r["location_precision"])
        for r in pq.read_table(FX / "santa_clara/facility.parquet").to_pylist()
    ]
    gap = compute_gap(ORIGIN, 15, d15.iso_cells, kids, fac)
    return d15, kids, fac, gap


def test_curation_drops_licensee_and_inactive_rows() -> None:
    prov = Provenance(
        release_id=REL.cdss, method_ver="0.1.0", build_id="t", license_class=LicenseClass.RESTRICTED
    )
    raw = read_cdss_csv(FX / "santa_clara/cdss_raw_synthetic.csv")
    assert "licensee_name" in raw[0]
    cur = curate_cdss_rows(raw, prov)
    assert len(cur) == sum(1 for r in raw if r["status"] == "LICENSED")
    cols = facility_columns(cur[0][0])
    assert not any("licensee" in c for c in cols)
    assert {f.location_precision for f, _, _ in cur if f.kind == "family_childcare_home"} == {"zip_centroid"}


def test_gap_arithmetic(inputs: tuple[Any, ...]) -> None:
    d15, kids, fac, gap = inputs
    assert gap.children_0_5 == sum(kids.get(c, 0) for c in d15.iso_cells)
    assert gap.licensed_seats == sum(f.licensed_capacity for f in fac if f.h3_r8 in d15.iso_cells)
    assert gap.gap_seats == gap.children_0_5 - gap.licensed_seats > 0


def test_decision_flags_gap_with_evidence(inputs: tuple[Any, ...]) -> None:
    d15, _, _, gap = inputs
    score, rec = gap_decision(gap, feature_rows(gap, d15, REL))
    assert rec.verdict == "recommend" and rec.evidence
    assert score.value == gap.gap_seats
    assert not any(e.feature_id.startswith("param_") for e in rec.evidence)


def test_decision_abstains_on_zip_centroid_heavy_supply(inputs: tuple[Any, ...]) -> None:
    d15, kids, _, _ = inputs
    zip_only = [FacilitySeat(c, 14, "zip_centroid") for c in sorted(d15.iso_cells)[:5]]
    gap = compute_gap(ORIGIN, 15, d15.iso_cells, kids, zip_only)
    _, rec = gap_decision(gap, feature_rows(gap, d15, REL))
    assert rec.verdict == "abstain" and rec.abstain_reason == "insufficient_coverage"


def test_decision_abstains_with_no_children(inputs: tuple[Any, ...]) -> None:
    d15, _, fac, _ = inputs
    gap = compute_gap(ORIGIN, 15, d15.iso_cells, {}, fac)
    score, rec = gap_decision(gap, feature_rows(gap, d15, REL))
    assert rec.verdict == "abstain" and rec.abstain_reason == "out_of_domain" and score.value is None


def test_memo_copy_rules(inputs: tuple[Any, ...]) -> None:
    d15, _, _, gap = inputs
    body = render_memo(gap, d15, REL)
    assert GAP_TERM in body.lower()
    assert FFN_DISCLAIMER in body and "family, friend and neighbor (FFN) care" in body
    assert not any(t in body.lower() for t in BANNED_TERMS)


def test_memo_passes_adr004_grounding(inputs: tuple[Any, ...]) -> None:
    d15, _, _, gap = inputs
    memo, findings = build_memo(gap, d15, REL, feature_rows(gap, d15, REL), ALLOWED, WHEN)
    assert findings == [] and memo.grounding_passed


def test_tampered_memo_fails_grounding(inputs: tuple[Any, ...]) -> None:
    d15, _, _, gap = inputs
    rows = feature_rows(gap, d15, REL)
    body = render_memo(gap, d15, REL).replace(f"{gap.licensed_seats:,}", f"{gap.licensed_seats + 250:,}")
    frows = [FeatureRow(r["feature_id"], Decimal(str(r["value"])), r["unit"], r["release_id"]) for r in rows]
    assert any(f.reason == "no deterministic feature row matches" for f in verify(body, frows, ALLOWED))


def test_committed_memo_fixture_is_current(inputs: tuple[Any, ...]) -> None:
    d15, _, _, gap = inputs
    assert (FX / "memos/p01_santa_clara_memo.md").read_text() == render_memo(gap, d15, REL)
    payload = json.loads((FX / "memos/p01_santa_clara_features.json").read_text())
    assert payload["rows"] == feature_rows(gap, d15, REL)
