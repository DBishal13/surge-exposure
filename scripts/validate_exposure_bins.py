"""Check whether the pipeline's exposure_score actually tracks real losses,
using FEMA NFIP redacted claims for Lee County, FL (Fort Myers Beach,
Sanibel, Cape Coral — directly hit by Hurricane Ian's 2022 surge).

NFIP claim coordinates are rounded by FEMA to 1 decimal degree (~11km) for
privacy, so this can't be a per-building join. Both building exposure
scores and claims are aggregated to that same 0.1-degree grid, then
compared cell-by-cell. This is a one-off analysis script (like
scripts/precompute_regions.py), not part of the served app.

Buildings are scored **per claim grid-cell** rather than with one big
bbox query: a single Overture query over all of Lee County returns
~420k buildings, and a flat LIMIT on that query (no ORDER BY) happened to
return only buildings clustered on the coastal barrier islands, missing
most of the county entirely -- see git history on this file. Querying a
small (0.1x0.1 degree) bbox per cell that actually has claims bounds the
total work while guaranteeing every claim cell gets a shot at building
coverage.

Run against the already-cached SLOSH raster (see README Setup):

    source .venv/bin/activate
    python scripts/validate_exposure_bins.py
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from surge_exposure.data import nfip
from surge_exposure.pipeline import run_exposure_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_CSV = REPO_ROOT / "paper" / "data" / "lee_county_grid.csv"

STATE = "FL"
COUNTY_CODES = ["12071"]  # Lee County, FL

# A handful of NFIP claims come back mis-coded well outside the county
# (e.g. lat 29.4 for a Lee County record) -- drop grid cells outside this
# generous county-shaped bound before querying buildings for them, rather
# than wasting a query on what's almost certainly bad source data.
COUNTY_BOUNDS = (-82.4, 26.2, -81.5, 26.9)  # (min_lon, min_lat, max_lon, max_lat)

PER_CELL_BUILDING_LIMIT = 500
GRID_STEP = 0.1


def aggregate_and_correlate(
    buildings_gdf: gpd.GeoDataFrame, claims_df: pd.DataFrame
) -> tuple[pd.DataFrame, float, float]:
    """Snap buildings and claims to the same 0.1-degree grid, aggregate each
    side per cell, and inner-join. Returns (per-cell table, Pearson
    correlation of mean exposure_score vs claim_count, ditto vs mean
    amount paid). Correlations are NaN if fewer than 2 cells overlap."""
    b = buildings_gdf.copy()
    utm_crs = b.estimate_utm_crs()
    centroids = b.geometry.to_crs(utm_crs).centroid.set_crs(utm_crs).to_crs(b.crs)
    b["latitude"] = centroids.y
    b["longitude"] = centroids.x
    b = nfip.snap_to_grid(b)
    building_cells = (
        b.groupby(["grid_lat", "grid_lon"])
        .agg(mean_exposure_score=("exposure_score", "mean"), building_count=("exposure_score", "size"))
        .reset_index()
    )

    c = nfip.snap_to_grid(claims_df)
    c["amount_paid"] = c["amountPaidOnBuildingClaim"].fillna(0) + c["amountPaidOnContentsClaim"].fillna(0)
    claim_cells = (
        c.groupby(["grid_lat", "grid_lon"])
        .agg(claim_count=("amount_paid", "size"), mean_amount_paid=("amount_paid", "mean"))
        .reset_index()
    )

    merged = building_cells.merge(claim_cells, on=["grid_lat", "grid_lon"], how="inner")

    if len(merged) < 2:
        return merged, float("nan"), float("nan")

    corr_claim_count = float(np.corrcoef(merged["mean_exposure_score"], merged["claim_count"])[0, 1])
    corr_amount_paid = float(np.corrcoef(merged["mean_exposure_score"], merged["mean_amount_paid"])[0, 1])
    return merged, corr_claim_count, corr_amount_paid


def _claim_cells_in_bounds(claims: pd.DataFrame) -> list[tuple[float, float]]:
    c = nfip.snap_to_grid(claims)
    min_lon, min_lat, max_lon, max_lat = COUNTY_BOUNDS
    in_bounds = c[c["grid_lat"].between(min_lat, max_lat) & c["grid_lon"].between(min_lon, max_lon)]
    cells = in_bounds[["grid_lat", "grid_lon"]].drop_duplicates()
    return list(cells.itertuples(index=False, name=None))


def _score_buildings_for_cell(grid_lat: float, grid_lon: float) -> gpd.GeoDataFrame:
    half = GRID_STEP / 2
    bbox = (grid_lon - half, grid_lat - half, grid_lon + half, grid_lat + half)
    return run_exposure_pipeline(bbox, building_limit=PER_CELL_BUILDING_LIMIT)


def main() -> None:
    print(f"Fetching NFIP claims for state={STATE} county={COUNTY_CODES}...")
    claims = nfip.get_claims(state=STATE, county_codes=COUNTY_CODES)
    print(f"{len(claims)} NFIP claims fetched.")

    cells = _claim_cells_in_bounds(claims)
    print(f"{len(cells)} distinct claim grid cells within the county bounds to score buildings for.")

    scored_parts = []
    for i, (grid_lat, grid_lon) in enumerate(cells, 1):
        print(f"[{i}/{len(cells)}] scoring buildings for cell ({grid_lat}, {grid_lon})...")
        part = _score_buildings_for_cell(grid_lat, grid_lon)
        if not part.empty:
            scored_parts.append(part)

    buildings = pd.concat(scored_parts, ignore_index=True) if scored_parts else gpd.GeoDataFrame()
    buildings = gpd.GeoDataFrame(buildings, geometry="geometry", crs="EPSG:4326") if not buildings.empty else buildings
    print(f"\n{len(buildings)} buildings scored across {len(scored_parts)} non-empty cells.")

    merged, corr_claim_count, corr_amount_paid = aggregate_and_correlate(buildings, claims)

    print(f"\n{len(merged)} grid cells have both scored buildings and NFIP claims.")
    print(
        "This is a grid-cell-level comparison (NFIP claim coordinates are "
        "rounded to ~11km for privacy) — treat the correlations below as "
        "directional, not a substitute for a proper statistical study."
    )
    if not merged.empty:
        print(merged.sort_values("mean_exposure_score", ascending=False).to_string(index=False))
    print(f"\ncorrelation(mean_exposure_score, claim_count)      = {corr_claim_count:.3f}")
    print(f"correlation(mean_exposure_score, mean_amount_paid) = {corr_amount_paid:.3f}")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUT_CSV, index=False)
    print(f"\nWrote per-cell table to {OUT_CSV}")


if __name__ == "__main__":
    main()
