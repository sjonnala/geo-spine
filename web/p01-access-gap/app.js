/* Product 01 static viewer (G-103 section 1.5). No build step, no basemap, no API keys.
 *
 * Data: by default the committed synthetic GeoJSON export in ./data (written by `make fixtures`).
 * Add ?tiles=<url-to.pmtiles> to read the `cells` layer from a PMTiles archive built by
 * `make tiles` instead; the pmtiles:// protocol is registered either way.
 */
/* global maplibregl, pmtiles */
"use strict";

// Kept on one line so tests/test_web_viewer.py can match it exactly against p01_tiles.ATTRIBUTION.
const ATTRIBUTION = "© OpenStreetMap contributors (ODbL) · CA Dept. of Social Services licensing data · U.S. Census Bureau ACS 5-year";
const GAP_TERM = "licensed-capacity gap";
// 4-class sequential ramp on seats per child; darkest = least access.
const RAMP = ["step", ["get", "seats_per_child_2sfca"], "#08306b", 0.1, "#2171b5", 0.25, "#6baed6", 0.5, "#c6dbef"];

const protocol = new pmtiles.Protocol();
maplibregl.addProtocol("pmtiles", protocol.tile);

function cellsSource(tilesUrl) {
  if (tilesUrl) {
    return { type: "vector", url: "pmtiles://" + tilesUrl, attribution: ATTRIBUTION };
  }
  return { type: "geojson", data: "data/cells.geojson", attribution: ATTRIBUTION };
}

function layers(sourceLayer) {
  const sl = sourceLayer ? { "source-layer": sourceLayer } : {};
  return [
    {
      id: "cells-gap", type: "fill", source: "cells", ...sl,
      filter: ["!=", ["get", "verdict"], "abstain"],
      paint: { "fill-color": RAMP, "fill-opacity": 0.7 },
    },
    {
      id: "cells-abstain", type: "fill", source: "cells", ...sl,
      filter: ["==", ["get", "verdict"], "abstain"],
      paint: { "fill-color": "#9e9e9e", "fill-opacity": 0.4 },
    },
    {
      id: "cells-outline", type: "line", source: "cells", ...sl, minzoom: 11,
      paint: { "line-color": "#ffffff", "line-width": 0.5 },
    },
    {
      // Centers only, rooftop precision; family child care homes are never drawn as points.
      id: "centers", type: "circle", source: "centers",
      paint: {
        "circle-color": "#e6550d", "circle-stroke-color": "#fff", "circle-stroke-width": 1,
        "circle-radius": ["interpolate", ["linear"], ["get", "licensed_capacity"], 24, 3, 120, 9],
      },
    },
    {
      id: "catchment-selected", type: "line", source: "selected",
      paint: { "line-color": "#111", "line-width": 2, "line-dasharray": [2, 1] },
    },
  ];
}

function describe(p) {
  if (p.verdict === "abstain") {
    return "Not enough data: " + String(p.abstain_reason).replace(/_/g, " ") + ".";
  }
  const spc = Number(p.seats_per_child_2sfca).toFixed(4);
  const gap = Number(p.gap_2sfca).toFixed(2);
  if (Number(p.gap_2sfca) > 0) {
    return `${p.children_0_5} children aged 0 to 5; ${spc} licensed seats per child after sharing; ` +
      `${GAP_TERM} of ${gap} children.`;
  }
  return `${p.children_0_5} children aged 0 to 5; ${spc} licensed seats per child; surplus, no ${GAP_TERM}.`;
}

// Cells that compete for at least one of the clicked cell's reachable facilities (2SFCA sharing set).
function sharingSet(sharing, cell) {
  const mine = new Set(sharing.reach[cell] || []);
  return Object.keys(sharing.reach).filter((c) => sharing.reach[c].some((k) => mine.has(k)));
}

async function main() {
  const params = new URLSearchParams(window.location.search);
  const tilesUrl = params.get("tiles");
  const [cells, sharing] = await Promise.all([
    fetch("data/cells.geojson").then((r) => r.json()),
    fetch("data/sharing.json").then((r) => r.json()),
  ]);
  const byCell = new Map(cells.features.map((f) => [f.properties.h3_r8, f]));

  const map = new maplibregl.Map({
    container: "map",
    style: { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#f4f4f2" } }] },
    center: [-121.9552, 37.3541],
    zoom: 11,
    attributionControl: { compact: false, customAttribution: ATTRIBUTION },
  });
  map.addControl(new maplibregl.NavigationControl(), "top-left");

  map.on("load", () => {
    map.addSource("cells", cellsSource(tilesUrl));
    map.addSource("centers", { type: "geojson", data: "data/centers.geojson" });
    map.addSource("selected", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    for (const layer of layers(tilesUrl ? "cells" : null)) map.addLayer(layer);

    const onClick = (e) => {
      const p = e.features[0].properties;
      const ids = sharingSet(sharing, p.h3_r8);
      const feats = ids.map((c) => byCell.get(c)).filter(Boolean);
      map.getSource("selected").setData({ type: "FeatureCollection", features: feats });
      document.getElementById("selected").textContent =
        `Cell ${p.h3_r8}: ${describe(p)} It shares seats with ${ids.length} cells (dashed outline).`;
    };
    map.on("click", "cells-gap", onClick);
    map.on("click", "cells-abstain", onClick);
  });
}

if (typeof window !== "undefined") {
  main().catch((err) => {
    document.getElementById("selected").textContent = "Could not load the fixture data: " + err;
  });
}
