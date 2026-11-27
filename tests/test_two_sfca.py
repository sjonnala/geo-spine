"""Kernel #2 (2SFCA) on the G-103 synthetic toy grid: NOT H3 and NOT Santa Clara data.

A 6x6 grid of demand cells with a 'freeway' barrier between rows 2 and 3, crossable only at
column 5. Travel time = 3 minutes per grid step along the shortest path (BFS)."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator

import pytest

from spine.compute.two_sfca import (
    METHOD_VER,
    facilities_in_reach,
    gaussian_decay,
    simple_ratio_seat_count,
    two_sfca,
)

N, STEP_MIN, D0 = 6, 3.0, 15.0


def cell(r: int, c: int) -> str:
    return f"r{r}c{c}"


def neighbours(r: int, c: int) -> Iterator[tuple[int, int]]:
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        rr, cc = r + dr, c + dc
        if not (0 <= rr < N and 0 <= cc < N):
            continue
        if {r, rr} == {2, 3} and c != 5:  # barrier: only column 5 crosses
            continue
        yield rr, cc


def travel_from(r0: int, c0: int) -> dict[str, float]:
    dist = {(r0, c0): 0}
    q = deque([(r0, c0)])
    while q:
        r, c = q.popleft()
        for n in neighbours(r, c):
            if n not in dist:
                dist[n] = dist[(r, c)] + 1
                q.append(n)
    return {cell(r, c): d * STEP_MIN for (r, c), d in dist.items()}


DEMAND = {cell(r, c): 40 + 10 * ((r * 7 + c * 3) % 5) for r in range(N) for c in range(N)}
FACILITIES = {"F_north": (1, 1, 120), "F_south": (4, 1, 60), "F_east": (2, 5, 90)}
SUPPLY = {f: s for f, (_, _, s) in FACILITIES.items()}
T = {(i, f): m for f, (r, c, _) in FACILITIES.items() for i, m in travel_from(r, c).items()}


def test_method_version() -> None:
    assert METHOD_VER == "0.2.0"


def test_seats_conserved() -> None:
    r = two_sfca(SUPPLY, DEMAND, T, D0)
    assert r.orphan_facilities == ()
    assert r.total_allocated == pytest.approx(sum(SUPPLY.values()), abs=1e-9)


def test_seats_conserved_with_distance_decay() -> None:
    r = two_sfca(SUPPLY, DEMAND, T, D0, weight=gaussian_decay(D0))
    assert r.total_allocated == pytest.approx(sum(SUPPLY.values()), abs=1e-9)


def test_simple_ratio_double_counts() -> None:
    assert simple_ratio_seat_count(SUPPLY, DEMAND, T, D0) == 5670  # G-103 toy figure, 21x real supply
    assert sum(SUPPLY.values()) == 270


def test_barrier_cells_get_less_access() -> None:
    r = two_sfca(SUPPLY, DEMAND, T, D0)
    assert r.access_by_cell["r3c0"] < r.access_by_cell["r1c0"]
    assert round(r.access_by_cell["r3c0"], 4) == 0.0566 and round(r.access_by_cell["r1c0"], 4) == 0.1111
    assert facilities_in_reach("r3c0", T, D0) == ("F_south",)


def test_orphan_facility_reported_not_allocated() -> None:
    r = two_sfca(dict(SUPPLY, F_island=50), DEMAND, T, D0)  # no travel rows reach F_island
    assert r.orphan_facilities == ("F_island",)
    assert r.total_allocated == pytest.approx(sum(SUPPLY.values()), abs=1e-9)


def test_unreached_cell_gets_zero_access_and_full_gap() -> None:
    demand = dict(DEMAND, far_away=30)
    r = two_sfca(SUPPLY, demand, T, D0)
    assert r.access_by_cell["far_away"] == 0.0 and r.gap(demand)["far_away"] == 30


def test_surplus_reported_as_is() -> None:
    r = two_sfca({"F": 100}, {"a": 10, "b": 10}, {("a", "F"): 5.0, ("b", "F"): 5.0}, D0)
    assert r.access_by_cell == {"a": 5.0, "b": 5.0}
    assert r.gap({"a": 10, "b": 10}) == {"a": -40.0, "b": -40.0}


def test_gap_definition() -> None:
    r = two_sfca(SUPPLY, DEMAND, T, D0)
    assert sum(r.gap(DEMAND).values()) == pytest.approx(sum(DEMAND.values()) - sum(SUPPLY.values()), abs=1e-9)


@pytest.mark.parametrize(
    ("supply", "demand", "d0"),
    [({"F": -1}, {"a": 1}, D0), ({"F": 1}, {"a": -1}, D0), ({"F": 1}, {"a": 1}, 0)],
)
def test_rejects_bad_inputs(supply: dict[str, int], demand: dict[str, int], d0: float) -> None:
    with pytest.raises(ValueError):
        two_sfca(supply, demand, {("a", "F"): 1.0}, d0)
