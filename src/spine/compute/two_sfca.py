"""Kernel #2, Two-Step Floating Catchment Area (2SFCA), Product 01 (G-103 section 1.2).

Luo & Wang 2003 (2SFCA); optional distance-decay weights in the style of Luo & Qi 2009 (E2SFCA).

Both steps read ONE origin-destination travel-time table ``t[(demand_cell, facility)]``, so the
catchment relation is identical in step 1 and step 2. That symmetry is what makes seats conserve:

    sum_i P_i * A_i == sum_j S_j      (over facilities with >= 1 populated cell in reach)

    Step 1: R_j = S_j / sum_{k: t_kj <= d0} w(t_kj) * P_k
    Step 2: A_i = sum_{j: t_ij <= d0} w(t_ij) * R_j          (seats per child)
    allocated_i = P_i * A_i ; gap_i = P_i - allocated_i

A facility no populated cell can reach is an *orphan*: its seats are reported, never spread.
A cell no facility reaches gets ``A_i = 0`` and ``gap_i = P_i``. ``A_i > 1`` is a surplus and is
reported as is. Unlike the PR #1 catchment ratio, overlapping catchments share each seat instead
of counting it once per origin that reaches it.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass

METHOD_VER = "0.2.0"
DEFAULT_D0_MIN = 15.0

Weight = Callable[[float], float]
TravelTable = Mapping[tuple[str, str], float]


def binary(_: float) -> float:
    """v0.2.0 weight: every reachable pair counts fully."""
    return 1.0


def gaussian_decay(d0: float) -> Weight:
    """E2SFCA-style decay with w(0) = 1 (a v0.3.0 option; conservation still holds)."""

    def w(t: float) -> float:
        return math.exp(-0.5 * (t / (d0 / 2)) ** 2)

    return w


@dataclass(frozen=True)
class TwoSFCAResult:
    d0: float
    ratio_by_facility: dict[str, float]  # R_j
    access_by_cell: dict[str, float]  # A_i, seats per child
    allocated_by_cell: dict[str, float]  # P_i * A_i
    orphan_facilities: tuple[str, ...]  # facilities with no populated cell in reach

    def gap(self, demand: Mapping[str, int]) -> dict[str, float]:
        return {c: demand[c] - self.allocated_by_cell.get(c, 0.0) for c in demand}

    @property
    def total_allocated(self) -> float:
        return math.fsum(self.allocated_by_cell.values())


def two_sfca(
    supply: Mapping[str, int],
    demand: Mapping[str, int],
    travel_min: TravelTable,
    d0: float = DEFAULT_D0_MIN,
    weight: Weight = binary,
) -> TwoSFCAResult:
    if d0 <= 0:
        raise ValueError("d0 must be positive minutes")
    if any(s < 0 for s in supply.values()) or any(p < 0 for p in demand.values()):
        raise ValueError("supply and demand must be non-negative")
    denom: dict[str, float] = {j: 0.0 for j in supply}
    for (i, j), t in travel_min.items():
        if t <= d0 and j in denom and i in demand:
            denom[j] += weight(t) * demand[i]
    ratio = {j: supply[j] / d for j, d in denom.items() if d > 0}
    orphans = tuple(sorted(j for j, d in denom.items() if d <= 0))
    access = {i: 0.0 for i in demand}
    for (i, j), t in travel_min.items():
        if t <= d0 and j in ratio and i in access:
            access[i] += weight(t) * ratio[j]
    allocated = {i: demand[i] * a for i, a in access.items()}
    return TwoSFCAResult(d0, ratio, access, allocated, orphans)


def facilities_in_reach(cell: str, travel_min: TravelTable, d0: float = DEFAULT_D0_MIN) -> tuple[str, ...]:
    return tuple(sorted(j for (i, j), t in travel_min.items() if i == cell and t <= d0))


def simple_ratio_seat_count(
    supply: Mapping[str, int], demand: Mapping[str, int], travel_min: TravelTable, d0: float = DEFAULT_D0_MIN
) -> int:
    """PR #1's catchment ratio, kept only as a diagnostic: each origin counts every seat in its own
    catchment, so summed over origins a seat is counted once per origin that reaches it."""
    return sum(supply[j] for (i, j), t in travel_min.items() if t <= d0 and i in demand and j in supply)
