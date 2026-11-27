"""Kernel #3, wildfire mitigation documentation (Product 02, Compute context).

1. The 12 mitigation items of 10 CCR § 2644.9(d)(1), the Safer from Wildfires regulation (filed and
   operative 2022-10-14), in the regulation's own wording (G-103 2.2): 2 community items, 5 for the
   immediate surroundings and 5 for building hardening. Product 02 scores against the regulation, not
   CDI's consumer "10 steps" summary.
2. Evidence per item: ``open_data_observed`` 1.0, ``owner_attested_with_photo`` 0.8, ``owner_attested``
   0.5, ``unknown`` 0 (G-103 2.3). Open data can upgrade an item (a pinned Firewise list, a clear NAIP
   0 to 5 ft ring) and can contradict an attestation (``conflicting_items``).
3. Documentation Score, 0 to 100: community 20 (10 per item), surroundings 40 (8 each), hardening 40
   (8 each), each item's points times its evidence strength. It measures how well the mitigation is
   documented, never wildfire risk; insurer models are proprietary (G-103 2.1).
4. Exposure join at H3 res 9: LANDFIRE canopy cover and 3DEP slope samples are averaged per res-9
   cell and joined to each structure point. Res-9 cell ids are household-scale, so they stay inside
   compute and decision and are never written to a published artifact (ADR-005 P2).

Arithmetic is in integer tenths, so scores are exact to one decimal. Deterministic, no I/O.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

METHOD_VER = "0.1.0"
RES = 9

Block = Literal["community", "surroundings", "hardening"]
EvidenceKind = Literal["open_data_observed", "owner_attested_with_photo", "owner_attested", "unknown"]
EVIDENCE_KINDS: tuple[EvidenceKind, ...] = (
    "open_data_observed",
    "owner_attested_with_photo",
    "owner_attested",
    "unknown",
)
OWNER_KINDS: frozenset[str] = frozenset({"owner_attested_with_photo", "owner_attested", "unknown"})
STRENGTH_TENTHS: dict[EvidenceKind, int] = {
    "open_data_observed": 10,
    "owner_attested_with_photo": 8,
    "owner_attested": 5,
    "unknown": 0,
}
BLOCKS: tuple[Block, ...] = ("community", "surroundings", "hardening")
ITEM_POINTS: dict[Block, int] = {"community": 10, "surroundings": 8, "hardening": 8}
BLOCK_MAX: dict[Block, int] = {"community": 20, "surroundings": 40, "hardening": 40}
SCORE_MAX = 100

# NAIP vegetation share in the 0 to 5 ft ring around the footprint [D, review thresholds].
# At or below CLEAR the ring counts as open-data evidence for `surround_5ft`; at or above CONFLICT an
# owner attestation of a cleared ring is contradicted. NAIP is 60 cm, so the ring is coarse.
MAX_VEG_5FT_PCT_CLEAR = 10.0
MIN_VEG_5FT_PCT_CONFLICT = 25.0


@dataclass(frozen=True)
class MitigationItem:
    item_id: str
    subdivision: str  # position in 10 CCR § 2644.9(d)(1)
    block: Block
    label: str  # short label used on surfaces
    regulation_text: str  # the regulation's wording (G-103 2.2, read on the LII copy)

    @property
    def points(self) -> int:
        return ITEM_POINTS[self.block]


MITIGATIONS: tuple[MitigationItem, ...] = (
    MitigationItem(
        "community_frrc",
        "(d)(1)(A)",
        "community",
        "Fire Risk Reduction Community",
        "Fire Risk Reduction Community listed by the Board of Forestry (PRC § 4290.1)",
    ),
    MitigationItem(
        "community_firewise",
        "(d)(1)(A)",
        "community",
        "Firewise USA site in good standing",
        "Firewise USA Site in Good Standing",
    ),
    MitigationItem(
        "surround_under_deck",
        "(d)(1)(B)1.a",
        "surroundings",
        "Cleared vegetation and debris under decks",
        "Clearing vegetation and debris under decks",
    ),
    MitigationItem(
        "surround_5ft",
        "(d)(1)(B)1.b",
        "surroundings",
        "Cleared within 5 ft of the building",
        "Clearing within five (5) feet of the building",
    ),
    MitigationItem(
        "surround_fence_5ft",
        "(d)(1)(B)1.c",
        "surroundings",
        "Only noncombustible fences and gates within 5 ft",
        "Only noncombustible fences and gates within five feet",
    ),
    MitigationItem(
        "surround_30ft_structures",
        "(d)(1)(B)1.d",
        "surroundings",
        "No combustible structures within 30 ft",
        "Removal of combustible structures within thirty (30) feet",
    ),
    MitigationItem(
        "surround_defensible_space",
        "(d)(1)(B)1.e",
        "surroundings",
        "Defensible space per state law and local ordinance",
        "Compliance with PRC § 4291 and local defensible-space ordinances",
    ),
    MitigationItem(
        "harden_class_a_roof",
        "(d)(1)(B)2.a",
        "hardening",
        "Class-A fire rated roof",
        "Class-A Fire Rated Roof",
    ),
    MitigationItem(
        "harden_enclosed_eaves",
        "(d)(1)(B)2.b",
        "hardening",
        "Enclosed eaves",
        "Enclosed Eaves",
    ),
    MitigationItem(
        "harden_vents",
        "(d)(1)(B)2.c",
        "hardening",
        "Fire-resistant vents",
        "Fire-Resistant Vents",
    ),
    MitigationItem(
        "harden_windows",
        "(d)(1)(B)2.d",
        "hardening",
        "Multipane windows or functional shutters",
        "Multipane windows, including dual pane windows, or functional shutters",
    ),
    MitigationItem(
        "harden_6in_clearance",
        "(d)(1)(B)2.e",
        "hardening",
        "6 in of noncombustible clearance at the wall base",
        "At least six (6) inches of noncombustible vertical clearance at the bottom of the exterior surface",
    ),
)
ITEMS_BY_ID: dict[str, MitigationItem] = {m.item_id: m for m in MITIGATIONS}


@dataclass(frozen=True)
class OpenDataObservation:
    """What pinned open data says about one structure (``None`` = no data for that signal)."""

    naip_veg_0_5ft_pct: float | None = None  # from the footprint ring table (ODbL footprints)
    firewise_listed: bool | None = None  # community on the pinned Firewise USA list
    frrc_listed: bool | None = None  # community on the pinned Board of Forestry FRRC list


def _check_attested_evidence(owner: Mapping[str, str]) -> None:
    unknown = sorted(set(owner) - set(ITEMS_BY_ID))
    if unknown:
        raise ValueError(f"not a 10 CCR 2644.9(d)(1) item: {unknown}")
    bad = sorted(k for k, v in owner.items() if v not in OWNER_KINDS)
    if bad:
        # An owner can attest, with or without a photo; only pinned open data is "observed".
        raise ValueError(f"invalid owner evidence kind for {bad}")


def resolve_evidence(owner: Mapping[str, str], obs: OpenDataObservation) -> dict[str, EvidenceKind]:
    """Final evidence kind per item: open-data observation where it exists, else the owner's."""
    _check_attested_evidence(owner)
    out: dict[str, EvidenceKind] = {}
    for m in MITIGATIONS:
        kind = owner.get(m.item_id, "unknown")
        if kind == "owner_attested_with_photo":
            out[m.item_id] = "owner_attested_with_photo"
        elif kind == "owner_attested":
            out[m.item_id] = "owner_attested"
        else:
            out[m.item_id] = "unknown"
    veg = obs.naip_veg_0_5ft_pct
    if veg is not None and veg <= MAX_VEG_5FT_PCT_CLEAR:
        out["surround_5ft"] = "open_data_observed"
    if obs.firewise_listed:
        out["community_firewise"] = "open_data_observed"
    if obs.frrc_listed:
        out["community_frrc"] = "open_data_observed"
    return out


