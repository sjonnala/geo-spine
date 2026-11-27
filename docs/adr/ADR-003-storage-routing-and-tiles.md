# ADR-003: Storage, routing and zero-server tiles

- **Status:** Accepted (G-102 approved; SQL and Kernel #1 implemented in G-201)

## Directory layout [D]
```
data/
  catalog/releases.yaml                 # the only place a URL may appear
  raw/<source_id>/<release_id>/...      # immutable, checksum-verified, gitignored
  curated/<entity>.parquet              # Identity context, GeoParquet
  features/<kernel>/<method_ver>/*.parquet
  decisions/<product>/<build_id>.parquet
  manifests/*.json                      # build manifests checked by tools/ci/license_guard.py
quarantine/nc/                          # non-commercial-licensed derivatives only (ADR-005)
tiles/<product>/<build_id>.pmtiles      # static, served from object storage / GitHub Pages
memos/<product>/<build_id>/*.md         # each passes ADR-004 before publish
tests/fixtures/                         # tiny SYNTHETIC Santa Clara fixtures for CI (seconds, no downloads)
```

## DuckDB query patterns
Extensions: `INSTALL spatial; LOAD spatial; INSTALL h3 FROM community; LOAD h3;` [V]
<https://duckdb.org/community_extensions/extensions/h3.html>. The queries live in
`src/spine/compute/adr003_sql.py` with input paths as parameters:

```sql
-- index facilities
CREATE OR REPLACE TABLE curated_facility AS
SELECT *, h3_latlng_to_cell(ST_Y(geom), ST_X(geom), 8) AS h3_r8_int FROM read_parquet(<facility>);
-- the integer must round-trip to the stored hex key
SELECT facility_id, h3_r8, h3_h3_to_string(h3_r8_int) FROM curated_facility;
-- seats per res-7 parent (sum counts, never average rates)
SELECT h3_h3_to_string(h3_cell_to_parent(h3_r8_int, 7)) AS h3_r7, SUM(licensed_capacity) AS seats
FROM curated_facility GROUP BY 1;
-- catchment demand: children within N minutes of each origin cell
SELECT c.origin_h3_r8, c.minutes, SUM(d.children_0_5) AS demand
FROM read_parquet(<catchment_cells>) c JOIN read_parquet(<children>) d ON d.h3_r8 = c.member_h3_r8
GROUP BY 1, 2;
```
The extension returns UBIGINT cells; published tables store the hex string (`h3_h3_to_string`) so IDs
round-trip through JSON and JavaScript [D].

**Execution status (G-201):** `tests/test_duckdb_adr003.py` runs these queries on the synthetic Santa Clara
GeoParquet fixtures two ways, each checked against an independent pure-Python h3 computation:
- *native* (real `spatial` + `h3` extensions): needs extension downloads. Skipped, never faked, where the
  network blocks `extensions.duckdb.org` / `community-extensions.duckdb.org`. GitHub Actions can reach them.
- *shim*: the same SQL in DuckDB core with test-only Python UDFs standing in for the five extension functions
  (`tests/support/duckdb_shim.py`). It proves the SQL's joins and rollups, not the extensions themselves.

Note: DuckDB 2.x reads GeoParquet into a core `GEOMETRY` type even without `spatial`.

## Routing: Valhalla in Docker [D template]
```yaml
# docker/valhalla/compose.yaml
services:
  valhalla:
    image: ghcr.io/valhalla/valhalla-scripted:3.9.3   # pin a version, never :latest (ADR-001)
    platform: linux/arm64                             # Oracle Ampere / Apple Silicon; drop on x86
    ports: ["8002:8002"]                              # usual Valhalla service port [U]
    volumes: ["./custom_files:/custom_files"]
    environment:
      tile_urls: "${OSM_PBF_URL}"   # a dated Geofabrik extract registered in releases.yaml, never *-latest
      server_threads: "2"           # lower this if the tile build is OOM-killed
      build_elevation: "False"
```
Images and ARM64 tags: G-101 Q7 [V]. **Sizing correction (G-101):** Oracle Always Free Ampere A1 is now
**2 OCPU / 12 GB** (was 4 OCPU / 24 GB), 200 GB storage [V2]. Build tiles on the Mac, serve prebuilt tiles on
the VM, and rebuild there only for Bay Area-sized extracts. The compose file is not committed yet.

**CI never builds tiles or calls Valhalla.** Tests use `tests/fixtures/valhalla/isochrone_santa_clara_synthetic.json`,
a **hand-built synthetic stand-in** for an `/isochrone` response. It is labelled as such in the file and was
not recorded from a Valhalla server. Replace it with a real recording once a Valhalla instance exists.

## Isochrone kernel contract: Kernel #1 "Isochrone Diff" (`spine.compute.isochrone_diff`)
1. Call `/isochrone` with `contours=[{time:5},{time:10},{time:15}]` and `polygons=true` per origin cell
   centroid (`build_isochrone_request` / `origin_request`).
2. Polyfill each polygon to res 8, keeping a cell if its centroid falls inside (`polyfill`).
3. Write `features/isochrone/<method_ver>/catchment_cells.parquet` (ADR-002 columns).
4. Write `features/isochrone/<method_ver>/radius_vs_isochrone_jaccard.parquet`: per origin and contour, the
   Jaccard index between drive-time cells and the cells within a straight-line radius, plus `radius_only_cells`
   (radius overcounts) and `iso_only_cells` (radius undercounts).

## Zero-server tiles [D]
- Tippecanoe writes PMTiles directly (`-o file.pmtiles`) [V] <https://github.com/felt/tippecanoe>:
  `tippecanoe -o tiles/01/<build_id>.pmtiles -zg --drop-densest-as-needed -l cells features.geojsonseq`.
- MapLibre GL JS reads `pmtiles://` via the `pmtiles` JS package [U].
- Any static host with HTTP Range support; tiles are immutable per `build_id`.
- Not implemented in G-201.
