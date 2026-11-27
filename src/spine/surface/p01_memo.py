"""Product 01 memo (Surface context): template-rendered, then gated by ADR-004.

No LLM here: the "AI plane" slot is a deterministic template for the scaffold. Whatever writes
the prose later, `grounding_passed` comes only from the verifier.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from spine.compute.isochrone_diff import DiffResult
from spine.decision.childcare_gap import AGE_MAX, AGE_MIN, CellGap, P01Releases, RegionAllocation
from spine.decision.grounding_verifier import FeatureRow, Finding, verify
from spine.surface.models import Memo

MODEL_ID = "template:p01_memo@0.2.0"
GAP_TERM = "licensed-capacity gap"
# Required on every Product 01 surface (G-101 Q5). No digits or number words, so it never trips
# the grounding verifier.
FFN_DISCLAIMER = (
    "**Licensed seats only.** These figures count licensed child care centers and family child care "
    "homes. Informal family, friend and neighbor (FFN) care, which California exempts from licensing, "
    "is not counted, so a licensed-capacity gap compares licensed supply with children; it does not "
    "show whether families have care. Family child care homes are placed at ZIP centroids to protect "
    "home addresses."
)
SYNTHETIC_BANNER = "_Synthetic fixture data for CI. These are not real Santa Clara figures._"
BANNED_TERMS = ("desert",)


def render_memo(cell: CellGap, region: RegionAllocation, diff: DiffResult, rel: P01Releases) -> str:
    """2SFCA memo. Ratios print with 4 decimals so ordinary rounding stays inside the verifier's
    0.5% tolerance (G-103 finding 1); no statute numbers in prose (G-103 finding 2)."""
    m = cell.minutes
    a, c, r, x = rel.acs, rel.cdss, rel.routing, rel.matrix
    if cell.gap_seats > 0:
        gap_line = (
            f"- Seats allocated to this cell: {cell.allocated_seats:,.2f}, leaving a {GAP_TERM} of "
            f"{cell.gap_seats:,.2f} children [src:{c}] [src:{a}]"
        )
    else:
        gap_line = (
            f"- Seats allocated to this cell: {cell.allocated_seats:,.2f}, a surplus of "
            f"{-cell.gap_seats:,.2f} licensed seats over children counted, so no {GAP_TERM} "
            f"[src:{c}] [src:{a}]"
        )
    radius = f"{diff.radius_mi:g}"
    lines = [
        f"# Santa Clara {GAP_TERM}, 2SFCA: cell {cell.h3_r8}",
        "",
        SYNTHETIC_BANNER,
        "",
        f"- Children aged {AGE_MIN} to {AGE_MAX} in this cell: {cell.children_0_5:,} [src:{a}]",
        f"- Licensed seats available per child after 2SFCA allocation: {cell.seats_per_child:.4f} "
        f"[src:{c}] [src:{x}]",
        gap_line,
        f"- Facilities reachable within a {m}-minute drive: {cell.facilities_in_reach:,}, holding "
        f"{cell.raw_seats_in_reach:,} licensed seats that this cell shares with every other cell in their "
        f"reach [src:{x}] [src:{c}]",
        f"- Why 2SFCA: the fixture region has {region.total_seats:,} licensed seats, but a simple per-origin "
        f"catchment ratio counts {region.simple_ratio_seats_counted:,}, about "
        f"{region.double_count_factor:.2f} times the real supply [src:{c}]",
        f"- A {radius}-mile radius and the {diff.minutes}-minute drive-time area around this cell overlap "
        f"with a Jaccard index of {diff.jaccard:.3f}: the radius adds {diff.radius_only:,} unreachable "
        f"cells and misses {diff.iso_only:,} reachable ones [src:{r}]",
        "",
        FFN_DISCLAIMER,
        "",
    ]
    return "\n".join(lines)


def build_memo(
    cell: CellGap,
    region: RegionAllocation,
    diff: DiffResult,
    rel: P01Releases,
    rows: list[dict[str, Any]],
    allowed_releases: set[str],
    generated_at: datetime,
) -> tuple[Memo, list[Finding]]:
    body = render_memo(cell, region, diff, rel)
    frows = [FeatureRow(x["feature_id"], Decimal(str(x["value"])), x["unit"], x["release_id"]) for x in rows]
    findings = verify(body, frows, allowed_releases)
    memo = Memo(
        memo_id=f"p01:{cell.h3_r8}:{cell.minutes}",
        subject_id=f"{cell.h3_r8}:{cell.minutes}min",
        body_md=body,
        cited_releases=tuple(sorted({rel.acs, rel.cdss, rel.routing, rel.matrix})),
        grounding_passed=not findings,
        model_id=MODEL_ID,
        generated_at=generated_at,
    )
    return memo, findings
