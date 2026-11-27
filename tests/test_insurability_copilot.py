"""Product 02 decision: the five-reason abstention gate, zero-PII intake, deadlines, appeal packet."""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import Any

import pytest
from license_guard import PII_COLS

from spine.compute.wildfire_mitigation import ITEMS_BY_ID, MITIGATIONS, StructureExposure
from spine.decision.insurability_copilot import (
    STRUCTURE_FIELDS,
    USER_SUPPLIED,
    AppealPacket,
    ChecklistRow,
    CommunityLists,
    Deadline,
    P02Assessment,
    Subject,
    UserDates,
    assess,
    build_appeal_packet,
    compute_deadlines,
    subject_from_record,
)
from support.p02 import assessments, catalog, gen

AS_OF = date(2026, 11, 27)
LISTS = CommunityLists(firewise=frozenset({"SYN-COMM-RIDGE"}), frrc=frozenset())
EXPO = StructureExposure("SYN_T", "cell", 20.0, 8.0, 2)
FULL = {k: "owner_attested_with_photo" for k in ITEMS_BY_ID if k != "community_frrc"}  # not on the FRRC list


def S(**kw: Any) -> Subject:
    rel = gen().REL
    base: dict[str, Any] = dict(
        structure_id="SYN_T",
        state="CA",
        county_fips="06007",
        community_id="SYN-COMM-RIDGE",
        structure_kind="single_family",
        lat=39.75,
        lon=-121.6,
        footprint_matched=True,
        naip_veg_0_5ft_pct=6.0,
        imagery_release_id=rel.imagery,
        imagery_vintage=date(2024, 6, 1),
        hazard_release_id=rel.canopy,
        hazard_vintage=date(2024, 1, 1),
        attested_evidence=FULL,
    )
    base.update(kw)
    return Subject(**base)


def run(s: Subject, exposure: StructureExposure | None = EXPO, commercial: bool = False) -> P02Assessment:
    return assess(s, LISTS, exposure, catalog(), gen().REL, as_of=AS_OF, commercial=commercial)


# --- the G-103 reference tests (insurability_rules.py, 7/7), ported -----------------------------------
def test_ok() -> None:
    a = run(S())
    assert not a.gate.abstain and a.recommendation.verdict == "recommend" and a.ready_to_appeal


def test_out_of_state() -> None:
    assert run(S(state="WA")).gate.primary == "out_of_domain"


def test_commercial_structure() -> None:
    assert run(S(structure_kind="commercial")).gate.primary == "out_of_domain"


def test_no_footprint() -> None:
    assert run(S(footprint_matched=False)).gate.primary == "insufficient_coverage"


def test_stale_imagery() -> None:
    assert run(S(imagery_vintage=date(2022, 6, 1))).gate.primary == "stale_release"


def test_too_few_known() -> None:
    a = run(
        S(
            attested_evidence={"harden_class_a_roof": "owner_attested"},
            community_id=None,
            naip_veg_0_5ft_pct=40.0,
        )
    )
    assert a.gate.reasons == ("insufficient_coverage",)


def test_twelve_items() -> None:
    assert len(MITIGATIONS) == 12 and len(run(S(state="WA")).checklist) == 12


# --- the other reasons and edges -------------------------------------------------------------------------
def test_stale_hazard_layer() -> None:
    assert run(S(hazard_vintage=date(2021, 1, 1))).gate.primary == "stale_release"


def test_no_exposure_join_is_insufficient_coverage() -> None:
    assert run(S(), exposure=None).gate.primary == "insufficient_coverage"


def test_conflicting_evidence() -> None:
    a = run(S(naip_veg_0_5ft_pct=32.0))
    assert a.gate.reasons == ("conflicting_evidence",)
    assert "32.0%" in a.gate.findings[0].detail


def test_license_blocked_non_commercial_input() -> None:
    a = run(S(hazard_release_id="fixture_nc_wildfire_model_butte_2026-01"))
    assert a.gate.primary == "license_blocked"


def test_license_blocked_restricted_input_in_commercial_use() -> None:
    assert not run(S()).gate.abstain
    assert run(S(), commercial=True).gate.primary == "license_blocked"  # community lists are restricted [U]


def test_license_blocked_unknown_release() -> None:
    assert run(S(imagery_release_id="naip_ghost_2026")).gate.primary == "license_blocked"


def test_all_reasons_reported_primary_first() -> None:
    a = run(S(state="WA", footprint_matched=False, imagery_vintage=date(2020, 1, 1)))
    assert a.gate.reasons == ("out_of_domain", "insufficient_coverage", "stale_release")
    assert a.recommendation.abstain_reason == "out_of_domain"


