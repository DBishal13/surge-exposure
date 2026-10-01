"""Fetch NWM-derived flood inundation extent polygons from NOAA's HydroVIS
ArcGIS services (maps.water.noaa.gov), analysis-and-assimilation config.

These are the operational flood-inundation-mapping (FIM) polygons behind
NWPS — a standard ArcGIS REST FeatureServer/MapServer, queried by bbox.
"""

from __future__ import annotations

import time

import geopandas as gpd
import httpx

from surge_exposure.config import settings

BBox = tuple[float, float, float, float]


def get_inundation_extent(bbox: BBox, layer: int = 0, timeout: float = 60.0,
                          retries: int = 3) -> gpd.GeoDataFrame:
    """Return flood inundation extent polygons intersecting bbox.

    bbox: (min_lon, min_lat, max_lon, max_lat) in EPSG:4326.
    Returns an empty GeoDataFrame if the service has no active inundation
    extent for the area (the common case outside of flood events).
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    url = f"{settings.nwm_fim_base_url}/{layer}/query"
    params = {
        "where": "1=1",
        "geometry": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "f": "geojson",
    }
    # The service intermittently returns 5xx under load; retry with backoff.
    for attempt in range(retries + 1):
        resp = httpx.get(url, params=params, timeout=timeout)
        if resp.status_code < 500 or attempt == retries:
            break
        time.sleep(2 ** attempt)
    resp.raise_for_status()
    geojson = resp.json()

    features = geojson.get("features", [])
    if not features:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    return gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")


if __name__ == "__main__":
    from surge_exposure.config import DEFAULT_DEMO_BBOX

    extent = get_inundation_extent(DEFAULT_DEMO_BBOX)
    print(f"{len(extent)} inundation polygons found in demo bbox")
