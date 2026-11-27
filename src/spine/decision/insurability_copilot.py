"""Product 02: California Insurability Copilot (Decision context).

A homeowner's evidence and appeal assistant built on 10 CCR § 2644.9, the Safer from Wildfires
regulation. It tells a California homeowner which of the 12 regulation-recognised mitigation items
they can document, what pinned open data shows around their structure, and assembles the score
request, revised-score request and appeal that the regulation entitles them to (G-103 2.1, 2.3).

It is **not** an insurer risk score or premium estimate. Insurer wildfire models are proprietary;
rating plans filed with the Commissioner are publicly inspectable (§ 2644.9(f)), which is the Prop 103
transparency anchor, not something this product reproduces. The only number it computes is the
Documentation Score (completeness of evidence). Open-data exposure is shown as a word tier.

Abstention is first-class (ADR-002): five reasons, all collected, the primary one first in
``ABSTAIN_ORDER``. When it abstains it still returns the full checklist so the homeowner knows what to
document; it withholds only the score and the "ready to appeal" state.

Zero PII (ADR-005 P1): a structure record is read through an allow-list, so owner, taxpayer or
occupant fields are rejected, never stored. Nothing here contacts an insurer; every letter is a draft
the homeowner sends. Engineering analysis of the regulation, not legal advice.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from spine.catalog.models import DatasetRelease, LicenseClass
from spine.compute.wildfire_mitigation import (
    ITEMS_BY_ID,
    MIN_VEG_5FT_PCT_CONFLICT,
    MITIGATIONS,
    DocumentationScore,
    EvidenceKind,
    ExposureContext,
    OpenDataObservation,
    StructureExposure,
    conflicting_items,
    documentation_score,
    exposure_context,
    resolve_evidence,
)
from spine.decision.models import AbstainReason, Evidence, Recommendation, Score

METHOD_VER = "0.1.0"
IN_SCOPE_KINDS = frozenset({"single_family", "duplex"})  # multi-unit, commercial, mobile homes deferred
STRUCTURE_KINDS = frozenset({"single_family", "duplex", "multi_unit", "commercial", "mobile_home"})
KIND_WORDS = {
    "single_family": "a single-family home",
    "duplex": "a duplex",
    "multi_unit": "a multi-unit building",
    "commercial": "a commercial building",
    "mobile_home": "a mobile home",
}
MAX_IMAGERY_AGE_YEARS = 3  # NAIP repeats at least every 3 years (G-101 [V])
MAX_HAZARD_AGE_YEARS = 5  # [D, review]
MAX_IMAGERY_AGE_DAYS = MAX_IMAGERY_AGE_YEARS * 365 + 1
MAX_HAZARD_AGE_DAYS = MAX_HAZARD_AGE_YEARS * 365 + 1
MIN_KNOWN_ITEMS = 6  # of 12 items need evidence other than "unknown" [D, G-103 open item 4]
READY_MIN_SCORE = 60.0  # documentation completeness at which a score request is "ready" [D, review]
ABSTAIN_ORDER: tuple[AbstainReason, ...] = (
    "out_of_domain",
    "license_blocked",
    "insufficient_coverage",
    "stale_release",
    "conflicting_evidence",
)
USER_SUPPLIED = "user_supplied"  # Evidence.release_id for the homeowner's own attestations

# The only keys a structure record may carry. Anything else (owner, taxpayer, occupant, APN, phone,
# email, ...) is rejected at the boundary, so person-level data never enters the build (ADR-005 P1).
STRUCTURE_FIELDS = frozenset(
    {
        "structure_id",
        "fixture",
        "state",
        "county_fips",
        "community_id",
        "structure_kind",
        "lat",
        "lon",
        "footprint_matched",
        "naip_veg_0_5ft_pct",
        "imagery_release_id",
        "imagery_vintage",
        "hazard_release_id",
        "hazard_vintage",
        "attested_evidence",
    }
)


@dataclass(frozen=True)
class P02Releases:
    """The release ids a Product 02 build cites, by role."""

    imagery: str  # NAIP
    canopy: str  # LANDFIRE
    terrain: str  # 3DEP
    buildings: str  # footprints (ODbL)
    community_lists: str  # Firewise USA + Board of Forestry FRRC lists
    regulation: str  # 10 CCR § 2644.9 text
    rubric: str  # pinned Product 02 method parameters (weights, thresholds), checksummed like data


@dataclass(frozen=True)
class Subject:
    structure_id: str  # synthetic id; never an APN or address
    state: str
    county_fips: str
    community_id: str | None
    structure_kind: str
    lat: float  # used only for the res-9 exposure join, never exported
    lon: float
    footprint_matched: bool
    naip_veg_0_5ft_pct: float | None
    imagery_release_id: str | None
    imagery_vintage: date | None
    hazard_release_id: str | None
    hazard_vintage: date | None
    attested_evidence: Mapping[str, str] = field(default_factory=dict)

    def input_releases(self, rel: P02Releases) -> tuple[str, ...]:
        ids = {rel.terrain, rel.buildings, rel.community_lists, rel.regulation, rel.rubric}
        ids |= {r for r in (self.imagery_release_id, self.hazard_release_id) if r}
        return tuple(sorted(ids))


def _date(v: Any) -> date | None:
    return None if v is None else date.fromisoformat(str(v))


def subject_from_record(rec: Mapping[str, Any]) -> Subject:
    extra = sorted(set(rec) - STRUCTURE_FIELDS)
    if extra:
        raise ValueError(f"fields not on the Product 02 allow-list (never fetched): {extra}")
    kind = str(rec["structure_kind"])
    if kind not in STRUCTURE_KINDS:
        raise ValueError(f"unknown structure_kind {kind!r}")
    veg = rec.get("naip_veg_0_5ft_pct")
    return Subject(
        structure_id=str(rec["structure_id"]),
        state=str(rec["state"]),
        county_fips=str(rec["county_fips"]),
        community_id=rec.get("community_id"),
        structure_kind=kind,
        lat=float(rec["lat"]),
        lon=float(rec["lon"]),
        footprint_matched=bool(rec["footprint_matched"]),
        naip_veg_0_5ft_pct=None if veg is None else float(veg),
        imagery_release_id=rec.get("imagery_release_id"),
        imagery_vintage=_date(rec.get("imagery_vintage")),
        hazard_release_id=rec.get("hazard_release_id"),
        hazard_vintage=_date(rec.get("hazard_vintage")),
        attested_evidence=dict(rec.get("attested_evidence") or {}),
    )


@dataclass(frozen=True)
class CommunityLists:
    """Pinned community lists: Firewise USA sites in good standing and Board of Forestry FRRCs."""

    firewise: frozenset[str]
    frrc: frozenset[str]

    def observe(self, s: Subject) -> OpenDataObservation:
        cid = s.community_id
        return OpenDataObservation(
            naip_veg_0_5ft_pct=s.naip_veg_0_5ft_pct if s.footprint_matched else None,
            firewise_listed=None if cid is None else cid in self.firewise,
            frrc_listed=None if cid is None else cid in self.frrc,
        )


@dataclass(frozen=True)
class GateFinding:
    reason: AbstainReason
    detail: str  # plain language; any figure in it is a grounded parameter (see spine.surface.p02_memo)


@dataclass(frozen=True)
class GateResult:
    findings: tuple[GateFinding, ...]  # sorted by ABSTAIN_ORDER; empty = proceed

    @property
    def reasons(self) -> tuple[AbstainReason, ...]:
        return tuple(dict.fromkeys(f.reason for f in self.findings))

    @property
    def primary(self) -> AbstainReason | None:
        return self.findings[0].reason if self.findings else None

    @property
    def abstain(self) -> bool:
        return bool(self.findings)


def abstention_gate(
    s: Subject,
    evidence: Mapping[str, EvidenceKind],
    conflicts: tuple[str, ...],
    exposure: StructureExposure | None,
    releases: Mapping[str, DatasetRelease],
    rel: P02Releases,
    *,
    as_of: date,
    commercial: bool,
) -> GateResult:
    """The five-reason gate. Every triggered reason is reported, primary first."""
    f: list[GateFinding] = []
    if s.state != "CA":
        f.append(GateFinding("out_of_domain", "this home is outside California"))
    if s.structure_kind not in IN_SCOPE_KINDS:
        f.append(
            GateFinding(
                "out_of_domain",
                f"this is {KIND_WORDS[s.structure_kind]}; only single-family homes and duplexes are "
                "covered for now",
            )
        )
    for rid in s.input_releases(rel):
        r = releases.get(rid)
        if r is None or r.status != "pinned":
            f.append(
                GateFinding("license_blocked", "a data source is not pinned, so its terms can't be checked")
            )
        elif r.license_class is LicenseClass.NON_COMMERCIAL:
            f.append(GateFinding("license_blocked", "a data source allows only non-commercial use"))
        elif r.license_class is LicenseClass.RESTRICTED and commercial:
            f.append(GateFinding("license_blocked", "a restricted data source needs approval for this use"))
    if not s.footprint_matched:
        f.append(GateFinding("insufficient_coverage", "no building footprint matched this structure"))
    if s.imagery_vintage is None:
        f.append(GateFinding("insufficient_coverage", "no NAIP imagery covers this structure"))
    if s.hazard_vintage is None or exposure is None:
        f.append(GateFinding("insufficient_coverage", "no canopy or slope data covers this structure"))
    known = sum(1 for m in MITIGATIONS if evidence[m.item_id] != "unknown")
    if known < MIN_KNOWN_ITEMS:
        f.append(
            GateFinding(
                "insufficient_coverage",
                f"evidence covers only {known} of the 12 items; at least {MIN_KNOWN_ITEMS} are needed",
            )
        )
    if s.imagery_vintage is not None and (as_of - s.imagery_vintage).days > MAX_IMAGERY_AGE_DAYS:
        f.append(
            GateFinding("stale_release", f"the NAIP imagery is older than {MAX_IMAGERY_AGE_YEARS} years")
        )
    if s.hazard_vintage is not None and (as_of - s.hazard_vintage).days > MAX_HAZARD_AGE_DAYS:
        f.append(GateFinding("stale_release", f"the canopy data is older than {MAX_HAZARD_AGE_YEARS} years"))
    for item_id in conflicts:
        label = ITEMS_BY_ID[item_id].label
        if item_id == "surround_5ft":
            why = (
                f"you attested “{label}”, but the imagery shows "
                f"{s.naip_veg_0_5ft_pct:.1f}% vegetation in that ring (limit {MIN_VEG_5FT_PCT_CONFLICT:.1f}%)"
            )
        else:
            why = f"you attested “{label}”, but the pinned list does not include your community"
        f.append(GateFinding("conflicting_evidence", why))
    f.sort(key=lambda g: ABSTAIN_ORDER.index(g.reason))
    return GateResult(tuple(f))


@dataclass(frozen=True)
class ChecklistRow:
    item_id: str
    subdivision: str
    label: str
    evidence: EvidenceKind
    strength: float


@dataclass(frozen=True)
class P02Assessment:
    subject_id: str
    structure_kind: str
    gate: GateResult
    checklist: tuple[ChecklistRow, ...]  # always all 12, even when abstaining
    score: DocumentationScore | None  # withheld (None) when abstaining
    exposure: StructureExposure | None
    exposure_context: ExposureContext | None
    naip_veg_0_5ft_pct: float | None
    canopy_release: str  # release behind the canopy figure (the subject's hazard layer)
    documentation_score: Score
    recommendation: Recommendation
    releases: P02Releases

    @property
    def ready_to_appeal(self) -> bool:
        return self.recommendation.verdict == "recommend"

    @property
    def items_needing_evidence(self) -> tuple[ChecklistRow, ...]:
        return tuple(r for r in self.checklist if r.evidence == "unknown")

    @property
    def items_with_evidence(self) -> tuple[ChecklistRow, ...]:
        return tuple(r for r in self.checklist if r.evidence != "unknown")


STRENGTH: dict[EvidenceKind, float] = {
    "open_data_observed": 1.0,
    "owner_attested_with_photo": 0.8,
    "owner_attested": 0.5,
    "unknown": 0.0,
}


def _evidence_rows(
    s: Subject, evidence: Mapping[str, EvidenceKind], rel: P02Releases
) -> tuple[Evidence, ...]:
    out: list[Evidence] = []
    for m in MITIGATIONS:
        kind = evidence[m.item_id]
        if kind == "unknown":
            continue
        if kind == "open_data_observed":
            source = rel.imagery if m.item_id == "surround_5ft" else rel.community_lists
        else:
            source = USER_SUPPLIED
        out.append(
            Evidence(
                evidence_id=f"p02:{s.structure_id}:{m.item_id}",
                feature_table="p02_item_evidence",
                feature_id=f"{s.structure_id}:{m.item_id}",
                value=STRENGTH[kind],
                release_id=source,
            )
        )
    return tuple(out)


def assess(
    s: Subject,
    lists: CommunityLists,
    exposure: StructureExposure | None,
    releases: Mapping[str, DatasetRelease],
    rel: P02Releases,
    *,
    as_of: date,
    commercial: bool = False,
) -> P02Assessment:
    obs = lists.observe(s)
    evidence = resolve_evidence(s.attested_evidence, obs)
    conflicts = conflicting_items(s.attested_evidence, obs)
    gate = abstention_gate(
        s, evidence, conflicts, exposure, releases, rel, as_of=as_of, commercial=commercial
    )
    full = documentation_score(evidence)
    checklist = tuple(
        ChecklistRow(m.item_id, m.subdivision, m.label, evidence[m.item_id], STRENGTH[evidence[m.item_id]])
        for m in MITIGATIONS
    )
    ev = _evidence_rows(s, evidence, rel)
    rec_id = f"p02:{s.structure_id}"
    if gate.abstain:
        rec = Recommendation(
            recommendation_id=rec_id,
            subject_id=s.structure_id,
            verdict="abstain",
            abstain_reason=gate.primary,
            rationale_md="We can't score this home yet: " + gate.findings[0].detail + ".",
            evidence=ev,
        )
        score: DocumentationScore | None = None
    else:
        ready = full.total >= READY_MIN_SCORE
        rec = Recommendation(
            recommendation_id=rec_id,
            subject_id=s.structure_id,
            verdict="recommend" if ready else "do_not_recommend",
            rationale_md=(
                "Documentation is complete enough to request your score and appeal."
                if ready
                else "Document more items before you request a score or appeal."
            ),
            evidence=ev,
        )
        score = full
    doc_score = Score(
        subject_id=s.structure_id,
        score_name="p02_documentation_completeness",
        value=None if score is None else score.total,
        evidence=ev,
    )
    return P02Assessment(
        subject_id=s.structure_id,
        structure_kind=s.structure_kind,
        gate=gate,
        checklist=checklist,
        score=score,
        exposure=exposure,
        exposure_context=None if exposure is None else exposure_context(exposure),
        naip_veg_0_5ft_pct=s.naip_veg_0_5ft_pct if s.footprint_matched else None,
        canopy_release=s.hazard_release_id or rel.canopy,
        documentation_score=doc_score,
        recommendation=rec,
        releases=rel,
    )


# --- appeal packet (the regulation's own duties, G-103 2.3) -------------------------------------------

SCORE_AFTER_APPLICATION_DAYS = 15  # (h) within 15 days of a completed application
SCORE_BEFORE_RENEWAL_DAYS = 45  # (h) at least 45 days before renewal
SCORE_BEFORE_NONRENEWAL_DAYS = 75  # (h) at least 75 days before nonrenewal
REVISED_SCORE_DAYS = 30  # (h)(4) within 30 days of a request after completed mitigation
APPEAL_ACK_DAYS = 10  # (i) written acknowledgement within 10 calendar days
APPEAL_DECISION_DAYS = 30  # (i) decision within 30 days

EXPLANATION_CHECKLIST: tuple[str, ...] = (
    "The range of possible scores",
    "Where your home falls in that range and how that affects your premium",
    "A detailed explanation of the score",
    "Mitigation that would lower your score",
    "The premium reduction each of those measures would bring",
)
ESCALATION = (
    "The insurer's response must include the Department of Insurance consumer hotline and the "
    "address of its Consumer Complaint Center."
)


@dataclass(frozen=True)
class UserDates:
    """Dates the homeowner enters. All optional; only entered events produce deadlines."""

    application_completed: date | None = None
    renewal: date | None = None
    nonrenewal_effective: date | None = None
    revised_score_requested: date | None = None
    appeal_received: date | None = None


@dataclass(frozen=True)
class Deadline:
    key: str
    rule: str  # subdivision of § 2644.9
    due: date
    description: str


def compute_deadlines(d: UserDates) -> tuple[Deadline, ...]:
    """Pure calendar arithmetic, mirrored in web/p02-insurability-copilot/deadlines.js (parity-tested)."""
    out: list[Deadline] = []
    if d.application_completed:
        out.append(
            Deadline(
                "score_after_application",
                "(h)",
                d.application_completed + timedelta(days=SCORE_AFTER_APPLICATION_DAYS),
                "Latest date for your written score after a completed application",
            )
        )
    if d.renewal:
        out.append(
            Deadline(
                "score_before_renewal",
                "(h)",
                d.renewal - timedelta(days=SCORE_BEFORE_RENEWAL_DAYS),
                "Latest date for your written score before renewal",
            )
        )
    if d.nonrenewal_effective:
        out.append(
            Deadline(
                "score_before_nonrenewal",
                "(h)",
                d.nonrenewal_effective - timedelta(days=SCORE_BEFORE_NONRENEWAL_DAYS),
                "Latest date for your written score before a nonrenewal takes effect",
            )
        )
    if d.revised_score_requested:
        out.append(
            Deadline(
                "revised_score",
                "(h)(4)",
                d.revised_score_requested + timedelta(days=REVISED_SCORE_DAYS),
                "Latest date for a revised score after your mitigation request",
            )
        )
    if d.appeal_received:
        out.append(
            Deadline(
                "appeal_acknowledgement",
                "(i)",
                d.appeal_received + timedelta(days=APPEAL_ACK_DAYS),
                "Latest date for the insurer's written acknowledgement of your appeal",
            )
        )
        out.append(
            Deadline(
                "appeal_decision",
                "(i)",
                d.appeal_received + timedelta(days=APPEAL_DECISION_DAYS),
                "Latest date for the insurer's decision on your appeal",
            )
        )
    return tuple(sorted(out, key=lambda x: (x.due, x.key)))


@dataclass(frozen=True)
class AppealPacket:
    subject_id: str
    ready: bool
    documented: tuple[ChecklistRow, ...]
    needing_evidence: tuple[ChecklistRow, ...]
    deadlines: tuple[Deadline, ...]
    explanation_checklist: tuple[str, ...] = EXPLANATION_CHECKLIST
    escalation: str = ESCALATION


def build_appeal_packet(a: P02Assessment, dates: UserDates | None = None) -> AppealPacket:
    return AppealPacket(
        subject_id=a.subject_id,
        ready=a.ready_to_appeal,
        documented=a.items_with_evidence,
        needing_evidence=a.items_needing_evidence,
        deadlines=compute_deadlines(dates or UserDates()),
    )
