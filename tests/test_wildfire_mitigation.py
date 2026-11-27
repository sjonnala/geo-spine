"""Kernel #3: the 10 CCR § 2644.9(d)(1) checklist, evidence resolution, documentation score, res-9 join."""

from __future__ import annotations

import json
from collections import Counter

import pytest

from spine.compute.wildfire_mitigation import (
    BLOCK_MAX,
    ITEMS_BY_ID,
    MITIGATIONS,
    SCORE_MAX,
    ExposureSample,
    OpenDataObservation,
    StructureExposure,
    aggregate_exposure,
    conflicting_items,
    documentation_score,
    exposure_context,
    join_exposure,
    resolve_evidence,
)
from support.p02 import BUTTE, gen

NO_DATA = OpenDataObservation()


def test_twelve_items_traceable_to_the_regulation() -> None:
    assert len(MITIGATIONS) == 12 and len(ITEMS_BY_ID) == 12
    assert Counter(m.block for m in MITIGATIONS) == {"community": 2, "surroundings": 5, "hardening": 5}
    assert all(m.subdivision == "(d)(1)(A)" for m in MITIGATIONS if m.block == "community")
    assert [m.subdivision for m in MITIGATIONS if m.block == "surroundings"] == [
        f"(d)(1)(B)1.{c}" for c in "abcde"
    ]
    assert [m.subdivision for m in MITIGATIONS if m.block == "hardening"] == [
        f"(d)(1)(B)2.{c}" for c in "abcde"
    ]
    reg = json.loads((BUTTE / "ccr_2644_9_d1_items.json").read_text())["items"]
    assert [(i["item_id"], i["subdivision"], i["text"]) for i in reg] == [
        (m.item_id, m.subdivision, m.regulation_text) for m in MITIGATIONS
    ]
    assert "Class-A Fire Rated Roof" in ITEMS_BY_ID["harden_class_a_roof"].regulation_text


def test_points_add_up_to_100() -> None:
    assert sum(m.points for m in MITIGATIONS) == SCORE_MAX == sum(BLOCK_MAX.values())


def test_score_extremes_and_a_hand_computed_mix() -> None:
    none = documentation_score(resolve_evidence({}, NO_DATA))
    assert none.total == 0.0 and none.items_with_evidence == 0
    photos = documentation_score(
        resolve_evidence(dict.fromkeys(ITEMS_BY_ID, "owner_attested_with_photo"), NO_DATA)
    )
    assert photos.total == 80.0  # 100 x 0.8
    obs = OpenDataObservation(naip_veg_0_5ft_pct=6.0, firewise_listed=True, frrc_listed=True)
    best = documentation_score(resolve_evidence(dict.fromkeys(ITEMS_BY_ID, "owner_attested_with_photo"), obs))
    assert (best.community, best.surroundings, best.hardening) == (20.0, 33.6, 32.0)  # 2x10, 8+4x6.4, 5x6.4
    assert best.total == 85.6
    mix = documentation_score(
        resolve_evidence(
            {"harden_class_a_roof": "owner_attested", "surround_under_deck": "owner_attested"}, NO_DATA
        )
    )
    assert (mix.surroundings, mix.hardening, mix.total) == (4.0, 4.0, 8.0)


def test_owner_cannot_claim_open_data_or_unknown_items() -> None:
    with pytest.raises(ValueError, match="invalid owner evidence"):
        resolve_evidence({"harden_vents": "open_data_observed"}, NO_DATA)
    with pytest.raises(ValueError, match="not a 10 CCR"):
        resolve_evidence({"zone_0_ember_resistant": "owner_attested"}, NO_DATA)
    with pytest.raises(ValueError, match="evidence missing"):
        documentation_score({"harden_vents": "unknown"})


@pytest.mark.parametrize(
    ("veg", "kind"), [(10.0, "open_data_observed"), (10.1, "unknown"), (None, "unknown")]
)
def test_clear_ring_is_open_data_evidence(veg: float | None, kind: str) -> None:
    assert resolve_evidence({}, OpenDataObservation(naip_veg_0_5ft_pct=veg))["surround_5ft"] == kind


def test_community_lists_upgrade_evidence() -> None:
    ev = resolve_evidence({"community_frrc": "owner_attested"}, OpenDataObservation(firewise_listed=True))
    assert ev["community_firewise"] == "open_data_observed" and ev["community_frrc"] == "owner_attested"


def test_conflicts() -> None:
    attested = {"surround_5ft": "owner_attested_with_photo", "community_firewise": "owner_attested"}
    assert conflicting_items(attested, OpenDataObservation(naip_veg_0_5ft_pct=25.0)) == ("surround_5ft",)
    assert conflicting_items(attested, OpenDataObservation(naip_veg_0_5ft_pct=24.9)) == ()
    assert conflicting_items(attested, OpenDataObservation(firewise_listed=False)) == ("community_firewise",)
    assert conflicting_items(attested, NO_DATA) == ()  # no data is not a contradiction
    assert conflicting_items({}, OpenDataObservation(naip_veg_0_5ft_pct=90.0, firewise_listed=False)) == ()


def test_exposure_aggregates_per_cell_and_joins() -> None:
    grid = gen().fake_grid
    samples = [
        ExposureSample(39.7596, -121.6219, 22.0, 9.0),
        ExposureSample(39.7596, -121.6219, 26.0, 11.0),
        ExposureSample(39.8196, -121.5619, 90.0, 40.0),
    ]
    cells = aggregate_exposure(samples, grid)
    assert sorted(c.samples for c in cells.values()) == [1, 2]
    joined = join_exposure([("a", 39.7596, -121.6219), ("b", 39.7, -121.7)], cells, grid)
    a = joined["a"]
    assert a is not None and (a.canopy_cover_pct, a.slope_deg, a.samples) == (24.0, 10.0, 2)
    assert joined["b"] is None


@pytest.mark.parametrize(
    ("canopy", "slope", "tier"),
    [
        (24.9, 14.9, "lower"),
        (25.0, 0.0, "elevated"),
        (0.0, 15.0, "elevated"),
        (50.0, 0.0, "high"),
        (0.0, 30.0, "high"),
    ],
)
def test_exposure_context_tiers(canopy: float, slope: float, tier: str) -> None:
    assert exposure_context(StructureExposure("s", "x", canopy, slope, 1)) == tier


def test_real_h3_res9_join() -> None:
    h3 = pytest.importorskip("h3")
    from spine.compute.wildfire_mitigation import h3_r9

    cell = h3_r9(39.7596, -121.6219)
    assert h3.get_resolution(cell) == 9
    cells = aggregate_exposure([ExposureSample(39.7596, -121.6219, 30.0, 12.0)])
    assert list(cells) == [cell]
    assert join_exposure([("s", 39.7596, -121.6219)], cells)["s"] is not None
