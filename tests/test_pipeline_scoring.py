import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from surge_exposure import pipeline


def _building(x, y, id_):
    return {
        "id": id_,
        "geometry": Polygon([(x, y), (x + 0.001, y), (x + 0.001, y + 0.001), (x, y + 0.001)]),
    }


def test_run_exposure_pipeline_scores_and_categorizes(monkeypatch):
    buildings = gpd.GeoDataFrame(
        [_building(-80.15, 25.75, "no_hazard"), _building(-80.16, 25.76, "severe")],
        crs="EPSG:4326",
    )

    def fake_get_buildings(bbox, limit=None, sample="first"):
        return buildings.copy()

    def fake_sample_surge_class(gdf, raster_path=None):
        out = gdf.copy()
        out["surge_class"] = [0, 21]
        out["surge_ft"] = [0.0, 20.0]
        return out

    def fake_get_inundation_extent(bbox):
        # Only the "severe" building's footprint intersects active flooding.
        severe_geom = buildings.loc[buildings["id"] == "severe", "geometry"].iloc[0]
        return gpd.GeoDataFrame({"geometry": [severe_geom]}, crs="EPSG:4326")

    monkeypatch.setattr(pipeline.overture, "get_buildings", fake_get_buildings)
    monkeypatch.setattr(pipeline.storm_surge, "sample_surge_class", fake_sample_surge_class)
    monkeypatch.setattr(pipeline.flood_inundation, "get_inundation_extent", fake_get_inundation_extent)

    result = pipeline.run_exposure_pipeline((-80.2, 25.7, -80.1, 25.8))

    no_hazard = result.set_index("id").loc["no_hazard"]
    severe = result.set_index("id").loc["severe"]

    assert no_hazard["exposure_score"] == 0.0
    assert no_hazard["exposure_category"] == "none"
    assert bool(no_hazard["flood_active"]) is False

    assert severe["exposure_score"] == 1.0
    assert severe["exposure_category"] == "severe"
    assert bool(severe["flood_active"]) is True


def test_run_exposure_pipeline_skips_live_flood_when_disabled(monkeypatch):
    buildings = gpd.GeoDataFrame([_building(-80.16, 25.76, "b")], crs="EPSG:4326")

    def fake_sample_surge_class(gdf, raster_path=None):
        out = gdf.copy()
        out["surge_class"], out["surge_ft"] = [11], [10.0]
        return out

    def fail_get_inundation_extent(bbox):
        raise AssertionError("live flood feed must not be queried")

    monkeypatch.setattr(pipeline.overture, "get_buildings", lambda bbox, limit=None, sample="first": buildings.copy())
    monkeypatch.setattr(pipeline.storm_surge, "sample_surge_class", fake_sample_surge_class)
    monkeypatch.setattr(pipeline.flood_inundation, "get_inundation_extent", fail_get_inundation_extent)

    result = pipeline.run_exposure_pipeline((-80.2, 25.7, -80.1, 25.8), live_flood=False)

    assert bool(result["flood_active"].iloc[0]) is False
    assert result["exposure_score"].iloc[0] == 0.3  # surge term only: 0.6 * 10/20
