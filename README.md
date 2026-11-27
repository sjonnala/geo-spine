# geo-spine

**One Spine, Six Products.** An H3-keyed geospatial spine: pinned data releases, deterministic kernels,
first-class abstention, and memos whose every number is checked against the data.

Wave G2 shipped the five bounded contexts, the release catalog, the CI guards, Kernel #1 (Isochrone Diff)
and the Product 01 Santa Clara childcare **licensed-capacity gap** scaffold. Wave G3 (G-301) moves Product 01
to **2SFCA** (Kernel #2), adds licence rule L4 for restricted inputs, a pinned Valhalla compose file with a
replayable HTTP client, and a static MapLibre + PMTiles viewer. Wave G4 (G-302) adds Product 02, the
California **Insurability Copilot**, on the same spine.

All Santa Clara data in `tests/fixtures/` is **synthetic**. The Valhalla isochrone fixture and the
origin-destination matrix cassette are hand-built, not recordings from a Valhalla server. The Butte County
Product 02 data in `tests/fixtures/butte/` is synthetic too.

## Product 02: Insurability Copilot
A homeowner tool for 10 CCR § 2644.9, California's "Safer from Wildfires" rule. It is not a risk score.
- `compute.wildfire_mitigation` scores how well the 12 § 2644.9(d)(1) mitigation items are documented
  (open data counts most, then a photo-backed attestation, then a plain one), and joins LANDFIRE canopy and
  3DEP slope to the structure's H3 res-9 cell. Cell ids stay internal.
- `decision.insurability_copilot` takes an allow-listed intake (no names, APNs or addresses), runs a
  five-reason abstention gate (out_of_domain, license_blocked, insufficient_coverage, stale_release,
  conflicting_evidence), and builds the appeal packet and the (h), (h)(4) and (i) deadlines.
- `surface.p02_memo` writes the evidence memo and draft letters. Every figure, regulation number and rubric
  parameter is a row of a pinned release, so ADR-004 grounding checks them all.
- `web/p02-insurability-copilot/` is a zero-build viewer. Its deadline calendar mirrors the Python one and
  is parity-tested through node. It never contacts an insurer; the homeowner sends every letter.

## Why 2SFCA
The Wave G2 ratio gave each cell every seat within 15 minutes, so a seat reachable from five cells was
counted five times. 2SFCA (Luo & Wang 2003) first divides each facility's licensed seats by all children who
can reach it, then sums those shares per cell. Summed over cells, allocated seats equal the licensed seats of
reachable facilities exactly; `tests/test_childcare_gap.py` proves it on the fixtures. Facilities no cell can
reach are reported as orphans, not allocated.

## Layout
```
src/spine/
  catalog/    Source Catalog: DatasetRelease, Provenance, releases.yaml loader + publish gate (ADR-001)
  identity/   Spatial Identity: Parcel, Structure, Place, Facility; CDSS curation drops licensee names
  compute/    Kernels: #1 isochrone_diff, #2 two_sfca; valhalla_client (live/record/replay); adr003_sql
  compute/    ... wildfire_mitigation (Product 02 documentation scorer + res-9 exposure join)
  decision/   Score / Evidence / Recommendation, grounding_verifier (ADR-004), childcare_gap (Product 01),
              insurability_copilot (Product 02 gate, appeal packet, deadlines)
  surface/    Tileset / Memo / ApiResource, p01_memo (gap memo + FFN disclaimer), p01_tiles (map export),
              p02_memo (evidence memo + draft letters)
data/catalog/releases.yaml        G-101 source catalog seed (all rows pending_download)
data/manifests/                   build manifests checked by the licence guard
docs/adr/ADR-001..005             architecture decisions (from G-102)
tools/ci/license_guard.py         ADR-005 licensing + privacy guard (L1-L4, P1-P2)
docker/valhalla/compose.yaml      pinned Valhalla 3.9.3 (amd64 + arm64), Oracle A1 sizing notes
web/p01-access-gap/               static MapLibre GL JS + PMTiles viewer for Product 01
web/p02-insurability-copilot/     zero-build appeal-card viewer for Product 02
tests/fixtures/valhalla/cassettes/ replay recordings for the Valhalla client (synthetic in CI)
tools/fixtures/                   deterministic generator for the synthetic fixtures
tests/                            pytest suite; tests/fixtures/ holds the synthetic Santa Clara data
```
Imports point one way only: **Catalog → Identity → Compute → Decision → Surface** (import-linter contract
in `pyproject.toml`, plus `tests/test_boundaries.py`).

## Run
```bash
python3 -m pip install -e ".[dev]"
make ci          # lint, typecheck, import boundaries, catalog, licence guard, memo grounding, pytest
make fixtures    # regenerate the synthetic fixtures, cassette, viewer data and pinned checksums
make fixtures-p02 # regenerate the synthetic Butte County fixtures, memos and viewer cards (needs h3)
make tiles       # build tiles/01/fixture-g301.pmtiles (needs tippecanoe)
make valhalla-up # start a local Valhalla (needs Docker and an OSM extract in docker/valhalla/custom_files)
```
The Valhalla client runs in `replay` mode unless `VALHALLA_MODE=live` or `record` is set; CI only replays.
`tests/test_duckdb_adr003.py::test_adr003_sql_native_extensions` needs DuckDB's `spatial` and `h3`
extensions and skips (never fakes) when they can't be downloaded; the shim variant always runs.

## Attribution
Routing data, when built, is © OpenStreetMap contributors (ODbL-1.0). See `data/catalog/releases.yaml` for
each source's licence and attribution notes.
