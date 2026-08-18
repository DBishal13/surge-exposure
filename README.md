# SurgeExposure — Storm-Surge & Flood Exposure Pipeline for Utility/Property Assets

![SurgeExposure map showing storm-surge exposure overlay for Clearwater Beach, FL](image.png)

**Research finding: a lightweight, explainable storm-surge exposure score
correlates with real Hurricane Ian claim severity robustly (r≈0.52, stable
under a date-window sensitivity check) but with claim frequency only
weakly and unreliably (r=0.25–0.37, depending on that same check) — and it
is silent about roughly a third of the county's real claims, which came
from inland, rainfall-driven flooding a surge-only signal was never going
to see.** That's not a calibration problem, it's a scope problem, and
distinguishing which of the score's two correlations actually deserves
trust is the more useful result of the two — full validation study,
literature review, and two honestly-reported methodological bugs found
along the way: **[paper/paper.md](paper/paper.md)**.

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
`exposure_score` is currently a fixed, explainable heuristic (60% surge
depth + 40% active flood intersection, see `pipeline.py`) — not calibrated
against real outcomes. This project includes a full validation study
against real FEMA NFIP claims for Lee County, FL (Fort Myers Beach,
Sanibel, Cape Coral — hit directly by Hurricane Ian's 2022 surge), written
up with a literature review, methodology, and results in
**[paper/](paper/)** — see [paper/paper.md](paper/paper.md) for the full
report, [paper/figures/](paper/figures/) for charts, and
[paper/data/](paper/data/) for the underlying per-cell CSV.

FEMA rounds NFIP claim coordinates to 1 decimal degree (~11km) before
publishing, for privacy — coarser than this project's building-level
scores, so the comparison can't be per-building. Instead both sides are
snapped to that same 0.1° grid and aggregated per cell before comparing.
Run it yourself (needs the SLOSH raster cached, see Setup, and live
network access):
```bash
python scripts/validate_exposure_bins.py
```
It prints the per-cell table plus Pearson correlation between mean
exposure score and (a) claim count and (b) mean amount paid per cell, and
writes the table to `paper/data/lee_county_grid.csv`. Regenerate the
chart below from that CSV with `python scripts/plot_validation_chart.py`.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="paper/figures/validation-chart-dark.png">
  <img src="paper/figures/validation-chart-light.png" alt="Two scatter plots across 37 Lee County grid cells: mean exposure score vs. NFIP claim count (r=0.37) and vs. mean claim payout (r=0.52)">
</picture>

**Actual result of the (corrected, county-wide) live run:** 18,050 scored
buildings and 48,105 NFIP claims across all 37 grid cells the county spans.
Mean exposure score correlated moderately with claim count (r = 0.37) and
mean claim payout (r = 0.52) — real but modest. One catch worth knowing
about: `flood_active` is a *live* NOAA feed with no historical replay, so
querying it in 2026 for a 2022 storm returned zero active flooding
everywhere — every score in this study was really just its 60% surge term.
That surge signal is spatially sensible (coastal cells score ~2x higher on
average than inland, 0.081 vs 0.039) but incomplete: inland cells actually
had *more* claims than coastal (25,755 vs 22,350), and ~30% of all claims
sit in cells with a near-zero score — Hurricane Ian's inland damage was
largely rainfall-driven riverine flooding, which a live-only,
surge-focused score isn't positioned to see.

**A follow-up check found the r=0.37 number is softer than it looks.** The
run above uses *all* years of Lee County NFIP claims (1978–2026), not just
Ian's. Restricting to a tight post-Ian date window
(`python scripts/validate_exposure_bins.py --ian-window`) drops 40% of raw
claims (19,290 of 48,117) as attributable to unrelated flood events — and
under that stricter, more defensible comparison, claim frequency's
correlation weakens by a third (r = 0.37 → **0.25**) while claim severity's
barely moves (r = 0.52 → **0.516**). Read this as: the score's ability to
flag *which cells see catastrophic losses* looks real and fairly robust;
its ability to predict *how many claims* a cell sees was partly an
artifact of comparing against decades of unrelated claims, not something
`exposure_score` itself earns credit for. Full writeup, including a second
real bug caught building this check (a timezone mismatch between FEMA's
API and the filter, now covered by a regression test):
[paper/paper.md](paper/paper.md) §5.4, §6, §6.1, §7.

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