def conflicting_items(owner: Mapping[str, str], obs: OpenDataObservation) -> tuple[str, ...]:
    """Items the owner attests that pinned open data contradicts (in checklist order)."""
    _check_attested_evidence(owner)

    def attested(item_id: str) -> bool:
        return owner.get(item_id, "unknown") != "unknown"

    out: list[str] = []
    if obs.frrc_listed is False and attested("community_frrc"):
        out.append("community_frrc")
    if obs.firewise_listed is False and attested("community_firewise"):
        out.append("community_firewise")
    veg = obs.naip_veg_0_5ft_pct
    if veg is not None and veg >= MIN_VEG_5FT_PCT_CONFLICT and attested("surround_5ft"):
        out.append("surround_5ft")
    return tuple(out)


@dataclass(frozen=True)
class ItemScore:
    item_id: str
    block: Block
    evidence: EvidenceKind
    strength: float  # 1.0, 0.8, 0.5 or 0.0
    points: float  # item points x strength


@dataclass(frozen=True)
class DocumentationScore:
    """Documentation completeness, 0 to 100. Not a risk score."""

    total: float
    community: float
    surroundings: float
    hardening: float
    items: tuple[ItemScore, ...]

    def block(self, b: Block) -> float:
        return {"community": self.community, "surroundings": self.surroundings, "hardening": self.hardening}[
            b
        ]

    @property
    def items_with_evidence(self) -> int:
        return sum(1 for i in self.items if i.evidence != "unknown")


