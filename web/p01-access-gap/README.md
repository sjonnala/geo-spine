# Product 01 static viewer (`web/p01-access-gap/`)

A no-build MapLibre GL JS page for the Product 01 2SFCA **licensed-capacity gap** layer.
Everything in `data/` is the **synthetic** Santa Clara fixture export written by `make fixtures`.

```bash
python3 -m http.server -d web/p01-access-gap 8000   # then open http://localhost:8000
```

- Default source: `data/cells.geojson` (layer spec from G-103 section 1.5: `cells-gap`, `cells-abstain`,
  `cells-outline`, `centers`, `catchment-selected`).
- PMTiles: `make tiles` (needs [tippecanoe](https://github.com/felt/tippecanoe)) writes
  `tiles/01/fixture-g301.pmtiles` with a `cells` layer. Serve it and open
  `?tiles=http://localhost:8000/<path>.pmtiles`; the page reads it through `pmtiles://`.
  No `.pmtiles` file is committed (tippecanoe isn't available in CI).
- Copy rules: always "licensed-capacity gap", never "desert"; the FFN disclaimer and the
  OSM / CDSS / ACS attribution are on the page. Only child care **centers** at rooftop precision are drawn;
  family child care homes are never points. No facility names or licensee fields reach `data/`.
- `catchment-selected` outlines every cell that competes for at least one of the clicked cell's reachable
  facilities (the 2SFCA sharing set), from the anonymous facility indices in `data/sharing.json`.
