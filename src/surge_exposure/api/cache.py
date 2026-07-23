"""Disk-backed cache for scored exposure results, keyed by (bbox, limit).

A live request takes ~35-40s (dominated by the DuckDB scan of Overture's
GeoParquet over the network), so repeat requests for the same area -- the
common case, since the frontend auto-loads a default preset on every page
load -- are cached to disk under data/cache/exposure/. Disk rather than an
in-memory dict so the cache survives a container restart, consistent with
how the storm-surge raster is cached (see data/storm_surge.py).
"""

from __future__ import annotations

import hashlib
import json
import time

import geopandas as gpd

from surge_exposure.config import settings

BBox = tuple[float, float, float, float]

CACHE_DIR = settings.data_dir / "cache" / "exposure"

# Hazard data (NWM flood extent) updates hourly, but this is a demo, not an
# operational system -- a few hours of staleness is an acceptable trade for
# not re-running a 35-40s live query on every repeat visit.
TTL_SECONDS = 6 * 3600


def _key(bbox: BBox, limit: int | None) -> str:
    # Round so near-identical float bboxes (e.g. from client-side rounding)
    # still hit the same cache entry.
    rounded = tuple(round(v, 4) for v in bbox)
    raw = f"{rounded}:{limit}"
    return hashlib.sha1(raw.encode()).hexdigest()


def get(bbox: BBox, limit: int | None) -> gpd.GeoDataFrame | None:
    path = CACHE_DIR / f"{_key(bbox, limit)}.geojson"
    if not path.exists():
        return None
    if (time.time() - path.stat().st_mtime) > TTL_SECONDS:
        return None
    data = json.loads(path.read_text())
    if not data["features"]:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    return gpd.GeoDataFrame.from_features(data["features"], crs="EPSG:4326")


def set(bbox: BBox, limit: int | None, gdf: gpd.GeoDataFrame) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{_key(bbox, limit)}.geojson"
    geojson = (
        json.loads(gdf.to_json())
        if not gdf.empty
        else {"type": "FeatureCollection", "features": []}
    )
    path.write_text(json.dumps(geojson))
