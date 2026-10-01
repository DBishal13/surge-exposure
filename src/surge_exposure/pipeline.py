"""Overlay pipeline: buildings x storm surge x active flood inundation ->
per-asset exposure score.

exposure_score in [0, 1] = 0.6 * (surge_ft / 20, capped) + 0.4 * (1 if the
building intersects an active NWM flood-inundation extent else 0).
This is a simple, explainable weighting, not a calibrated risk model —
swap in FEMA NFIP loss history (data/nfip.py, not yet built) to recalibrate
weights against observed claims.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import geopandas as gpd

from surge_exposure.config import settings
from surge_exposure.data import flood_inundation, overture, storm_surge

BBox = tuple[float, float, float, float]

SURGE_WEIGHT = 0.6
FLOOD_WEIGHT = 0.4
SURGE_FT_CAP = 20.0


def _exposure_category(score: float) -> str:
    if score >= 0.75:
        return "severe"
    if score >= 0.5:
        return "high"
    if score >= 0.25:
        return "moderate"
    if score > 0.0:
        return "low"
    return "none"


def run_exposure_pipeline(
    bbox: BBox,
    building_limit: int | None = None,
    raster_path: Path | None = None,
    building_sample: str = "first",
) -> gpd.GeoDataFrame:
    """Fetch buildings + hazard layers for bbox and return a GeoDataFrame of
    per-building exposure scores.

    building_sample: "first" (fast, for maps) or "random" (spatially unbiased,
    for anything that averages scores; see overture.limit_clause)."""
    buildings = overture.get_buildings(bbox, limit=building_limit, sample=building_sample)
    if buildings.empty:
        return buildings

    scored = storm_surge.sample_surge_class(buildings, raster_path=raster_path)

    inundation = flood_inundation.get_inundation_extent(bbox)
    if not inundation.empty:
        hit_idx = gpd.sjoin(
            scored, inundation[["geometry"]], how="left", predicate="intersects"
        )["index_right"].notna()
        scored["flood_active"] = hit_idx.groupby(level=0).any().reindex(scored.index, fill_value=False)
    else:
        scored["flood_active"] = False

    surge_component = (scored["surge_ft"].clip(upper=SURGE_FT_CAP) / SURGE_FT_CAP)
    flood_component = scored["flood_active"].astype(float)
    scored["exposure_score"] = (
        SURGE_WEIGHT * surge_component + FLOOD_WEIGHT * flood_component
    ).round(3)
    scored["exposure_category"] = scored["exposure_score"].map(_exposure_category)

    return scored


def persist(gdf: gpd.GeoDataFrame, table: str = "exposure", duckdb_path: Path | None = None) -> None:
    """Write scored buildings to a DuckDB table (as WKB geometry) for reuse
    by the API without re-running the pipeline."""
    duckdb_path = duckdb_path or settings.duckdb_path
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)

    df = gdf.copy()
    df["geometry_wkb"] = gdf.geometry.to_wkb()
    df = df.drop(columns=["geometry"])

    con = duckdb.connect(str(duckdb_path))
    con.execute("INSTALL spatial; LOAD spatial;")
    con.register("df_view", df)
    con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM df_view")
    con.close()


if __name__ == "__main__":
    from surge_exposure.config import DEFAULT_DEMO_BBOX

    result = run_exposure_pipeline(DEFAULT_DEMO_BBOX, building_limit=200)
    print(result[["id", "surge_ft", "flood_active", "exposure_score", "exposure_category"]])
    persist(result)
    print(f"Persisted {len(result)} scored buildings to {settings.duckdb_path}")
