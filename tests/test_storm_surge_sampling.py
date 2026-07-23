import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Polygon

from surge_exposure.data.storm_surge import sample_surge_class


def _write_synthetic_raster(path):
    # 10x10 raster, 1 degree pixels, origin at (-81, 26), EPSG:4326.
    # Row 0 (top, y in [25,26)) = class 5; everything else = class 0.
    data = np.zeros((10, 10), dtype=np.uint8)
    data[0, :] = 5
    transform = from_origin(-81, 26, 1, 1)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype=data.dtype,
        crs="EPSG:4326",
        transform=transform,
        nodata=255,
    ) as dst:
        dst.write(data, 1)


def test_sample_surge_class(tmp_path):
    raster_path = tmp_path / "synthetic_surge.tif"
    _write_synthetic_raster(raster_path)

    # One building centered in the class-5 row, one outside it.
    high_surge_building = Polygon(
        [(-80.5, 25.4), (-80.4, 25.4), (-80.4, 25.6), (-80.5, 25.6)]
    )
    no_surge_building = Polygon(
        [(-80.5, 20.4), (-80.4, 20.4), (-80.4, 20.6), (-80.5, 20.6)]
    )
    gdf = gpd.GeoDataFrame(
        {"id": ["a", "b"]},
        geometry=[high_surge_building, no_surge_building],
        crs="EPSG:4326",
    )

    scored = sample_surge_class(gdf, raster_path=raster_path)

    assert scored.loc[scored["id"] == "a", "surge_class"].iloc[0] == 5
    assert scored.loc[scored["id"] == "a", "surge_ft"].iloc[0] == 4.5
    assert scored.loc[scored["id"] == "b", "surge_class"].iloc[0] == 0
    assert scored.loc[scored["id"] == "b", "surge_ft"].iloc[0] == 0.0
