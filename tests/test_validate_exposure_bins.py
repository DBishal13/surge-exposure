import math

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from scripts.validate_exposure_bins import aggregate_and_correlate


def _buildings(cells: list[tuple[float, float, float]]) -> gpd.GeoDataFrame:
    """cells: list of (lat, lon, exposure_score), two buildings per cell."""
    rows = []
    for lat, lon, score in cells:
        for offset in (0.0, 0.01):
            rows.append({"geometry": Point(lon + offset, lat + offset), "exposure_score": score})
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


def _claims(cells: list[tuple[float, float, int, float]]) -> pd.DataFrame:
    """cells: list of (lat, lon, claim_count, amount_per_claim)."""
    rows = []
    for lat, lon, count, amount in cells:
        for _ in range(count):
            rows.append(
                {
                    "latitude": lat,
                    "longitude": lon,
                    "amountPaidOnBuildingClaim": amount,
                    "amountPaidOnContentsClaim": 0.0,
                }
            )
    return pd.DataFrame(rows)


def test_aggregate_and_correlate_joins_on_shared_grid_cells():
    buildings = _buildings([(26.4, -82.0, 0.9), (26.5, -81.9, 0.5), (26.6, -81.8, 0.1)])
    claims = _claims([(26.4, -82.0, 5, 500.0), (26.5, -81.9, 3, 300.0), (26.6, -81.8, 1, 100.0)])

    merged, corr_claim_count, corr_amount_paid = aggregate_and_correlate(buildings, claims)

    assert len(merged) == 3
    assert corr_claim_count == pytest.approx(1.0)
    assert corr_amount_paid == pytest.approx(1.0)


def test_aggregate_and_correlate_only_keeps_overlapping_cells():
    buildings = _buildings([(26.4, -82.0, 0.9), (40.0, -70.0, 0.2)])
    claims = _claims([(26.4, -82.0, 2, 200.0)])

    merged, _, _ = aggregate_and_correlate(buildings, claims)

    assert len(merged) == 1
    assert merged.iloc[0]["grid_lat"] == 26.4


def test_aggregate_and_correlate_nan_correlation_with_fewer_than_two_cells():
    buildings = _buildings([(26.4, -82.0, 0.9)])
    claims = _claims([(26.4, -82.0, 2, 200.0)])

    merged, corr_claim_count, corr_amount_paid = aggregate_and_correlate(buildings, claims)

    assert len(merged) == 1
    assert math.isnan(corr_claim_count)
    assert math.isnan(corr_amount_paid)
