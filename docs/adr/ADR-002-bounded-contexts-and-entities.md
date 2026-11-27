# ADR-002: Five bounded contexts and domain entities

- **Status:** Accepted (G-102 approved; implemented in G-201)

## Decision [D]
Five bounded contexts, one package each under `src/spine/`. **Dependencies point one way only:
Catalog → Identity → Compute → Decision → Surface.** A context may import any context to its left, never one
to its right.

| Context | Package | Owns | Key entities | Persisted as |
|---|---|---|---|---|
| Source Catalog | `spine.catalog` | Which data we may use, exactly which version | `DatasetRelease`, `Provenance` | `data/catalog/releases.yaml` |
| Spatial Identity | `spine.identity` | What a thing is and where | `Parcel`, `Structure`, `AddressAlias`, `Place`, `Facility` | `data/curated/*.parquet` |
| Compute | `spine.compute` | Deterministic kernels | `Catchment`, `HazardExposure`, `EmbeddingDelta` | `data/features/<kernel>/<method_ver>/*.parquet` |
| Decision | `spine.decision` | Scores and recommendations, incl. abstention | `Score`, `Evidence`, `Recommendation` | `data/decisions/<product>/<build_id>.parquet` |
| Surface | `spine.surface` | What users see | `Tileset`, `Memo`, `ApiResource` | `tiles/`, `memos/`, static JSON |

**First-class "We don't know":** `Recommendation.verdict` is `recommend`, `do_not_recommend` or `abstain`.
`abstain` requires an `abstain_reason` (`insufficient_coverage`, `stale_release`, `conflicting_evidence`,
`out_of_domain`, `license_blocked`); a non-abstaining recommendation requires at least one `Evidence` row.

## Table contract [D]
```sql
-- curated.facility (GeoParquet, geometry column 'geom', CRS OGC:CRS84 / EPSG:4326)
facility_id VARCHAR PRIMARY KEY, gers_id VARCHAR, kind VARCHAR, licensed_capacity INTEGER,
status VARCHAR, location_precision VARCHAR, h3_r8 VARCHAR NOT NULL, geom GEOMETRY,
release_id VARCHAR NOT NULL, method_ver VARCHAR NOT NULL, build_id VARCHAR NOT NULL, license_class VARCHAR NOT NULL

-- features.catchment_cells (one row per origin x minutes x member cell)
catchment_id VARCHAR, origin_h3_r8 VARCHAR, mode VARCHAR, minutes INTEGER, member_h3_r8 VARCHAR,
release_ids VARCHAR[], method_ver VARCHAR, build_id VARCHAR, license_class VARCHAR

-- decisions.recommendation
recommendation_id VARCHAR, subject_id VARCHAR, verdict VARCHAR, abstain_reason VARCHAR,
rationale_md VARCHAR, evidence_ids VARCHAR[], build_id VARCHAR
```
GeoParquet files carry the `geo` metadata key. Storage CRS is OGC:CRS84; metric computation reprojects to
EPSG:3310 (California Albers).

## G-201 enforcement
- **Import boundaries:** an import-linter `layers` contract in `pyproject.toml` (`make boundaries`, i.e.
  `lint-imports`) plus an AST check in `tests/test_boundaries.py` so the rule also holds wherever only pytest
  runs. Both include a negative test.
- Entities live in `src/spine/<context>/models.py` and keep the G-102 validators (tested).
- The curated facility fixture is written in exactly the column order above (tested).
