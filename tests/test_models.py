"""ADR-001/002 entities: the 6 G-102 tests (ported to pytest) plus the pending-release rule."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from spine.catalog.models import DatasetRelease, LicenseClass, Provenance
from spine.compute.models import EmbeddingDelta
from spine.decision.models import Recommendation
from spine.identity.models import Facility

P = Provenance(
    release_id="cdss_ccl_2026-11-01",
    method_ver="0.1.0",
    build_id="b1",
    license_class=LicenseClass.PUBLIC_DOMAIN,
)
SHA = "a" * 64
NOW = dt.datetime(2026, 11, 27, tzinfo=dt.UTC)


def _rel(**kw: object) -> DatasetRelease:
    base: dict[str, object] = dict(
        release_id="osm_ca_2026-11-20",
        source_id="osm",
        vintage="2026-11-20",
        url="https://x/california-261120.osm.pbf",
        sha256=SHA,
        license_spdx="ODbL-1.0",
        license_class="share_alike",
        commercial_ok=True,
        retrieved_at=NOW,
    )
    base.update(kw)
    return DatasetRelease.model_validate(base)


def test_latest_rejected() -> None:
    with pytest.raises(ValidationError):
        _rel(vintage="latest", url="https://x/california-latest.osm.pbf")


def test_release_ok() -> None:
    assert _rel().status == "pinned"


def test_pinned_needs_checksum_but_pending_does_not() -> None:
    with pytest.raises(ValidationError):
        _rel(sha256=None)
    assert _rel(sha256=None, retrieved_at=None, status="pending_download").sha256 is None


def test_abstain_needs_reason() -> None:
    with pytest.raises(ValidationError):
        Recommendation(recommendation_id="r", subject_id="s", verdict="abstain", rationale_md="", evidence=())
    Recommendation(
        recommendation_id="r",
        subject_id="s",
        verdict="abstain",
        abstain_reason="insufficient_coverage",
        rationale_md="",
        evidence=(),
    )


def test_recommend_needs_evidence() -> None:
    with pytest.raises(ValidationError):
        Recommendation(
            recommendation_id="r", subject_id="s", verdict="recommend", rationale_md="x", evidence=()
        )


def test_h3_pattern() -> None:
    Facility(
        facility_id="f",
        kind="childcare_center",
        status="LICENSED",
        h3_r8="88283082a3fffff",
        location_precision="rooftop",
        prov=P,
    )
    with pytest.raises(ValidationError):
        Facility(
            facility_id="f",
            kind="childcare_center",
            status="LICENSED",
            h3_r8="zz",
            location_precision="rooftop",
            prov=P,
        )


def test_embedding_years() -> None:
    with pytest.raises(ValidationError):
        EmbeddingDelta(h3_r9="89283082a3fffff", year_a=2019, year_b=2017, cosine_distance=0.2, prov=P)
