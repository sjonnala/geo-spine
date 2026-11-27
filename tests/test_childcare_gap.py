"""Product 01 on 2SFCA: Santa Clara licensed-capacity gap, decision and ADR-004-checked memo.

The OD matrix comes from the SYNTHETIC replay cassette through ValhallaClient(mode="replay"), so
these tests also prove the cassette still matches the request the fixtures produce."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import h3
import pytest

from conftest import CASSETTES, FIXTURE_RELEASES, FX, ORIGIN, WEB, load_p01_region_inputs
from spine.catalog.models import LicenseClass, Provenance
from spine.compute.isochrone_diff import isochrone_diff, parse_valhalla_isochrone
from spine.compute.valhalla_client import ValhallaClient, matrix_request, parse_matrix_minutes
from spine.decision.childcare_gap import (
    CellGap,
    FacilitySeat,
    P01Releases,
    allocate_region,
    cell_verdict,
    feature_rows,
    gap_decision,
    seats_conserved,
)
from spine.decision.grounding_verifier import FeatureRow, verify
from spine.identity.facilities import curate_cdss_rows, facility_columns, read_cdss_csv
from spine.surface.p01_memo import BANNED_TERMS, FFN_DISCLAIMER, GAP_TERM, build_memo, render_memo
from spine.surface.p01_tiles import cells_feature_collection

REL = P01Releases(**FIXTURE_RELEASES)
ALLOWED = set(FIXTURE_RELEASES.values())
WHEN = datetime(2026, 11, 27, tzinfo=UTC)


@pytest.fixture(scope="module")
def p01(iso_payload: dict[str, Any]) -> tuple[Any, ...]:
    d15 = next(
        d for d in isochrone_diff(ORIGIN, parse_valhalla_isochrone(iso_payload), 2.0) if d.minutes == 15
    )
    kids, seats, coords, cells = load_p01_region_inputs()
    body = matrix_request([h3.cell_to_latlng(c) for c in cells], coords)
    payload = ValhallaClient(mode="replay", cassette_dir=CASSETTES).matrix(body)
    travel = parse_matrix_minutes(payload, cells, [s.facility_id for s in seats])
    region = allocate_region(kids, seats, travel)
    return d15, kids, seats, travel, region


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


# --- G-103 G1.1: exact seat conservation on the Santa Clara fixtures ---
def test_seats_conserved_across_cells(p01: tuple[Any, ...]) -> None:
    _, _, seats, _, region = p01
    assert region.total_seats == sum(s.licensed_capacity for s in seats)
    assert region.result.total_allocated == pytest.approx(region.allocatable_seats, rel=0, abs=1e-9)
    assert seats_conserved(region)


def test_fixture_region_has_no_orphans_and_real_variation(p01: tuple[Any, ...]) -> None:
    _, _, _, _, region = p01
    assert region.result.orphan_facilities == () and region.orphan_seats == 0
    access = [c.seats_per_child for c in region.cells.values()]
    assert min(access) < max(access)  # the barrier and distance make access uneven


def test_orphan_facility_excluded_and_conservation_holds(p01: tuple[Any, ...]) -> None:
    _, kids, seats, travel, _ = p01
    island = FacilitySeat("SYN-ISLAND", "8828347029fffff", 77, "rooftop")  # no OD rows reach it
    region = allocate_region(kids, [*seats, island], travel)
    assert region.result.orphan_facilities == ("SYN-ISLAND",) and region.orphan_seats == 77
    assert seats_conserved(region)
    assert region.result.total_allocated == pytest.approx(region.total_seats - 77, abs=1e-9)


def test_suppressed_facilities_are_not_allocated(p01: tuple[Any, ...]) -> None:
    _, kids, seats, travel, region = p01
    hidden = FacilitySeat(seats[0].facility_id + "-S", seats[0].h3_r8, 50, "suppressed")
    again = allocate_region(kids, [*seats, hidden], travel)
    assert again.total_seats == region.total_seats and seats_conserved(again)


def test_duplicate_facility_ids_rejected(p01: tuple[Any, ...]) -> None:
    _, kids, seats, travel, _ = p01
    with pytest.raises(ValueError, match="unique"):
        allocate_region(kids, [*seats, seats[0]], travel)


# --- G-103 G1.2: the old ratio double counts, so it is retired from P01 output ---
def test_simple_ratio_double_counts_on_fixtures(p01: tuple[Any, ...]) -> None:
    _, _, _, _, region = p01
    assert region.simple_ratio_seats_counted > region.total_seats
    assert region.double_count_factor > 1


def test_p01_output_reads_2sfca_not_the_old_ratio(p01: tuple[Any, ...]) -> None:
    d15, _, _, _, region = p01
    ids = {r["feature_id"] for r in feature_rows(region.cells[ORIGIN], region, d15, REL)}
    assert {"seats_per_child_2sfca", "licensed_capacity_gap_2sfca", "allocated_seats_2sfca"} <= ids
    assert not any(i.startswith(("licensed_seats_within", "seats_per_child_15min")) for i in ids)


def test_cell_gap_arithmetic(p01: tuple[Any, ...]) -> None:
    _, kids, _, _, region = p01
    cell = region.cells[ORIGIN]
    assert cell.children_0_5 == kids[ORIGIN]
    assert cell.allocated_seats == pytest.approx(cell.children_0_5 * cell.seats_per_child)
    assert cell.gap_seats == pytest.approx(cell.children_0_5 - cell.allocated_seats)
    assert 0 < cell.raw_seats_in_reach <= region.total_seats


def test_decision_flags_gap_with_evidence(p01: tuple[Any, ...]) -> None:
    d15, _, _, _, region = p01
    cell = region.cells[ORIGIN]
    score, rec = gap_decision(cell, feature_rows(cell, region, d15, REL))
    assert rec.verdict == "recommend" and rec.evidence
    assert score.value == round(cell.gap_seats, 2)
    assert not any(e.feature_id.startswith("param_") for e in rec.evidence)


def _cell(**kw: Any) -> CellGap:
    base: dict[str, Any] = dict(
        h3_r8=ORIGIN,
        minutes=15,
        children_0_5=100,
        seats_per_child=0.2,
        allocated_seats=20.0,
        facilities_in_reach=3,
        raw_seats_in_reach=100,
        zip_centroid_seats_in_reach=10,
    )
    base.update(kw)
    return CellGap(**base)


def test_verdicts() -> None:
    assert cell_verdict(_cell()) == ("recommend", None)
    assert cell_verdict(_cell(children_0_5=0, allocated_seats=0.0)) == ("abstain", "out_of_domain")
    assert cell_verdict(_cell(zip_centroid_seats_in_reach=60)) == ("abstain", "insufficient_coverage")
    surplus = _cell(seats_per_child=1.5, allocated_seats=150.0)
    assert surplus.surplus and cell_verdict(surplus) == ("do_not_recommend", None)


def test_decision_abstains_with_no_children(p01: tuple[Any, ...]) -> None:
    d15, _, _, _, region = p01
    cell = _cell(children_0_5=0, allocated_seats=0.0, seats_per_child=0.0)
    score, rec = gap_decision(cell, feature_rows(cell, region, d15, REL))
    assert rec.verdict == "abstain" and rec.abstain_reason == "out_of_domain" and score.value is None


def test_memo_copy_rules(p01: tuple[Any, ...]) -> None:
    d15, _, _, _, region = p01
    body = render_memo(region.cells[ORIGIN], region, d15, REL)
    assert GAP_TERM in body.lower() and "2SFCA" in body
    assert FFN_DISCLAIMER in body and "family, friend and neighbor (FFN) care" in body
    assert not any(t in body.lower() for t in BANNED_TERMS)


def test_surplus_memo_says_surplus(p01: tuple[Any, ...]) -> None:
    d15, _, _, _, region = p01
    cell = _cell(seats_per_child=1.5, allocated_seats=150.0)
    body = render_memo(cell, region, d15, REL)
    assert "surplus of 50.00 licensed seats" in body and f"no {GAP_TERM}" in body


def test_memo_passes_adr004_grounding(p01: tuple[Any, ...]) -> None:
    d15, _, _, _, region = p01
    cell = region.cells[ORIGIN]
    memo, findings = build_memo(cell, region, d15, REL, feature_rows(cell, region, d15, REL), ALLOWED, WHEN)
    assert findings == [] and memo.grounding_passed
    assert REL.matrix in memo.cited_releases


def test_memo_ratio_printed_with_4_decimals(p01: tuple[Any, ...]) -> None:
    d15, _, _, _, region = p01
    cell = region.cells[ORIGIN]
    assert f"{cell.seats_per_child:.4f}" in render_memo(cell, region, d15, REL)


def test_tampered_memo_fails_grounding(p01: tuple[Any, ...]) -> None:
    d15, _, _, _, region = p01
    cell = region.cells[ORIGIN]
    rows = feature_rows(cell, region, d15, REL)
    body = render_memo(cell, region, d15, REL).replace(
        f"{cell.gap_seats:,.2f}", f"{cell.gap_seats + 250:,.2f}"
    )
    frows = [FeatureRow(r["feature_id"], Decimal(str(r["value"])), r["unit"], r["release_id"]) for r in rows]
    assert any(f.reason == "no deterministic feature row matches" for f in verify(body, frows, ALLOWED))


def test_committed_memo_fixture_is_current(p01: tuple[Any, ...]) -> None:
    d15, _, _, _, region = p01
    cell = region.cells[ORIGIN]
    assert (FX / "memos/p01_santa_clara_memo.md").read_text() == render_memo(cell, region, d15, REL)
    payload = json.loads((FX / "memos/p01_santa_clara_features.json").read_text())
    assert payload["rows"] == feature_rows(cell, region, d15, REL)
    assert set(payload["allowed_releases"]) == ALLOWED


def test_committed_viewer_export_is_current(p01: tuple[Any, ...]) -> None:
    _, _, seats, _, region = p01
    fc = cells_feature_collection(region, sorted(ALLOWED), "fixture-g301")
    assert json.loads((WEB / "data/cells.geojson").read_text()) == json.loads(json.dumps(fc))
    centers = json.loads((WEB / "data/centers.geojson").read_text())["features"]
    rooftop_centers = [s for s in seats if s.location_precision == "rooftop"]
    assert len(centers) == len(rooftop_centers)  # every rooftop center, no family child care homes
