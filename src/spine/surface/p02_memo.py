"""Product 02 memo and appeal letters (Surface context), gated by the ADR-004 grounding verifier.

Template ``template:p02_memo@0.1.0``; no LLM. Every figure in the memo and the letters must match a
deterministic feature row whose release is cited, so the regulation's own numbers (the title, the
section, its day counts and distances) are rows of the pinned regulation release, and the rubric's
weights and thresholds are rows of the pinned rubric release (G-103 recommendation: ``ref_*`` rows
for legal citations). ``Memo.grounding_passed`` comes only from the verifier.

Copy rules: the Documentation Score is always called "documentation completeness" and is never
called a risk score; the memo says everything is a draft the homeowner sends; no owner name,
address or APN appears (letters carry bracketed placeholders the homeowner fills in).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from spine.compute.wildfire_mitigation import (
    BLOCK_MAX,
    ITEM_POINTS,
    MAX_VEG_5FT_PCT_CLEAR,
    MIN_VEG_5FT_PCT_CONFLICT,
    MITIGATIONS,
    SCORE_MAX,
    EvidenceKind,
)
from spine.decision.grounding_verifier import CITE_RE, FeatureRow, Finding, verify
from spine.decision.insurability_copilot import (
    APPEAL_ACK_DAYS,
    APPEAL_DECISION_DAYS,
    ESCALATION,
    EXPLANATION_CHECKLIST,
    MAX_HAZARD_AGE_YEARS,
    MAX_IMAGERY_AGE_YEARS,
    MIN_KNOWN_ITEMS,
    READY_MIN_SCORE,
    REVISED_SCORE_DAYS,
    SCORE_AFTER_APPLICATION_DAYS,
    SCORE_BEFORE_NONRENEWAL_DAYS,
    SCORE_BEFORE_RENEWAL_DAYS,
    AppealPacket,
    P02Assessment,
)
from spine.surface.models import Memo

MODEL_ID = "template:p02_memo@0.1.0"
SYNTHETIC_BANNER = "_Synthetic fixture data for CI. This is not a real Butte County home._"
DRAFT_LINE = "Draft only. You send every letter yourself; this tool never contacts an insurer."
NOT_A_RISK_SCORE = (
    "This measures how well your mitigation is documented. It is not a risk score: insurers use "
    "their own wildfire models."
)
EVIDENCE_WORDS: dict[EvidenceKind, str] = {
    "open_data_observed": "seen in pinned open data",
    "owner_attested_with_photo": "your attestation with a photo",
    "owner_attested": "your attestation",
    "unknown": "no evidence yet",
}
LETTER_EVIDENCE: dict[EvidenceKind, str] = {
    "open_data_observed": "public records",
    "owner_attested_with_photo": "photo attached",
    "owner_attested": "my attestation",
    "unknown": "",
}
CCR_TITLE, CCR_SECTION = 10, Decimal("2644.9")
ITEM_COUNT = len(MITIGATIONS)
RING_INNER_FT, RING_FT, OUTER_FT, CLEARANCE_IN = 0, 5, 30, 6


def _row(feature_id: str, value: float | int | Decimal, release_id: str, unit: str = "") -> dict[str, Any]:
    v = value if isinstance(value, Decimal) else Decimal(str(value))
    return {"feature_id": feature_id, "value": float(v), "unit": unit, "release_id": release_id}


def feature_rows(a: P02Assessment) -> list[dict[str, Any]]:
    """Deterministic rows that back every figure the memo and letters may print."""
    r = a.releases
    reg, rub = r.regulation, r.rubric
    rows = [
        _row("ref_ccr_title", CCR_TITLE, reg),
        _row("ref_ccr_section", CCR_SECTION, reg),
        _row("ref_items_total", ITEM_COUNT, reg),
        _row("ref_ring_inner_ft", RING_INNER_FT, reg),
        _row("ref_ring_ft", RING_FT, reg),
        _row("ref_combustible_structures_ft", OUTER_FT, reg),
        _row("ref_vertical_clearance_in", CLEARANCE_IN, reg),
        _row("ref_score_after_application_days", SCORE_AFTER_APPLICATION_DAYS, reg),
        _row("ref_score_before_renewal_days", SCORE_BEFORE_RENEWAL_DAYS, reg),
        _row("ref_score_before_nonrenewal_days", SCORE_BEFORE_NONRENEWAL_DAYS, reg),
        _row("ref_revised_score_days", REVISED_SCORE_DAYS, reg),
        _row("ref_appeal_ack_days", APPEAL_ACK_DAYS, reg),
        _row("ref_appeal_decision_days", APPEAL_DECISION_DAYS, reg),
        _row("param_score_max", SCORE_MAX, rub),
        _row("param_community_max", BLOCK_MAX["community"], rub),
        _row("param_surroundings_max", BLOCK_MAX["surroundings"], rub),
        _row("param_hardening_max", BLOCK_MAX["hardening"], rub),
        _row("param_community_item_points", ITEM_POINTS["community"], rub),
        _row("param_other_item_points", ITEM_POINTS["surroundings"], rub),
        _row("param_ready_min_score", READY_MIN_SCORE, rub),
        _row("param_min_known_items", MIN_KNOWN_ITEMS, rub),
        _row("param_max_imagery_age_years", MAX_IMAGERY_AGE_YEARS, rub),
        _row("param_max_hazard_age_years", MAX_HAZARD_AGE_YEARS, rub),
        _row("param_veg_5ft_clear_pct", MAX_VEG_5FT_PCT_CLEAR, rub, "%"),
        _row("param_veg_5ft_conflict_pct", MIN_VEG_5FT_PCT_CONFLICT, rub, "%"),
        _row("items_with_evidence", len(a.items_with_evidence), reg),
        _row("items_needing_evidence", len(a.items_needing_evidence), reg),
    ]
    if a.score is not None:
        rows += [
            _row("documentation_score", a.score.total, rub),
            _row("documentation_community", a.score.community, rub),
            _row("documentation_surroundings", a.score.surroundings, rub),
            _row("documentation_hardening", a.score.hardening, rub),
        ]
    if a.naip_veg_0_5ft_pct is not None:
        rows.append(_row("naip_veg_0_5ft_pct", a.naip_veg_0_5ft_pct, r.imagery, "%"))
    if a.exposure is not None:
        rows += [
            _row("landfire_canopy_cover_pct", a.exposure.canopy_cover_pct, a.canopy_release, "%"),
            _row("usgs_3dep_slope_deg", a.exposure.slope_deg, r.terrain),
        ]
    return rows


def allowed_releases(a: P02Assessment) -> set[str]:
    r = a.releases
    return {r.imagery, a.canopy_release, r.terrain, r.buildings, r.community_lists, r.regulation, r.rubric}


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:]


def render_memo(a: P02Assessment, packet: AppealPacket) -> str:
    r = a.releases
    reg, rub, img, ter = r.regulation, r.rubric, r.imagery, r.terrain
    law = f"{CCR_TITLE} CCR § {CCR_SECTION}"
    lines = [
        f"# Wildfire mitigation evidence memo: structure {a.subject_id}",
        "",
        SYNTHETIC_BANNER,
        "",
        DRAFT_LINE,
        "",
    ]
    if a.score is not None:
        s = a.score
        status = (
            "Ready: your documentation is complete enough to request your score and appeal."
            if packet.ready
            else f"Not ready yet: document more items until completeness reaches {READY_MIN_SCORE:.1f} "
            f"[src:{rub}]."
        )
        lines += [
            "## Documentation completeness",
            f"- Documentation completeness: {s.total:.1f} out of {SCORE_MAX} [src:{rub}]. {NOT_A_RISK_SCORE}",
            f"- Community {s.community:.1f} of {BLOCK_MAX['community']}, surroundings "
            f"{s.surroundings:.1f} of "
            f"{BLOCK_MAX['surroundings']}, building hardening {s.hardening:.1f} of {BLOCK_MAX['hardening']} "
            f"[src:{rub}]",
            f"- Items with evidence: {len(a.items_with_evidence)} of the {ITEM_COUNT} items in {law} "
            f"[src:{reg}]",
            f"- {status}",
            "",
        ]
    else:
        lines += ["## We can't score this home yet"]
        lines += [f"- {_sentence(f.detail)} [src:{reg}] [src:{rub}] [src:{img}]" for f in a.gate.findings]
        lines += [
            f"- Items with evidence so far: {len(a.items_with_evidence)} of the {ITEM_COUNT} items in {law} "
            f"[src:{reg}]",
            "- The checklist below still shows what to document. The score and the appeal stay withheld "
            "until these are resolved.",
            "",
        ]
    lines += ["## What open data shows around this structure"]
    if a.naip_veg_0_5ft_pct is not None:
        lines.append(
            f"- Vegetation within {RING_INNER_FT} to {RING_FT} ft of the building on NAIP imagery: "
            f"{a.naip_veg_0_5ft_pct:.1f}% [src:{img}] [src:{reg}]"
        )
    else:
        lines.append(
            f"- No building footprint matched, so the ring around the building wasn't measured [src:{img}]"
        )
    if a.exposure is not None:
        lines += [
            "- Tree canopy cover in this structure's grid cell (LANDFIRE): "
            f"{a.exposure.canopy_cover_pct:.1f}% "
            f"[src:{a.canopy_release}]",
            f"- Average slope in that cell (USGS 3DEP): {a.exposure.slope_deg:.1f} degrees [src:{ter}]",
            f"- Open-data exposure context: {a.exposure_context}. This describes the surroundings; it is "
            "not an insurer's score.",
        ]
    else:
        lines.append("- No canopy or slope data covers this structure's grid cell.")
    lines += ["", "## Evidence per item"]
    lines += [f"- {row.label}: {EVIDENCE_WORDS[row.evidence]}" for row in a.checklist]
    lines += [
        "",
        f"## Your rights under {law} [src:{reg}]",
        f"- Score request: your insurer must give your wildfire score in writing within "
        f"{SCORE_AFTER_APPLICATION_DAYS} days of a completed application, at least "
        f"{SCORE_BEFORE_RENEWAL_DAYS} "
        f"days before renewal and at least {SCORE_BEFORE_NONRENEWAL_DAYS} days before nonrenewal [src:{reg}]",
        f"- Revised score: within {REVISED_SCORE_DAYS} days of your request after you complete a mitigation "
        f"measure [src:{reg}]",
        f"- Appeal: you can appeal orally or in writing; the insurer acknowledges in writing within "
        f"{APPEAL_ACK_DAYS} calendar days and decides within {APPEAL_DECISION_DAYS} days [src:{reg}]",
        "- Check that the insurer's explanation covers:",
    ]
    lines += [f"  - {x}" for x in EXPLANATION_CHECKLIST]
    lines += [f"- {ESCALATION}", ""]
    return "\n".join(lines)


def _documented_lines(packet: AppealPacket) -> list[str]:
    return [f"- {row.label} ({LETTER_EVIDENCE[row.evidence]})" for row in packet.documented]


def render_letters(a: P02Assessment, packet: AppealPacket) -> dict[str, str]:
    """Draft letters for § 2644.9 (h), (h)(4) and (i). Placeholders in brackets; no citations inside,
    because the insurer reads them (they are verified with the memo's sources appended)."""
    law = f"{CCR_TITLE} CCR § {CCR_SECTION}"
    head = ["[Your name]", "[Date]", "", "To [insurer name], policy [policy number]:", ""]
    sign = ["", "Thank you,", "[Your name]", ""]
    explanation = (
        "the range of possible scores, where my home falls in that range and how that affects my premium, "
        "a detailed explanation, the mitigation that would lower my score, and the premium reduction each "
        "of those measures would bring"
    )
    documented = _documented_lines(packet) or ["- (none documented yet)"]
    letters = {
        "score_request": "\n".join(
            [
                *head,
                f"Under {law}, I request my property's wildfire score in writing, with the explanation the "
                f"regulation requires: {explanation}.",
                "",
                "My home has the following mitigation:",
                *documented,
                *sign,
            ]
        )
    }
    if packet.documented:
        letters["revised_score_request"] = "\n".join(
            [
                *head,
                f"I have completed the mitigation listed below. Under {law}, please send a revised wildfire "
                f"score within {REVISED_SCORE_DAYS} days of this request.",
                "",
                *documented,
                *sign,
            ]
        )
    if packet.ready:
        letters["appeal"] = "\n".join(
            [
                *head,
                f"I appeal my wildfire score under {law}. My home has the mitigation below, which I believe "
                "the score does not reflect. Please acknowledge this appeal in writing within "
                f"{APPEAL_ACK_DAYS} calendar days and send your decision within {APPEAL_DECISION_DAYS} days, "
                f"with {explanation}.",
                "",
                *documented,
                "",
                "Please include the Department of Insurance consumer hotline and Consumer Complaint Center "
                "address in your response.",
                *sign,
            ]
        )
    return letters


def _frows(rows: list[dict[str, Any]]) -> list[FeatureRow]:
    return [FeatureRow(x["feature_id"], Decimal(str(x["value"])), x["unit"], x["release_id"]) for x in rows]


def verify_letter(letter: str, a: P02Assessment) -> list[Finding]:
    """Letters carry no [src:] tags; verify them with the regulation and rubric releases as sources."""
    if CITE_RE.search(letter):
        return [Finding("[src:", "letters must not show citation tags", 0)]
    footer = f"\n[src:{a.releases.regulation}] [src:{a.releases.rubric}]"
    return verify(letter + footer, _frows(feature_rows(a)), allowed_releases(a))


def build_memo(a: P02Assessment, packet: AppealPacket, generated_at: datetime) -> tuple[Memo, list[Finding]]:
    body = render_memo(a, packet)
    findings = verify(body, _frows(feature_rows(a)), allowed_releases(a))
    memo = Memo(
        memo_id=f"p02:{a.subject_id}",
        subject_id=a.subject_id,
        body_md=body,
        cited_releases=tuple(sorted(set(CITE_RE.findall(body)))),
        grounding_passed=not findings,
        model_id=MODEL_ID,
        generated_at=generated_at,
    )
    return memo, findings


def features_payload(a: P02Assessment) -> dict[str, Any]:
    """The JSON shape ``python -m spine.decision.grounding_verifier`` reads."""
    return {"allowed_releases": sorted(allowed_releases(a)), "rows": feature_rows(a)}
