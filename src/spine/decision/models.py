"""Decision entities (ADR-002), Pydantic v2."""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from spine.catalog.models import Frozen

AbstainReason = Literal[
    "insufficient_coverage", "stale_release", "conflicting_evidence", "out_of_domain", "license_blocked"
]


class Evidence(Frozen):
    evidence_id: str
    feature_table: str
    feature_id: str
    value: float
    release_id: str


class Score(Frozen):
    subject_id: str
    score_name: str
    value: float | None
    ci_low: float | None = None
    ci_high: float | None = None
    evidence: tuple[Evidence, ...]


class Recommendation(Frozen):
    recommendation_id: str
    subject_id: str
    verdict: Literal["recommend", "do_not_recommend", "abstain"]
    abstain_reason: AbstainReason | None = None
    rationale_md: str
    evidence: tuple[Evidence, ...]

    @model_validator(mode="after")
    def abstention_is_first_class(self) -> Recommendation:
        if self.verdict == "abstain" and self.abstain_reason is None:
            raise ValueError("'We don't know' requires an abstain_reason")
        if self.verdict != "abstain" and not self.evidence:
            raise ValueError("non-abstaining recommendation needs >=1 Evidence row")
        return self
