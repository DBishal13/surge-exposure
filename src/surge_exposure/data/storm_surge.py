"""NOAA National Storm Surge Risk Maps (SLOSH MOM — Maximum of MEOWs).

Distributed as a single large GeoTIFF covering Texas-to-Maine at 8-bit
class resolution (class 1 = 0-1 ft inundation ... class 21 = >20 ft). This
module downloads/caches that raster once and samples it at building
centroids rather than re-downloading per request.

Source: https://www.nhc.noaa.gov/nationalsurge/
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import geopandas as gpd
import httpx
import numpy as np
import rasterio

from surge_exposure.config import settings

# NOAA's "class value" bins -> midpoint inundation depth in feet (class 1 =
# 0-1ft bin -> 0.5ft, class 2 = 1-2ft bin -> 1.5ft, ...). Midpoint (rather
# than the bin's lower bound) avoids collapsing the lowest non-zero bin down
# to the same 0.0ft value as "no inundation".
CLASS_TO_FEET = {i: i - 0.5 for i in range(1, 22)}
CLASS_TO_FEET[0] = 0.0


def ensure_storm_surge_raster(dest: Path | None = None) -> Path:
    """Download and unzip the SLOSH MOM GeoTIFF into data/raw/ if not already
    cached. This is a multi-GB file (~1.6GB zipped) — only fetched once, and
    streamed to disk rather than buffered in memory."""
    dest = dest or settings.storm_surge_geotiff
    if dest.exists():
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    zip_path = dest.with_suffix(".zip")

    with httpx.stream(
        "GET", settings.storm_surge_download_url, timeout=None, follow_redirects=True
    ) as resp:
        resp.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)

    with zipfile.ZipFile(zip_path) as zf:
        tif_names = [n for n in zf.namelist() if n.lower().endswith(".tif")]
        if not tif_names:
            raise RuntimeError("No .tif found in storm surge zip archive")
        with zf.open(tif_names[0]) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)

    zip_path.unlink()
    return dest


def sample_surge_class(gdf: gpd.GeoDataFrame, raster_path: Path | None = None) -> gpd.GeoDataFrame:
    """Add `surge_class` and `surge_ft` columns by sampling the storm surge
    raster at each feature's centroid. Points outside raster coverage or in
    the no-inundation zone get surge_class = 0."""
    raster_path = raster_path or settings.storm_surge_geotiff
    if not raster_path.exists():
        raise FileNotFoundError(
            f"{raster_path} not found — call ensure_storm_surge_raster() first"
        )

    out = gdf.copy()
    utm_crs = out.estimate_utm_crs()
    centroids = out.geometry.to_crs(utm_crs).centroid.set_crs(utm_crs)

    with rasterio.open(raster_path) as src:
        nodata = src.nodata
        centroids_proj = centroids.to_crs(src.crs)
        coords = [(pt.x, pt.y) for pt in centroids_proj]
        sampled = list(src.sample(coords))
        classes = np.array([int(v[0]) if v[0] is not None else 0 for v in sampled])
        # Raster nodata (outside the modeled inundation extent, e.g. 255) and
        # any negative fill values both mean "not inundated in this scenario".
        if nodata is not None:
            classes = np.where(classes == int(nodata), 0, classes)
        classes = np.where(classes < 0, 0, classes)

    out["surge_class"] = classes
    out["surge_ft"] = [CLASS_TO_FEET.get(c, 0.0) for c in classes]
    return out


if __name__ == "__main__":
    path = ensure_storm_surge_raster()
    print(f"Storm surge raster cached at {path}")
