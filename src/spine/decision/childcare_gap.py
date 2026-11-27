"""Product 01 scaffold: Santa Clara childcare licensed-capacity gap (Decision context).

For one origin cell and one drive-time contour:

    children_0_5  = sum of ACS children aged 0-5 in the catchment's member cells
    licensed_seats = sum of licensed capacity of LICENSED facilities in those cells
    gap_seats      = children_0_5 - licensed_seats   (positive = licensed-capacity gap)

This is a plain catchment ratio, not a two-step floating catchment (2SFCA) allocation, so
neighbouring catchments overlap and double count [D]. It measures licensed supply only:
informal family, friend and neighbour (FFN) care is invisible in CDSS data (G-101 Q5), which is
why outputs say "licensed-capacity gap" and never "childcare desert".
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from spine.compute.isochrone_diff import DiffResult
from spine.decision.models import Evidence, Recommendation, Score

METHOD_VER = "0.1.0"
# Abstain when more than half of the counted seats sit at ZIP centroids rather than rooftops:
# the cell-level supply is then too uncertain to call a gap [D, review threshold].
MAX_ZIP_CENTROID_SEAT_SHARE = 0.5
AGE_MIN, AGE_MAX = 0, 5


@dataclass(frozen=True)
class FacilitySeat:
    h3_r8: str
    licensed_capacity: int
    location_precision: str


@dataclass(frozen=True)
class GapResult:
    origin_h3_r8: str
    minutes: int
    children_0_5: int
    licensed_seats: int
    zip_centroid_seats: int

    @property
    def gap_seats(self) -> int:
        return self.children_0_5 - self.licensed_seats

    @property
    def seats_per_child(self) -> float:
        return self.licensed_seats / self.children_0_5 if self.children_0_5 else 0.0

    @property
    def zip_centroid_seat_share(self) -> float:
        return self.zip_centroid_seats / self.licensed_seats if self.licensed_seats else 0.0


def compute_gap(
    origin_h3_r8: str,
    minutes: int,
    member_cells: Iterable[str],
    children_by_cell: Mapping[str, int],
    facilities: Iterable[FacilitySeat],
) -> GapResult:
    cells = set(member_cells)
    inside = [f for f in facilities if f.h3_r8 in cells and f.location_precision != "suppressed"]
    return GapResult(
        origin_h3_r8=origin_h3_r8,
        minutes=minutes,
        children_0_5=sum(children_by_cell.get(c, 0) for c in cells),
        licensed_seats=sum(f.licensed_capacity for f in inside),
        zip_centroid_seats=sum(f.licensed_capacity for f in inside if f.location_precision == "zip_centroid"),
    )


@dataclass(frozen=True)
class P01Releases:
    acs: str
    cdss: str
    routing: str


def feature_rows(gap: GapResult, diff: DiffResult, rel: P01Releases) -> list[dict[str, Any]]:
    """Deterministic feature rows: the only numbers a P01 memo may state (ADR-004), including the
    kernel parameters (ADR-004 step 5)."""
    m = gap.minutes
    return [
        {
            "feature_id": f"children_0_5_within_{m}min",
            "value": gap.children_0_5,
            "unit": "",
            "release_id": rel.acs,
        },
        {
            "feature_id": f"licensed_seats_within_{m}min",
            "value": gap.licensed_seats,
            "unit": "",
            "release_id": rel.cdss,
        },
        {
            "feature_id": f"licensed_capacity_gap_seats_{m}min",
            "value": gap.gap_seats,
            "unit": "",
            "release_id": rel.cdss,
        },
        {
            "feature_id": f"seats_per_child_{m}min",
            "value": round(gap.seats_per_child, 6),
            "unit": "",
            "release_id": rel.cdss,
        },
        {
            "feature_id": f"radius_vs_isochrone_jaccard_{m}min",
            "value": round(diff.jaccard, 6),
            "unit": "",
            "release_id": rel.routing,
        },
        {
            "feature_id": f"radius_only_cells_{m}min",
            "value": diff.radius_only,
            "unit": "",
            "release_id": rel.routing,
        },
        {
            "feature_id": f"iso_only_cells_{m}min",
            "value": diff.iso_only,
            "unit": "",
            "release_id": rel.routing,
        },
        {"feature_id": "param_isochrone_min", "value": m, "unit": "", "release_id": rel.routing},
        {"feature_id": "param_radius_mi", "value": diff.radius_mi, "unit": "", "release_id": rel.routing},
        {"feature_id": "param_age_min", "value": AGE_MIN, "unit": "", "release_id": rel.acs},
        {"feature_id": "param_age_max", "value": AGE_MAX, "unit": "", "release_id": rel.acs},
    ]


def _evidence(rows: list[dict[str, Any]], table: str) -> tuple[Evidence, ...]:
    return tuple(
        Evidence(
            evidence_id=f"{table}:{r['feature_id']}",
            feature_table=table,
            feature_id=r["feature_id"],
            value=float(r["value"]),
            release_id=r["release_id"],
        )
        for r in rows
        if not r["feature_id"].startswith("param_")
    )


def gap_decision(
    gap: GapResult, rows: list[dict[str, Any]], table: str = "p01_gap"
) -> tuple[Score, Recommendation]:
    """Score the gap and decide whether to flag the catchment, with first-class abstention.

    verdict "recommend" = flag as a licensed-capacity gap for follow-up; "do_not_recommend" = no gap;
    "abstain" = too few children to say, or too much supply located only at ZIP centroids.
    """
    ev = _evidence(rows, table)
    subject = f"{gap.origin_h3_r8}:{gap.minutes}min"
    rid = f"p01:{subject}"
    if gap.children_0_5 == 0:
        rec = Recommendation(
            recommendation_id=rid,
            subject_id=subject,
            verdict="abstain",
            abstain_reason="out_of_domain",
            rationale_md="No children counted in catchment.",
            evidence=ev,
        )
        return Score(
            subject_id=subject, score_name="licensed_capacity_gap_seats", value=None, evidence=ev
        ), rec
    if gap.zip_centroid_seat_share > MAX_ZIP_CENTROID_SEAT_SHARE:
        rec = Recommendation(
            recommendation_id=rid,
            subject_id=subject,
            verdict="abstain",
            abstain_reason="insufficient_coverage",
            rationale_md="Most counted seats are located only at ZIP centroids.",
            evidence=ev,
        )
    elif gap.gap_seats > 0:
        rec = Recommendation(
            recommendation_id=rid,
            subject_id=subject,
            verdict="recommend",
            rationale_md="Licensed-capacity gap in this catchment.",
            evidence=ev,
        )
    else:
        rec = Recommendation(
            recommendation_id=rid,
            subject_id=subject,
            verdict="do_not_recommend",
            rationale_md="Licensed seats meet or exceed children counted.",
            evidence=ev,
        )
    score = Score(
        subject_id=subject, score_name="licensed_capacity_gap_seats", value=float(gap.gap_seats), evidence=ev
    )
    return score, rec
