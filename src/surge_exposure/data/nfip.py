"""FEMA OpenFEMA NFIP redacted claims (v3).

Real observed flood-insurance claims, used to check whether the
pipeline's exposure_score/category actually tracks real losses. Claim
coordinates are rounded by FEMA to 1 decimal degree (~11km) before
publication for privacy, so this data can only be compared against
building exposure at that same grid resolution — not per-building.

Source: https://www.fema.gov/openfema-data-page/nfip-redacted-claims-v3
"""

from __future__ import annotations

import httpx
import pandas as pd

from surge_exposure.config import settings

CLAIM_FIELDS = [
    "state",
    "countyCode",
    "latitude",
    "longitude",
    "dateOfLoss",
    "yearOfLoss",
    "ratedFloodZone",
    "amountPaidOnBuildingClaim",
    "amountPaidOnContentsClaim",
]

PAGE_SIZE = 1000


def _build_filter(state: str, county_codes: list[str]) -> str:
    """OData $filter for one state and one or more FEMA county codes."""
    counties = " or ".join(f"countyCode eq '{c}'" for c in county_codes)
    return f"state eq '{state}' and ({counties})"


def get_claims(
    state: str,
    county_codes: list[str],
    limit: int | None = None,
    timeout: float = 60.0,
) -> pd.DataFrame:
    """Fetch NFIP claims for a state + set of FEMA county codes, paginating
    until the API returns a short page or `limit` rows have been collected.
    Rows with no coordinates (redacted/withheld) are dropped."""
    filter_ = _build_filter(state, county_codes)
    rows: list[dict] = []
    skip = 0

    while True:
        page_top = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - len(rows))
        if page_top <= 0:
            break

        resp = httpx.get(
            settings.nfip_base_url,
            params={
                "$filter": filter_,
                "$select": ",".join(CLAIM_FIELDS),
                "$top": page_top,
                "$skip": skip,
                "$format": "json",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        page = resp.json().get("NfipClaims", [])
        rows.extend(page)

        if len(page) < page_top:
            break
        skip += page_top

    df = pd.DataFrame(rows, columns=CLAIM_FIELDS)
    return df.dropna(subset=["latitude", "longitude"])


def snap_to_grid(df: pd.DataFrame, lat_col: str = "latitude", lon_col: str = "longitude") -> pd.DataFrame:
    """Add grid_lat/grid_lon columns rounded to 1 decimal degree — the same
    precision NFIP claim coordinates are already rounded to, so this adds
    no extra error when aggregating claims and only rounds building
    centroids down to that same resolution for a fair join."""
    out = df.copy()
    out["grid_lat"] = out[lat_col].round(1)
    out["grid_lon"] = out[lon_col].round(1)
    return out


if __name__ == "__main__":
    claims = get_claims(state="FL", county_codes=["12071"], limit=2000)
    print(f"{len(claims)} NFIP claims fetched for Lee County, FL")
