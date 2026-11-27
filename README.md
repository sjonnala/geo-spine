# geo-spine

**One Spine, Six Products.** An H3-keyed geospatial spine: pinned data releases, deterministic kernels,
first-class abstention, and memos whose every number is checked against the data.

Wave G2 (this scaffold) ships the five bounded contexts, the release catalog, the CI guards, Kernel #1
(Isochrone Diff) and the Product 01 Santa Clara childcare **licensed-capacity gap** scaffold.
All Santa Clara data in `tests/fixtures/` is **synthetic**; the Valhalla isochrone fixture is hand-built,
not a recording from a Valhalla server.

## Layout
```
src/spine/
  catalog/    Source Catalog: DatasetRelease, Provenance, releases.yaml loader + publish gate (ADR-001)
  identity/   Spatial Identity: Parcel, Structure, Place, Facility; CDSS curation drops licensee names
  compute/    Kernels: Kernel #1 isochrone_diff, ADR-003 DuckDB SQL (adr003_sql)
  decision/   Score / Evidence / Recommendation, grounding_verifier (ADR-004), childcare_gap (Product 01)
  surface/    Tileset / Memo / ApiResource, p01_memo (licensed-capacity gap memo + FFN disclaimer)
data/catalog/releases.yaml        G-101 source catalog seed (all rows pending_download)
data/manifests/                   build manifests checked by the licence guard
docs/adr/ADR-001..005             architecture decisions (from G-102)
tools/ci/license_guard.py         ADR-005 licensing + privacy guard
tools/fixtures/                   deterministic generator for the synthetic fixtures
tests/                            pytest suite; tests/fixtures/ holds the synthetic Santa Clara data
```
Imports point one way only: **Catalog → Identity → Compute → Decision → Surface** (import-linter contract
in `pyproject.toml`, plus `tests/test_boundaries.py`).

## Run
```bash
python3 -m pip install -e ".[dev]"
make ci          # lint, typecheck, import boundaries, catalog, licence guard, memo grounding, pytest
make fixtures    # regenerate the synthetic fixtures and their pinned checksums
```
`tests/test_duckdb_adr003.py::test_adr003_sql_native_extensions` needs DuckDB's `spatial` and `h3`
extensions and skips (never fakes) when they can't be downloaded; the shim variant always runs.

## Attribution
Routing data, when built, is © OpenStreetMap contributors (ODbL-1.0). See `data/catalog/releases.yaml` for
each source's licence and attribution notes.
