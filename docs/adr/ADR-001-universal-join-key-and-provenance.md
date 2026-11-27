# ADR-001: Universal join key and provenance

- **Status:** Accepted (G-102 approved by the Director; implemented in G-201)
- **Source:** `Spine-ADRs-and-Contracts.md` (G-102) · tags: [V] verified, [V2] two sources, [D] decision, [U] unverified

## Context
Six products must share one spatial index so that a new product costs a kernel, not a new pipeline.

## Decision
1. **The join key is H3 resolution 8**, stored as the 15-character hex string `h3_r8`. Average hexagon
   area: res 7 = 5.161293360 km², res 8 = 0.737327598 km², res 9 = 0.105332513 km²; 7 children per step
   (pentagons 6) [V] <https://h3geo.org/docs/core-library/restable/>.
2. **Rollups [D]**
   - Up (res 9 → 8 → 7) with `h3_cell_to_parent`. Counts are summed; rates are re-derived from summed
     numerators and denominators, never averaged.
   - Down with `h3_cell_to_children`, allocating only by an explicit weight column. Never a uniform 1/7 split.
   - Structure-level data (02 Insurability, 03 Survivor) at res 9; facility, catchment and demand data (01)
     at res 8; regional dashboards at res 7.
   - H3 cells are not equal-area: area-normalised metrics use the actual `h3_cell_area`, never a constant.
3. **DatasetRelease pinning [D].** Every input is a row in `data/catalog/releases.yaml` with `release_id`,
   `source_id`, `vintage`, `url`, `sha256`, `license_spdx`, `license_class`, `commercial_ok`. CI fails when a
   `url`, `vintage` or `release_id` contains `latest`, when a download's SHA-256 differs from the pin, or when
   code references a `release_id` not in the catalog.
4. **Row-level provenance [D].** Every curated or feature table carries `release_id` (or a sorted
   `release_ids` list), `method_ver` (kernel semver), `build_id` and `license_class`.

## G-201 implementation notes
- `spine.catalog.models.DatasetRelease` enforces the `latest` rule and the release_id pattern.
- **Seed rows [D, new in G-201]:** the G-101 catalog has landing-page URLs and no checksums yet, so rows carry
  `status: pending_download` with `sha256: null`. `spine.catalog.releases.assert_publishable` refuses any
  pending or unknown release, so a pending row can never feed a published build. A `pinned` row must have
  `sha256` and `retrieved_at`.
- CI validates both catalogs with `make catalog`. The synthetic fixture catalog
  (`tests/fixtures/releases.fixture.yaml`) is fully pinned and its checksums are tested against the committed files.
- Checksum verification of real downloads arrives with the first ingest task; there is no download code yet.

## Consequences
Joins are string equality, fast in DuckDB, and products can be added without touching the spine. The cost is
quantisation error at boundaries, which ADR-003's isochrone kernel bounds by computing on polygons first and
indexing to H3 second.
