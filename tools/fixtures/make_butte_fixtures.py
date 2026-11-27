"""Regenerate the SYNTHETIC Butte County / Paradise fixtures for Product 02 (deterministic).

Nothing here is real data: no real parcel, structure, address or person. Structure ids are
``SYN_BUTTE_*``, community ids ``SYN-COMM-*``, and every value is written out below.

Source files (each one is a pinned fixture "release" in tests/fixtures/releases_p02.fixture.yaml):

* butte/intake_synthetic.json: what a homeowner enters (structure kind, community, attested evidence).
  Not a release: it is user-supplied. It has no owner, taxpayer, occupant or APN field.
* butte/footprint_rings_synthetic.json: footprint match + NAIP vegetation in the 0 to 5 ft ring.
  Footprint-derived, so it mirrors ODbL (Overture Buildings) and stays in its own table (G-103 G2.6).
* butte/exposure_samples_synthetic.json: LANDFIRE canopy and 3DEP slope sample points, joined to
  structures at H3 res 9. Samples sit exactly on their structure point, decoys are >1.5 km away, so
  the join result is the same under the real H3 grid and the test grid.
* butte/community_lists_synthetic.json: Firewise USA sites and Board of Forestry FRRC communities.
* butte/ccr_2644_9_d1_items.json: the 12 items of 10 CCR § 2644.9(d)(1) (the regulation release).
* butte/p02_rubric_params.json: Product 02 weights and thresholds, pinned like data (ADR-004 rows).
* butte/naip_tiles_{2024,2022}_synthetic.json, butte/nc_wildfire_model_synthetic.json: tile indexes
  and a non-commercial model stand-in, so the stale and licence-blocked paths have real releases.

Derived: tests/fixtures/memos/p02_butte_{memo,abstain_memo}.md + features JSON, and the viewer
export web/p02-insurability-copilot/data/cards.json. Res-9 cell ids are never written anywhere.

Run: ``make fixtures-p02`` (needs h3). ``--fake-grid`` uses a rounding grid instead of H3, for
machines without h3; CI regenerates with real H3 and checks the committed files byte for byte.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from spine.catalog.models import DatasetRelease
from spine.compute.wildfire_mitigation import (
    BLOCK_MAX,
    ELEVATED_CANOPY_PCT,
    ELEVATED_SLOPE_DEG,
    HIGH_CANOPY_PCT,
    HIGH_SLOPE_DEG,
    ITEM_POINTS,
    MAX_VEG_5FT_PCT_CLEAR,
    METHOD_VER,
    MIN_VEG_5FT_PCT_CONFLICT,
    MITIGATIONS,
    SCORE_MAX,
    STRENGTH_TENTHS,
    CellOf,
    ExposureSample,
    aggregate_exposure,
    h3_r9,
    join_exposure,
)
from spine.decision.insurability_copilot import (
    APPEAL_ACK_DAYS,
    APPEAL_DECISION_DAYS,
    MAX_HAZARD_AGE_YEARS,
    MAX_IMAGERY_AGE_YEARS,
    MIN_KNOWN_ITEMS,
    READY_MIN_SCORE,
    REVISED_SCORE_DAYS,
    SCORE_AFTER_APPLICATION_DAYS,
    SCORE_BEFORE_NONRENEWAL_DAYS,
    SCORE_BEFORE_RENEWAL_DAYS,
    CommunityLists,
    P02Assessment,
    P02Releases,
    Subject,
    assess,
    build_appeal_packet,
    subject_from_record,
)
from spine.surface.p02_memo import build_memo, features_payload, render_letters

ROOT = Path(__file__).resolve().parents[2]
AS_OF = date(2026, 11, 27)
GENERATED_AT = datetime(2026, 11, 27, tzinfo=UTC)
RETRIEVED_AT = "2026-11-27T00:00:00+00:00"
BUILD_ID = "fixture-g302"
NOTE = "SYNTHETIC fixture for CI. Not real Butte County data; no real structure, address or person."
B = "tests/fixtures/butte"
REL = P02Releases(
    imagery="fixture_naip_butte_2024-06-15",
    canopy="fixture_landfire_butte_2024",
    terrain="fixture_3dep_butte_2026-11",
    buildings="fixture_overture_buildings_butte_2026-11",
    community_lists="fixture_community_lists_butte_2026-11",
    regulation="fixture_ccr_title10_2644_9_2022-10-14",
    rubric="fixture_p02_rubric_2026-11-27",
)
NAIP_2022 = "fixture_naip_butte_2022-06-01"
NC_MODEL = "fixture_nc_wildfire_model_butte_2026-01"
MEMO_SUBJECT, ABSTAIN_MEMO_SUBJECT = "SYN_BUTTE_0001", "SYN_BUTTE_0005"
ATTRIBUTION = (
    "Synthetic stand-ins for: USDA NAIP imagery · LANDFIRE · USGS 3DEP · Overture Maps buildings (ODbL) · "
    "Firewise USA and Board of Forestry community lists · 10 CCR § 2644.9"
)

P, A = "owner_attested_with_photo", "owner_attested"
BASE_LAT, BASE_LON = 39.7596, -121.6219  # synthetic points around Paradise, CA


def _structure(
    n: int,
    dlat: float,
    dlon: float,
    kind: str,
    community: str | None,
    evidence: dict[str, str],
    *,
    imagery: tuple[str, str] | None = (REL.imagery, "2024-06-15"),
    hazard: tuple[str, str] | None = (REL.canopy, "2024-01-01"),
) -> dict[str, Any]:
    return {
        "structure_id": f"SYN_BUTTE_{n:04d}",
        "fixture": "synthetic",
        "state": "CA",
        "county_fips": "06007",
        "community_id": community,
        "structure_kind": kind,
        "lat": round(BASE_LAT + dlat, 4),
        "lon": round(BASE_LON + dlon, 4),
        "imagery_release_id": imagery[0] if imagery else None,
        "imagery_vintage": imagery[1] if imagery else None,
        "hazard_release_id": hazard[0] if hazard else None,
        "hazard_vintage": hazard[1] if hazard else None,
        "attested_evidence": evidence,
    }


WELL_DOCUMENTED = {
    "surround_under_deck": P,
    "surround_fence_5ft": A,
    "surround_30ft_structures": P,
    "surround_defensible_space": A,
    "harden_class_a_roof": P,
    "harden_enclosed_eaves": P,
    "harden_vents": P,
    "harden_windows": A,
}


def intake() -> dict[str, Any]:
    ridge, magalia = "SYN-COMM-PARADISE-RIDGE", "SYN-COMM-MAGALIA"
    return {
        "_fixture_note": NOTE + " Homeowner intake: user-supplied, not a release.",
        "structures": [
            # Ready: Firewise community + clear 0-5 ft ring from open data + photo-backed hardening.
            _structure(1, 0.0, 0.0, "single_family", ridge, WELL_DOCUMENTED),
            # In scope but thinly documented: scored, "document more first".
            _structure(
                2,
                0.02,
                0.0,
                "duplex",
                magalia,
                {k: A for k in ("surround_under_deck", "surround_fence_5ft", "surround_30ft_structures")}
                | {k: A for k in ("harden_class_a_roof", "harden_vents", "harden_windows")},
            ),
            _structure(3, -0.02, 0.0, "commercial", ridge, WELL_DOCUMENTED),  # out_of_domain
            _structure(
                4, 0.0, 0.025, "single_family", ridge, WELL_DOCUMENTED, imagery=(NAIP_2022, "2022-06-01")
            ),
            _structure(5, 0.0, -0.025, "single_family", magalia, WELL_DOCUMENTED | {"surround_5ft": P}),
            _structure(6, -0.02, 0.025, "single_family", magalia, {"harden_class_a_roof": A}),
            _structure(
                7, 0.02, 0.025, "single_family", ridge, WELL_DOCUMENTED, hazard=(NC_MODEL, "2026-01-15")
            ),
        ],
    }


def footprint_rings() -> dict[str, Any]:
    veg = {1: 6.0, 2: 18.0, 3: 4.0, 4: 7.0, 5: 32.0, 7: 5.0}
    return {
        "_fixture_note": NOTE + " Footprint-derived ring metrics (mirrors ODbL; separate table, G-103 G2.6).",
        "structures": [
            {
                "structure_id": f"SYN_BUTTE_{n:04d}",
                "fixture": "synthetic",
                "footprint_matched": n in veg,
                "naip_veg_0_5ft_pct": veg.get(n),
            }
            for n in range(1, 8)
        ],
    }


def exposure_samples(structures: list[dict[str, Any]]) -> dict[str, Any]:
    # (canopy %, slope deg) pairs per structure; structure 6 has no samples (no coverage).
    vals = {
        1: [(22.0, 9.0), (26.0, 11.0)],
        2: [(40.0, 12.0), (44.0, 14.0)],
        3: [(20.0, 6.0), (24.0, 8.0)],
        4: [(30.0, 10.0), (32.0, 12.0)],
        5: [(55.0, 18.0), (59.0, 22.0)],
        7: [(28.0, 16.0), (30.0, 18.0)],
    }
    pts = []
    for s in structures:
        n = int(s["structure_id"].rsplit("_", 1)[1])
        for canopy, slope in vals.get(n, []):
            pts.append({"lat": s["lat"], "lon": s["lon"], "canopy_cover_pct": canopy, "slope_deg": slope})
    for dlat, dlon in ((0.06, 0.06), (-0.06, -0.06), (0.06, -0.06)):  # decoys, far from every structure
        pts.append(
            {
                "lat": round(BASE_LAT + dlat, 4),
                "lon": round(BASE_LON + dlon, 4),
                "canopy_cover_pct": 90.0,
                "slope_deg": 40.0,
            }
        )
    return {"_fixture_note": NOTE + " LANDFIRE canopy + 3DEP slope sample points.", "samples": pts}


def community_lists() -> dict[str, Any]:
    return {
        "_fixture_note": NOTE + " Community lists with synthetic ids.",
        "firewise_usa_sites_in_good_standing": ["SYN-COMM-PARADISE-RIDGE"],
        "board_of_forestry_frrc": ["SYN-COMM-CONCOW"],
    }


def regulation_items() -> dict[str, Any]:
    return {
        "_fixture_note": (
            "Fixture copy of the 12 mitigation items of 10 CCR § 2644.9(d)(1) (filed and operative "
            "2022-10-14), as read on the LII copy for G-103 section 2.2. Engineering summary, not legal "
            "advice."
        ),
        "items": [
            {"item_id": m.item_id, "subdivision": m.subdivision, "block": m.block, "text": m.regulation_text}
            for m in MITIGATIONS
        ],
    }


def rubric_params() -> dict[str, Any]:
    return {
        "_fixture_note": (
            "Product 02 rubric parameters (G-103 2.3 and 2.4, [D] values), pinned so memos can cite them."
        ),
        "method_ver": METHOD_VER,
        "strength_tenths": dict(STRENGTH_TENTHS),
        "item_points": dict(ITEM_POINTS),
        "block_max": dict(BLOCK_MAX),
        "score_max": SCORE_MAX,
        "ready_min_score": READY_MIN_SCORE,
        "min_known_items": MIN_KNOWN_ITEMS,
        "max_imagery_age_years": MAX_IMAGERY_AGE_YEARS,
        "max_hazard_age_years": MAX_HAZARD_AGE_YEARS,
        "veg_5ft_clear_pct": MAX_VEG_5FT_PCT_CLEAR,
        "veg_5ft_conflict_pct": MIN_VEG_5FT_PCT_CONFLICT,
        "exposure_context": {
            "high_canopy_pct": HIGH_CANOPY_PCT,
            "high_slope_deg": HIGH_SLOPE_DEG,
            "elevated_canopy_pct": ELEVATED_CANOPY_PCT,
            "elevated_slope_deg": ELEVATED_SLOPE_DEG,
        },
        "deadline_days": {
            "score_after_application": SCORE_AFTER_APPLICATION_DAYS,
            "score_before_renewal": SCORE_BEFORE_RENEWAL_DAYS,
            "score_before_nonrenewal": SCORE_BEFORE_NONRENEWAL_DAYS,
            "revised_score": REVISED_SCORE_DAYS,
            "appeal_acknowledgement": APPEAL_ACK_DAYS,
            "appeal_decision": APPEAL_DECISION_DAYS,
        },
    }


def naip_tiles(vintage: str) -> dict[str, Any]:
    return {
        "_fixture_note": NOTE + " NAIP-shaped tile index.",
        "acquisition_date": vintage,
        "tiles": [{"tile_id": f"SYN-NAIP-BUTTE-{vintage}-A", "gsd_m": 0.6}],
    }


def nc_model() -> dict[str, Any]:
    return {
        "_fixture_note": NOTE + " Stand-in for a non-commercial wildfire model layer (licence-gate test).",
        "layer": "synthetic_nc_hazard",
    }


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def source_files() -> dict[str, str]:
    ik = intake()
    return {
        f"{B}/intake_synthetic.json": dumps(ik),
        f"{B}/footprint_rings_synthetic.json": dumps(footprint_rings()),
        f"{B}/exposure_samples_synthetic.json": dumps(exposure_samples(ik["structures"])),
        f"{B}/community_lists_synthetic.json": dumps(community_lists()),
        f"{B}/ccr_2644_9_d1_items.json": dumps(regulation_items()),
        f"{B}/p02_rubric_params.json": dumps(rubric_params()),
        f"{B}/naip_tiles_2024_synthetic.json": dumps(naip_tiles("2024-06-15")),
        f"{B}/naip_tiles_2022_synthetic.json": dumps(naip_tiles("2022-06-01")),
        f"{B}/nc_wildfire_model_synthetic.json": dumps(nc_model()),
    }


# release_id -> (source_id, vintage, file, spdx, class, commercial_ok, note)
RELEASES: tuple[tuple[str, str, str, str, str, str, bool, str], ...] = (
    (
        REL.imagery,
        "fixture_naip",
        "2024-06-15",
        "naip_tiles_2024_synthetic.json",
        "LicenseRef-fixture-mirrors-US-PD",
        "public_domain",
        True,
        "NAIP-shaped tile index.",
    ),
    (
        NAIP_2022,
        "fixture_naip",
        "2022-06-01",
        "naip_tiles_2022_synthetic.json",
        "LicenseRef-fixture-mirrors-US-PD",
        "public_domain",
        True,
        "Older NAIP-shaped tile index, used to test stale_release.",
    ),
    (
        REL.canopy,
        "fixture_landfire",
        "2024",
        "exposure_samples_synthetic.json",
        "LicenseRef-fixture-mirrors-US-PD",
        "public_domain",
        True,
        "LANDFIRE-shaped canopy samples (shares a file with the 3DEP slope samples).",
    ),
    (
        REL.terrain,
        "fixture_3dep",
        "2026-11",
        "exposure_samples_synthetic.json",
        "LicenseRef-fixture-mirrors-US-PD",
        "public_domain",
        True,
        "3DEP-shaped slope samples (shares a file with the LANDFIRE canopy samples).",
    ),
    (
        REL.buildings,
        "fixture_overture_buildings",
        "2026-11",
        "footprint_rings_synthetic.json",
        "LicenseRef-fixture-mirrors-ODbL",
        "share_alike",
        True,
        "Footprint match and ring metrics; class mirrors ODbL.",
    ),
    (
        REL.community_lists,
        "fixture_community_lists",
        "2026-11",
        "community_lists_synthetic.json",
        "LicenseRef-fixture-unverified-terms",
        "restricted",
        False,
        "Firewise USA / FRRC-shaped lists. Real list terms are unverified [U], so the class is the "
        "stricter one.",
    ),
    (
        REL.regulation,
        "fixture_ccr_title10",
        "2022-10-14",
        "ccr_2644_9_d1_items.json",
        "LicenseRef-fixture-state-regulation",
        "public_domain",
        True,
        "Fixture copy of the 10 CCR 2644.9(d)(1) item list.",
    ),
    (
        REL.rubric,
        "fixture_p02_rubric",
        "2026-11-27",
        "p02_rubric_params.json",
        "LicenseRef-fixture-project-params",
        "permissive",
        True,
        "Product 02 rubric weights and thresholds.",
    ),
    (
        NC_MODEL,
        "fixture_nc_wildfire_model",
        "2026-01",
        "nc_wildfire_model_synthetic.json",
        "LicenseRef-fixture-noncommercial",
        "non_commercial",
        False,
        "Non-commercial stand-in, used to test license_blocked.",
    ),
)


def releases_yaml(sources: Mapping[str, str]) -> str:
    rows = []
    for rid, src, vintage, fname, spdx, cls, ok, note in RELEASES:
        path = f"{B}/{fname}"
        rows.append(
            {
                "release_id": rid,
                "source_id": src,
                "vintage": vintage,
                "url": f"fixture://{path}",
                "sha256": hashlib.sha256(sources[path].encode("utf-8")).hexdigest(),
                "license_spdx": spdx,
                "license_class": cls,
                "commercial_ok": ok,
                "retrieved_at": RETRIEVED_AT,
                "status": "pinned",
                "notes": f"SYNTHETIC {note}",
            }
        )
    header = (
        "# SYNTHETIC Product 02 fixture catalog for CI. Regenerate with `make fixtures-p02`; do "
        "not hand-edit.\n"
    )
    body: str = yaml.safe_dump({"releases": rows}, sort_keys=False, allow_unicode=True)
    return header + body


def load_catalog_text(text: str) -> dict[str, DatasetRelease]:
    raw: Any = yaml.safe_load(text)
    return {r["release_id"]: DatasetRelease.model_validate(r) for r in raw["releases"]}


def load_subjects(sources: Mapping[str, str]) -> list[Subject]:
    ik = json.loads(sources[f"{B}/intake_synthetic.json"])
    rings = {
        r["structure_id"]: r for r in json.loads(sources[f"{B}/footprint_rings_synthetic.json"])["structures"]
    }
    out = []
    for rec in ik["structures"]:
        ring = {k: v for k, v in rings[rec["structure_id"]].items() if k not in ("structure_id", "fixture")}
        out.append(subject_from_record(rec | ring))
    return out


def load_lists(sources: Mapping[str, str]) -> CommunityLists:
    raw = json.loads(sources[f"{B}/community_lists_synthetic.json"])
    return CommunityLists(
        firewise=frozenset(raw["firewise_usa_sites_in_good_standing"]),
        frrc=frozenset(raw["board_of_forestry_frrc"]),
    )


def load_samples(sources: Mapping[str, str]) -> list[ExposureSample]:
    raw = json.loads(sources[f"{B}/exposure_samples_synthetic.json"])
    return [ExposureSample(s["lat"], s["lon"], s["canopy_cover_pct"], s["slope_deg"]) for s in raw["samples"]]


def assess_all(
    sources: Mapping[str, str], catalog: Mapping[str, DatasetRelease], cell_of: CellOf
) -> list[P02Assessment]:
    subjects = load_subjects(sources)
    cells = aggregate_exposure(load_samples(sources), cell_of)
    exposure = join_exposure(((s.structure_id, s.lat, s.lon) for s in subjects), cells, cell_of)
    lists = load_lists(sources)
    return [assess(s, lists, exposure[s.structure_id], catalog, REL, as_of=AS_OF) for s in subjects]


def card(a: P02Assessment) -> dict[str, Any]:
    packet = build_appeal_packet(a)
    memo, findings = build_memo(a, packet, GENERATED_AT)
    return {
        "structure_id": a.subject_id,
        "structure_kind": a.structure_kind,
        "verdict": a.recommendation.verdict,
        "abstain_reasons": list(a.gate.reasons),
        "abstain_messages": [f.detail for f in a.gate.findings],
        "ready": a.ready_to_appeal,
        "score": None
        if a.score is None
        else {
            "total": a.score.total,
            "community": a.score.community,
            "surroundings": a.score.surroundings,
            "hardening": a.score.hardening,
        },
        "checklist": [
            {
                "item_id": r.item_id,
                "subdivision": r.subdivision,
                "label": r.label,
                "evidence": r.evidence,
                "strength": r.strength,
            }
            for r in a.checklist
        ],
        "open_data": {
            "naip_veg_0_5ft_pct": a.naip_veg_0_5ft_pct,
            "canopy_cover_pct": None if a.exposure is None else a.exposure.canopy_cover_pct,
            "slope_deg": None if a.exposure is None else a.exposure.slope_deg,
            "exposure_context": a.exposure_context,
        },
        "memo_md": memo.body_md,
        "grounding_passed": memo.grounding_passed and not findings,
        "letters": render_letters(a, packet),
    }


def derived_files(sources: Mapping[str, str], releases_text: str, cell_of: CellOf) -> dict[str, str]:
    catalog = load_catalog_text(releases_text)
    assessments = assess_all(sources, catalog, cell_of)
    by_id = {a.subject_id: a for a in assessments}
    out: dict[str, str] = {}
    for sid, stem in ((MEMO_SUBJECT, "p02_butte_memo"), (ABSTAIN_MEMO_SUBJECT, "p02_butte_abstain_memo")):
        a = by_id[sid]
        memo, findings = build_memo(a, build_appeal_packet(a), GENERATED_AT)
        if findings:
            raise SystemExit(f"{sid}: memo failed grounding: {findings}")
        out[f"tests/fixtures/memos/{stem}.md"] = memo.body_md
        out[f"tests/fixtures/memos/{stem.replace('_memo', '_features')}.json"] = dumps(features_payload(a))
    cards = {
        "_fixture_note": NOTE,
        "build_id": BUILD_ID,
        "as_of": AS_OF.isoformat(),
        "attribution": ATTRIBUTION,
        "cards": [card(a) for a in assessments],
    }
    out["web/p02-insurability-copilot/data/cards.json"] = dumps(cards)
    return out


def build_all(cell_of: CellOf) -> dict[str, str]:
    sources = source_files()
    rel_text = releases_yaml(sources)
    return {
        **sources,
        "tests/fixtures/releases_p02.fixture.yaml": rel_text,
        **derived_files(sources, rel_text, cell_of),
    }


def fake_grid(lat: float, lon: float) -> str:
    """Rounding grid (~100 m) for machines without h3. Gives the same join as H3 res 9 for these
    fixtures because samples sit exactly on structure points and decoys are kilometres away."""
    return f"fake:{round(lat, 3)}:{round(lon, 3)}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fake-grid", action="store_true", help="use a rounding grid instead of H3 res 9")
    ns = ap.parse_args(argv)
    cell_of: CellOf = fake_grid if ns.fake_grid else h3_r9
    for rel_path, text in build_all(cell_of).items():
        p = ROOT / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"wrote {rel_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
