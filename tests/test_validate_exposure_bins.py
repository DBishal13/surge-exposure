import math

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from scripts.validate_exposure_bins import IAN_WINDOW, _restrict_to_ian_window, aggregate_and_correlate


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


def _claim_row(date_of_loss) -> dict:
    return {
        "latitude": 26.4,
        "longitude": -82.0,
        "dateOfLoss": date_of_loss,
        "amountPaidOnBuildingClaim": 100.0,
        "amountPaidOnContentsClaim": 0.0,
    }


def test_restrict_to_ian_window_drops_claims_outside_the_window():
    claims = pd.DataFrame(
        [
            _claim_row("2021-06-15"),  # unrelated storm, well before the window
            _claim_row(IAN_WINDOW[0]),  # inclusive lower bound
            _claim_row("2022-09-28"),  # Ian's actual landfall date
            _claim_row(IAN_WINDOW[1]),  # inclusive upper bound
            _claim_row("2023-06-01"),  # unrelated later flood event
        ]
    )

    restricted = _restrict_to_ian_window(claims)

    assert len(restricted) == 3
    assert set(pd.to_datetime(restricted["dateOfLoss"]).dt.strftime("%Y-%m-%d")) == {
        IAN_WINDOW[0],
        "2022-09-28",
        IAN_WINDOW[1],
    }


def test_restrict_to_ian_window_drops_unparseable_dates():
    claims = pd.DataFrame([_claim_row("2022-10-01"), _claim_row(None), _claim_row("not-a-date")])

    restricted = _restrict_to_ian_window(claims)

    assert len(restricted) == 1


def test_restrict_to_ian_window_handles_tz_aware_dates_from_the_live_api():
    # FEMA's OpenFEMA API returns tz-aware ISO timestamps (e.g. with a
    # trailing +00:00 offset), not the naive date strings used above --
    # this reproduces that shape so a tz mismatch bug can't silently pass.
    claims = pd.DataFrame(
        [
            _claim_row("2022-10-01T00:00:00+00:00"),
            _claim_row("2021-06-15T00:00:00+00:00"),
        ]
    )

    restricted = _restrict_to_ian_window(claims)

    assert len(restricted) == 1
