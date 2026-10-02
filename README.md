# SurgeExposure — Storm-Surge & Flood Exposure Pipeline for Utility/Property Assets

![SurgeExposure map showing storm-surge exposure overlay for Clearwater Beach, FL](image.png)

**Research findings (Hurricane Ian, Lee County, FL; [manuscript](paper/manuscript/manuscript.md), [full technical report](paper/paper.md)):**

- **Frequency.** NOAA's Category 1 SLOSH MOM depth, sampled at all 366,764
  buildings, tracks Ian's claim rate (claims ÷ policies in force) strongly
  at block-group, tract and grid scale: block-group r = 0.64 [0.52, 0.77],
  significant after spatial correction.
- **Severity.** It tracks the damage ratio only moderately (r ≈ 0.45), and
  only at fine scale.
- **Category.** Against 239 USGS high-water marks, the Category 1
  envelope matches Ian's water best (bias +0.3 ft). The envelope for Ian's
  own landfall category (4) is 13 ft too deep and tracks losses worse.
- **Observed depth.** An observed depth surface from those marks predicts
  losses only marginally better than MOM. The severity limit is depth
  itself, not the surge map.
- **Method.** An earlier grid-cell analysis using raw counts and payouts
  reached the opposite conclusion about which result was robust. Scale
  and normalization matter.

## Related work

