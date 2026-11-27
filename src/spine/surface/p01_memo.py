"""Product 01 memo (Surface context): template-rendered, then gated by ADR-004.

No LLM here: the "AI plane" slot is a deterministic template for the scaffold. Whatever writes
the prose later, `grounding_passed` comes only from the verifier.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from spine.compute.isochrone_diff import DiffResult
from spine.decision.childcare_gap import AGE_MAX, AGE_MIN, GapResult, P01Releases
from spine.decision.grounding_verifier import FeatureRow, Finding, verify
from spine.surface.models import Memo

MODEL_ID = "template:p01_memo@0.1.0"
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


def render_memo(gap: GapResult, diff: DiffResult, rel: P01Releases) -> str:
    m = gap.minutes
    a, c, r = rel.acs, rel.cdss, rel.routing
    if gap.gap_seats > 0:
        gap_line = (
            f"- {GAP_TERM.capitalize()}: {gap.gap_seats:,} more children than licensed seats, "
            f"or {gap.seats_per_child:.3f} licensed seats per child [src:{c}] [src:{a}]"
        )
    else:
        gap_line = (
            f"- No {GAP_TERM}: licensed seats exceed children by {-gap.gap_seats:,}, "
            f"or {gap.seats_per_child:.3f} licensed seats per child [src:{c}] [src:{a}]"
        )
    radius = f"{diff.radius_mi:g}"
    lines = [
        f"# Santa Clara {GAP_TERM}: catchment {gap.origin_h3_r8}",
        "",
        SYNTHETIC_BANNER,
        "",
        f"- Children aged {AGE_MIN} to {AGE_MAX} within a {m}-minute drive: {gap.children_0_5:,} "
        f"[src:{a}] [src:{r}]",
        f"- Licensed seats within the same {m}-minute drive: {gap.licensed_seats:,} [src:{c}]",
        gap_line,
        f"- A {radius}-mile radius and the {m}-minute drive-time area overlap with a Jaccard index of "
        f"{diff.jaccard:.3f}: the radius adds {diff.radius_only:,} unreachable cells and misses "
        f"{diff.iso_only:,} reachable ones [src:{r}]",
        "",
        FFN_DISCLAIMER,
        "",
    ]
    return "\n".join(lines)


def build_memo(
    gap: GapResult,
    diff: DiffResult,
    rel: P01Releases,
    rows: list[dict[str, Any]],
    allowed_releases: set[str],
    generated_at: datetime,
) -> tuple[Memo, list[Finding]]:
    body = render_memo(gap, diff, rel)
    frows = [FeatureRow(x["feature_id"], Decimal(str(x["value"])), x["unit"], x["release_id"]) for x in rows]
    findings = verify(body, frows, allowed_releases)
    memo = Memo(
        memo_id=f"p01:{gap.origin_h3_r8}:{gap.minutes}",
        subject_id=f"{gap.origin_h3_r8}:{gap.minutes}min",
        body_md=body,
        cited_releases=tuple(sorted({a for a in (rel.acs, rel.cdss, rel.routing)})),
        grounding_passed=not findings,
        model_id=MODEL_ID,
        generated_at=generated_at,
    )
    return memo, findings