def documentation_score(evidence: Mapping[str, EvidenceKind]) -> DocumentationScore:
    missing = [m.item_id for m in MITIGATIONS if m.item_id not in evidence]
    if missing:
        raise ValueError(f"evidence missing for {missing}")
    tenths: dict[Block, int] = dict.fromkeys(BLOCKS, 0)
    items: list[ItemScore] = []
    for m in MITIGATIONS:
        kind = evidence[m.item_id]
        t = m.points * STRENGTH_TENTHS[kind]
        tenths[m.block] += t
        items.append(ItemScore(m.item_id, m.block, kind, STRENGTH_TENTHS[kind] / 10, t / 10))
    return DocumentationScore(
        total=sum(tenths.values()) / 10,
        community=tenths["community"] / 10,
        surroundings=tenths["surroundings"] / 10,
        hardening=tenths["hardening"] / 10,
        items=tuple(items),
    )


# --- exposure join at H3 res 9 ----------------------------------------------------------------------

CellOf = Callable[[float, float], str]


def h3_r9(lat: float, lon: float) -> str:
    """Default cell function. h3 is imported lazily so the scorer itself stays dependency-free."""
    import h3

    return str(h3.latlng_to_cell(lat, lon, RES))


@dataclass(frozen=True)
class ExposureSample:
    """One raster sample point (cell centre of a LANDFIRE / 3DEP pixel), in WGS84."""

    lat: float
    lon: float
    canopy_cover_pct: float  # LANDFIRE canopy cover
    slope_deg: float  # derived from the 3DEP DEM


@dataclass(frozen=True)
class CellExposure:
    h3_r9: str
    canopy_cover_pct: float
    slope_deg: float
    samples: int


@dataclass(frozen=True)
class StructureExposure:
    structure_id: str
    h3_r9: str  # internal only: never exported (household-scale)
    canopy_cover_pct: float
    slope_deg: float
    samples: int


def aggregate_exposure(samples: Iterable[ExposureSample], cell_of: CellOf = h3_r9) -> dict[str, CellExposure]:
    acc: dict[str, list[ExposureSample]] = defaultdict(list)
    for s in samples:
        acc[cell_of(s.lat, s.lon)].append(s)
    return {
        c: CellExposure(
            h3_r9=c,
            canopy_cover_pct=round(sum(s.canopy_cover_pct for s in ss) / len(ss), 1),
            slope_deg=round(sum(s.slope_deg for s in ss) / len(ss), 1),
            samples=len(ss),
        )
        for c, ss in sorted(acc.items())
    }


def join_exposure(
    structures: Iterable[tuple[str, float, float]],
    cells: Mapping[str, CellExposure],
    cell_of: CellOf = h3_r9,
) -> dict[str, StructureExposure | None]:
    """(structure_id, lat, lon) -> exposure of its res-9 cell, or None when no sample fell there."""
    out: dict[str, StructureExposure | None] = {}
    for sid, lat, lon in structures:
        c = cells.get(cell_of(lat, lon))
        out[sid] = (
            None if c is None else StructureExposure(sid, c.h3_r9, c.canopy_cover_pct, c.slope_deg, c.samples)
        )
    return out


ExposureContext = Literal["lower", "elevated", "high"]
# Open-data context tiers [D, review]. Shown as words next to the canopy and slope figures, never as
# a number: insurer wildfire scores are proprietary and Product 02 does not imitate one.
HIGH_CANOPY_PCT, HIGH_SLOPE_DEG = 50.0, 30.0
ELEVATED_CANOPY_PCT, ELEVATED_SLOPE_DEG = 25.0, 15.0


def exposure_context(e: StructureExposure) -> ExposureContext:
    if e.canopy_cover_pct >= HIGH_CANOPY_PCT or e.slope_deg >= HIGH_SLOPE_DEG:
        return "high"
    if e.canopy_cover_pct >= ELEVATED_CANOPY_PCT or e.slope_deg >= ELEVATED_SLOPE_DEG:
        return "elevated"
    return "lower"
