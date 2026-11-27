"""Product 01: Santa Clara childcare licensed-capacity gap, 2SFCA edition (Decision context).

G-301 retires the PR #1 catchment ratio from Product 01 output. For each H3 res-8 cell ``i``:

    children_0_5        = P_i, ACS children aged 0-5 in the cell
    seats_per_child     = A_i from Kernel #2 (spine.compute.two_sfca), d0 = 15 drive minutes
    allocated_seats     = P_i * A_i
    gap_seats           = P_i - allocated_seats   (positive = licensed-capacity gap)

Every licensed seat is shared among all populated cells that can reach it, so summed over cells
the allocated seats equal the licensed seats of non-orphan facilities (no double counting). The
old per-origin ratio survives only as a diagnostic (``double_count_factor_simple_ratio``).

It measures licensed supply only: informal family, friend and neighbour (FFN) care is invisible
in CDSS data (G-101 Q5), which is why outputs say "licensed-capacity gap" and never "desert".
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from spine.compute.isochrone_diff import DiffResult
from spine.compute.two_sfca import (
    DEFAULT_D0_MIN,
    TravelTable,
    TwoSFCAResult,
    simple_ratio_seat_count,
    two_sfca,
)
from spine.decision.models import AbstainReason, Evidence, Recommendation, Score, Verdict

METHOD_VER = "0.2.0"
# Abstain when more than half of the seats in reach sit at ZIP centroids rather than rooftops:
# the cell-level supply is then too uncertain to call a gap [D, review threshold].
MAX_ZIP_CENTROID_SEAT_SHARE = 0.5
AGE_MIN, AGE_MAX = 0, 5
D0_MIN = int(DEFAULT_D0_MIN)


@dataclass(frozen=True)
class FacilitySeat:
    facility_id: str
    h3_r8: str
    licensed_capacity: int
    location_precision: str


@dataclass(frozen=True)
class CellGap:
    h3_r8: str
    minutes: int
    children_0_5: int
    seats_per_child: float  # A_i
    allocated_seats: float  # P_i * A_i
    facilities_in_reach: int
    raw_seats_in_reach: int
    zip_centroid_seats_in_reach: int

    @property
    def gap_seats(self) -> float:
        return self.children_0_5 - self.allocated_seats

    @property
    def surplus(self) -> bool:
        return self.seats_per_child > 1.0

    @property
    def zip_centroid_seat_share(self) -> float:
        return self.zip_centroid_seats_in_reach / self.raw_seats_in_reach if self.raw_seats_in_reach else 0.0


@dataclass(frozen=True)
class RegionAllocation:
    minutes: int
    result: TwoSFCAResult
    cells: dict[str, CellGap]
    total_seats: int  # licensed seats of non-suppressed facilities
    orphan_seats: int
    simple_ratio_seats_counted: int

    @property
    def allocatable_seats(self) -> int:
        return self.total_seats - self.orphan_seats

    @property
    def double_count_factor(self) -> float:
        return self.simple_ratio_seats_counted / self.total_seats if self.total_seats else 0.0


def allocate_region(
    children_by_cell: Mapping[str, int],
    facilities: Iterable[FacilitySeat],
    travel_min: TravelTable,
    minutes: int = D0_MIN,
) -> RegionAllocation:
    """Run 2SFCA over every populated cell and every non-suppressed licensed facility."""
    usable = [f for f in facilities if f.location_precision != "suppressed"]
    by_id = {f.facility_id: f for f in usable}
    if len(by_id) != len(usable):
        raise ValueError("facility_id must be unique")
    supply = {f.facility_id: f.licensed_capacity for f in usable}
    res = two_sfca(supply, children_by_cell, travel_min, float(minutes))
    reach: dict[str, list[str]] = {c: [] for c in children_by_cell}
    for (i, j), t in travel_min.items():
        if t <= minutes and i in reach and j in by_id:
            reach[i].append(j)
    cells = {
        c: CellGap(
            h3_r8=c,
            minutes=minutes,
            children_0_5=p,
            seats_per_child=res.access_by_cell[c],
            allocated_seats=res.allocated_by_cell[c],
            facilities_in_reach=len(reach[c]),
            raw_seats_in_reach=sum(by_id[j].licensed_capacity for j in reach[c]),
            zip_centroid_seats_in_reach=sum(
                by_id[j].licensed_capacity for j in reach[c] if by_id[j].location_precision == "zip_centroid"
            ),
        )
        for c, p in children_by_cell.items()
    }
    return RegionAllocation(
        minutes=minutes,
        result=res,
        cells=cells,
        total_seats=sum(supply.values()),
        orphan_seats=sum(supply[j] for j in res.orphan_facilities),
        simple_ratio_seats_counted=simple_ratio_seat_count(supply, children_by_cell, travel_min, minutes),
    )


def seats_conserved(region: RegionAllocation, tol: float = 1e-9) -> bool:
    """Total allocated seats == licensed seats of non-orphan facilities (G-103 G1.1)."""
    return math.isclose(region.result.total_allocated, region.allocatable_seats, rel_tol=0, abs_tol=tol)


@dataclass(frozen=True)
class P01Releases:
    acs: str
    cdss: str
    routing: str  # Kernel #1 isochrone recording
    matrix: str  # origin-destination matrix recording used by 2SFCA


def feature_rows(
    cell: CellGap, region: RegionAllocation, diff: DiffResult, rel: P01Releases
) -> list[dict[str, Any]]:
    """Deterministic feature rows: the only numbers a P01 memo may state (ADR-004), including the
    kernel parameters (ADR-004 step 5). Ratios keep 6 decimals; the memo prints 4 (G-103 fix)."""
    m = cell.minutes

    def row(fid: str, value: float | int, release: str) -> dict[str, Any]:
        return {"feature_id": fid, "value": value, "unit": "", "release_id": release}

    return [
        row("children_0_5_cell", cell.children_0_5, rel.acs),
        row("seats_per_child_2sfca", round(cell.seats_per_child, 6), rel.cdss),
        row("allocated_seats_2sfca", round(cell.allocated_seats, 2), rel.cdss),
        row("licensed_capacity_gap_2sfca", round(cell.gap_seats, 2), rel.cdss),
        row(f"facilities_in_reach_{m}min", cell.facilities_in_reach, rel.matrix),
        row(f"raw_seats_in_reach_{m}min", cell.raw_seats_in_reach, rel.cdss),
        row("region_total_seats", region.total_seats, rel.cdss),
        row("region_seats_counted_simple_ratio", region.simple_ratio_seats_counted, rel.cdss),
        row("double_count_factor_simple_ratio", round(region.double_count_factor, 2), rel.cdss),
        row(f"radius_vs_isochrone_jaccard_{diff.minutes}min", round(diff.jaccard, 6), rel.routing),
        row(f"radius_only_cells_{diff.minutes}min", diff.radius_only, rel.routing),
        row(f"iso_only_cells_{diff.minutes}min", diff.iso_only, rel.routing),
        row("param_isochrone_min", m, rel.matrix),
        row("param_radius_mi", diff.radius_mi, rel.routing),
        row("param_age_min", AGE_MIN, rel.acs),
        row("param_age_max", AGE_MAX, rel.acs),
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


_RATIONALE: dict[tuple[Verdict, AbstainReason | None], str] = {
    ("abstain", "out_of_domain"): "No children counted in this cell.",
    ("abstain", "insufficient_coverage"): "Most licensed seats in reach are located only at ZIP centroids.",
    ("recommend", None): "Licensed-capacity gap after sharing every reachable seat (2SFCA).",
    ("do_not_recommend", None): "Allocated licensed seats meet or exceed children counted (surplus).",
}


def cell_verdict(cell: CellGap) -> tuple[Verdict, AbstainReason | None]:
    """First-class abstention, then the gap call. Shared by the memo decision and the map tiles."""
    if cell.children_0_5 == 0:
        return "abstain", "out_of_domain"
    if cell.zip_centroid_seat_share > MAX_ZIP_CENTROID_SEAT_SHARE:
        return "abstain", "insufficient_coverage"
    return ("recommend", None) if cell.gap_seats > 0 else ("do_not_recommend", None)


def gap_decision(
    cell: CellGap, rows: list[dict[str, Any]], table: str = "p01_gap_2sfca"
) -> tuple[Score, Recommendation]:
    """verdict "recommend" = flag as a licensed-capacity gap for follow-up; "do_not_recommend" =
    surplus; "abstain" = no children, or too much supply in reach located only at ZIP centroids."""
    ev = _evidence(rows, table)
    subject = f"{cell.h3_r8}:{cell.minutes}min"
    verdict, reason = cell_verdict(cell)
    rec = Recommendation(
        recommendation_id=f"p01:{subject}",
        subject_id=subject,
        verdict=verdict,
        abstain_reason=reason,
        rationale_md=_RATIONALE[(verdict, reason)],
        evidence=ev,
    )
    value = None if reason == "out_of_domain" else round(cell.gap_seats, 2)
    return Score(subject_id=subject, score_name="licensed_capacity_gap_2sfca", value=value, evidence=ev), rec