def test_abstaining_withholds_score_and_ready_but_keeps_checklist() -> None:
    a = run(S(structure_kind="mobile_home"))
    assert a.score is None and a.documentation_score.value is None and not a.ready_to_appeal
    assert len(a.checklist) == 12 and a.recommendation.verdict == "abstain"
    assert a.recommendation.rationale_md.startswith("We can't score this home yet: this is a mobile home")


def test_thin_documentation_is_scored_but_not_ready() -> None:
    six = {k: "owner_attested" for k in list(ITEMS_BY_ID)[2:8]}
    a = run(S(attested_evidence=six, community_id=None, naip_veg_0_5ft_pct=18.0))
    assert a.score is not None and a.score.total == 24.0
    assert a.recommendation.verdict == "do_not_recommend" and not a.ready_to_appeal


def test_evidence_rows_name_their_source() -> None:
    a = run(S())
    src = {e.feature_id.split(":")[1]: e.release_id for e in a.recommendation.evidence}
    rel = gen().REL
    assert src["surround_5ft"] == rel.imagery and src["community_firewise"] == rel.community_lists
    assert src["harden_vents"] == USER_SUPPLIED
    assert {e.value for e in a.recommendation.evidence} <= {1.0, 0.8, 0.5}


def test_fixture_verdicts() -> None:
    got = {sid: (a.recommendation.verdict, a.gate.reasons) for sid, a in assessments().items()}
    assert got == {
        "SYN_BUTTE_0001": ("recommend", ()),
        "SYN_BUTTE_0002": ("do_not_recommend", ()),
        "SYN_BUTTE_0003": ("abstain", ("out_of_domain",)),
        "SYN_BUTTE_0004": ("abstain", ("stale_release",)),
        "SYN_BUTTE_0005": ("abstain", ("conflicting_evidence",)),
        "SYN_BUTTE_0006": ("abstain", ("insufficient_coverage",)),
        "SYN_BUTTE_0007": ("abstain", ("license_blocked",)),
    }
    assert assessments()["SYN_BUTTE_0001"].score is not None
    assert assessments()["SYN_BUTTE_0001"].score.total == 62.0  # type: ignore[union-attr]


# --- zero PII ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("field", ["owner_name", "taxpayer", "occupant", "apn", "phone", "email", "address"])
def test_intake_allow_list_rejects_person_level_fields(field: str) -> None:
    rec = gen().intake()["structures"][0] | {"footprint_matched": True, "naip_veg_0_5ft_pct": 6.0, field: "x"}
    with pytest.raises(ValueError, match="allow-list"):
        subject_from_record(rec)


def test_unknown_structure_kind_rejected() -> None:
    rec = gen().intake()["structures"][0] | {"footprint_matched": True, "structure_kind": "castle"}
    with pytest.raises(ValueError, match="structure_kind"):
        subject_from_record(rec)


def test_no_entity_field_looks_like_person_data() -> None:
    names = set(STRUCTURE_FIELDS)
    for cls in (Subject, P02Assessment, ChecklistRow, Deadline, AppealPacket):
        names |= {f.name for f in dataclasses.fields(cls)}
    assert [n for n in sorted(names) if PII_COLS.search(n)] == []


# --- deadlines and the appeal packet -------------------------------------------------------------------
def test_deadlines_from_entered_dates() -> None:
    d = UserDates(
        application_completed=date(2027, 1, 4),
        renewal=date(2027, 3, 1),
        nonrenewal_effective=date(2027, 3, 1),
        revised_score_requested=date(2027, 2, 1),
        appeal_received=date(2027, 2, 10),
    )
    got = {x.key: (x.rule, x.due) for x in compute_deadlines(d)}
    assert got == {
        "score_after_application": ("(h)", date(2027, 1, 19)),
        "score_before_renewal": ("(h)", date(2027, 1, 15)),
        "score_before_nonrenewal": ("(h)", date(2026, 12, 16)),
        "revised_score": ("(h)(4)", date(2027, 3, 3)),
        "appeal_acknowledgement": ("(i)", date(2027, 2, 20)),
        "appeal_decision": ("(i)", date(2027, 3, 12)),
    }
    dues = [x.due for x in compute_deadlines(d)]
    assert dues == sorted(dues)
    assert compute_deadlines(UserDates()) == ()


def test_appeal_packet() -> None:
    a = assessments()["SYN_BUTTE_0001"]
    p = build_appeal_packet(a, UserDates(appeal_received=date(2027, 2, 10)))
    assert p.ready and len(p.documented) == 10 and len(p.needing_evidence) == 2
    assert [x.key for x in p.deadlines] == ["appeal_acknowledgement", "appeal_decision"]
    assert len(p.explanation_checklist) == 5 and "hotline" in p.escalation
    blocked = build_appeal_packet(assessments()["SYN_BUTTE_0005"])
    assert not blocked.ready
