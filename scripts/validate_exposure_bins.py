"""Check whether the pipeline's exposure_score actually tracks real losses,
using FEMA NFIP redacted claims for Lee County, FL (Fort Myers Beach,
Sanibel, Cape Coral — directly hit by Hurricane Ian's 2022 surge).

NFIP claim coordinates are rounded by FEMA to 1 decimal degree (~11km) for
privacy, so this can't be a per-building join. Both building exposure
scores and claims are aggregated to that same 0.1-degree grid, then
compared cell-by-cell. This is a one-off analysis script (like
scripts/precompute_regions.py), not part of the served app.

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
OUT_CSV = REPO_ROOT / "data" / "validation" / "lee_county_grid.csv"

# Lee County, FL (FEMA county code 12071) — Fort Myers Beach, Sanibel,
# Cape Coral, Fort Myers. Wide enough to span ~10-12 distinct 0.1-degree
# grid cells, unlike the tight showcase bboxes in precompute_regions.py.
BBOX = (-82.15, 26.35, -81.75, 26.70)
BUILDING_LIMIT = 5000
STATE = "FL"
COUNTY_CODES = ["12071"]


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


def main() -> None:
    print(f"Scoring buildings for Lee County, FL bbox={BBOX}...")
    buildings = run_exposure_pipeline(BBOX, building_limit=BUILDING_LIMIT)
    print(f"{len(buildings)} buildings scored.")

    print(f"Fetching NFIP claims for state={STATE} county={COUNTY_CODES}...")
    claims = nfip.get_claims(state=STATE, county_codes=COUNTY_CODES)
    print(f"{len(claims)} NFIP claims fetched.")

    merged, corr_claim_count, corr_amount_paid = aggregate_and_correlate(buildings, claims)

    print(f"\n{len(merged)} grid cells have both scored buildings and NFIP claims.")
    print(
        "This is a small-sample, grid-cell-level comparison (NFIP claim "
        "coordinates are rounded to ~11km for privacy) — treat the "
        "correlations below as directional, not statistically conclusive."
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