This pipeline's real building/exposure data and validation findings became
the foundation for two follow-on Databricks projects:
- **[surge-exposure-agent](https://github.com/DBishal13/surge-exposure-agent)** —
  turns this data into a conversational Agent Bricks agent with a real
  write action (flagging buildings for inspection) and an honest,
  validation-study-grounded sense of its own trustworthiness.
- **[surge-exposure-ml](https://github.com/DBishal13/surge-exposure-ml)** —
  re-validates this project's own methodology at 8x the geographic scope
  (140k+ real FEMA claims, not just Lee County) and trains an actual model
  to check honestly whether it beats this hand-picked heuristic. The
  severity correlation held up outside Lee County; the frequency one
  didn't. That replication used the earlier grid method (raw counts and
  payouts), so its numbers are not comparable with the current results —
  see [paper/paper.md §9.1](paper/paper.md#91-update-september-2026-multi-region-replication).

Both are part of a broader
[Databricks AI portfolio](https://github.com/DBishal13/databricks-ai-capstone)
covering Agent Bricks, MLflow, Unity Catalog, and Vector Search.

## Description
A reproducible pipeline that ingests NOAA National Storm Surge Risk
(MEOW/MOM) layers and NOAA NWPS flood-inundation polygons, overlays them against
building/infrastructure footprints from Overture Maps (GeoParquet), and produces
per-asset exposure scores plus an interactive map and an API endpoint. Optionally
enriched with FEMA NFIP claims to check the score against real historical loss —
see the finding above and the validation study below.

## Open data
- NOAA National Storm Surge Risk Maps
- NOAA NWPS flood-inundation API
- Overture Maps buildings/infrastructure
- FEMA NFIP redacted claims

## Tech stack
Python, DuckDB spatial (query Overture GeoParquet directly on S3), GeoPandas,
FastAPI, Folium/Leaflet for the map, Docker for local/self-hosted deployment.
No database persistence layer or cloud deployment exists yet — see Next
steps below for what's actually planned versus built.

## Status
Working MVP, plus a completed validation study (see the finding above and
[paper/paper.md](paper/paper.md)). Demo region: a coastal strip of
Miami-Dade County (FPL/South Florida service territory), configurable via
`bbox` query params; the validation study itself covers Lee County, FL.

## Setup
```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# One-time ~1.6GB download of the NOAA SLOSH MOM storm-surge raster, cached
# in data/raw/ (only needs to run once):
python -m surge_exposure.data.storm_surge
```

## Run
```bash
# API + interactive map
uvicorn surge_exposure.api.main:app --reload
# then visit:
#   http://127.0.0.1:8000/exposure?bbox=-80.20,25.70,-80.10,25.80  (GeoJSON)
#   http://127.0.0.1:8000/map?bbox=-80.20,25.70,-80.10,25.80       (Folium map)

# Or run the pipeline directly and persist to DuckDB:
python -m surge_exposure.pipeline
```

## Run with Docker
```bash
docker compose up --build
# then, once, fetch the storm-surge raster into the persisted volume:
docker compose exec app python -m surge_exposure.data.storm_surge

# visit http://127.0.0.1:8000/exposure?bbox=... or /map?bbox=...
```
The storm-surge raster is fetched lazily into a named volume (`surge-data`)
rather than baked into the image, so it survives container rebuilds and
doesn't bloat the image. Requires Docker Desktop (or another Docker
engine) installed locally.

## Architecture
- `data/overture.py` — Overture Maps building footprints, queried live via
  DuckDB spatial + httpfs directly against S3 GeoParquet (release resolved
  dynamically from Overture's STAC catalog, bbox pushdown via the `bbox`
  struct column — no local download).
- `data/nwps.py` — NOAA NWPS gauge client (`api.water.noaa.gov/nwps/v1`).
- `data/flood_inundation.py` — live NWM analysis-and-assimilation flood
  inundation extent polygons from NOAA's HydroVIS ArcGIS services
  (`maps.water.noaa.gov`), updated hourly.
- `data/storm_surge.py` — NOAA SLOSH MOM storm-surge raster (cached locally
  once, ~1.6GB), sampled at building centroids.
- `pipeline.py` — overlays the three hazard layers into a 0-1
  `exposure_score` per building (60% storm-surge depth, 40% active flood
  intersection) and an `exposure_category` (none/low/moderate/high/severe).
- `api/` — FastAPI endpoints (`/exposure` GeoJSON, `/map` Folium HTML).

## Tests
```bash
pytest tests/
```
Unit tests validate the scoring/categorization logic and raster-sampling
against synthetic data — they don't hit live NOAA/Overture services, so
they run fast and offline.

## Live demo
A static, precomputed showcase (8 coastal regions, no live backend) is
published via GitHub Pages: https://dbishal13.github.io/surge-exposure/
See `scripts/precompute_regions.py` and `docs/`.

## Caching
`/exposure` and `/map` cache scored results to disk
(`data/cache/exposure/`, keyed by bbox + limit, 6h TTL) so a cold request
is still ~35-40s (dominated by the live Overture GeoParquet scan) but a
repeat request for the same area is ~60ms. See `api/cache.py`.

## Validation against real losses
The validation study tests the surge input, NOAA SLOSH MOM depth at building
centroids, against Hurricane Ian in Lee County, FL. The paper is
[paper/manuscript/manuscript.md](paper/manuscript/manuscript.md), and the
full technical report with history and documented bugs is
[paper/paper.md](paper/paper.md).

NFIP claims are public with coordinates rounded to 0.1°, but they carry
census block-group codes, so the analysis runs at block-group, tract and
grid scale. Install the analysis extras
(`pip install -e ".[analysis]"`) and run the scripts below. They cache
inputs under `data/` and write outputs under `paper/data/`.

```bash
python scripts/validate_units.py           # claim rate, damage ratio, SFHA, take-up, bootstrap CIs
python scripts/spatial_models.py           # Dutilleul modified t-test, spatial error model
python scripts/fetch_mom_categories.py     # MOM Category 1-5 rasters (range-extracted from NOAA's zip)
python scripts/validate_categories.py      # each category vs USGS high-water marks and claims
python scripts/validate_observed_depth.py  # observed depth from high-water marks + 3DEP DEM
python scripts/validate_exposure_bins.py [--ian-window]   # earlier grid-cell design, for comparison
python scripts/plot_units_chart.py && python scripts/plot_categories_chart.py && python scripts/plot_validation_chart.py
```

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="paper/figures/units-chart-dark.png">
  <img src="paper/figures/units-chart-light.png" alt="Mean SLOSH MOM depth against Hurricane Ian claim rate and damage ratio at block-group, tract and 0.1-degree grid scale">
</picture>

A historical validation turns off the live NOAA flood feed
(`run_exposure_pipeline(..., live_flood=False)`), because that feed has no
historical replay. The MOM category is set by
`settings.storm_surge_category` (default 1, which fits Ian best; paper
§6.3).

## Next steps
- Give the active-flood term a historical/event-specific data source
  instead of only the live feed, then confirm or extend its coverage to
  rainfall-driven flooding — the validation study found this matters more
  than reweighting the surge/flood split (see
  [paper/paper.md](paper/paper.md) §7, §9).
- Persist scored results to PostGIS instead of (or alongside) DuckDB for
  multi-user access.
- Deploy the live Docker image (not just the static showcase) to a
  publicly reachable demo URL (Render/AWS).
