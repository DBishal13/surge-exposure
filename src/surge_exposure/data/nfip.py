"""FEMA OpenFEMA NFIP redacted claims (v3).

Real observed flood-insurance claims, used to check whether the
pipeline's exposure_score/category actually tracks real losses. Claim
coordinates are rounded by FEMA to 1 decimal degree (~11km) before
publication for privacy, so this data can only be compared against
building exposure at that same grid resolution — not per-building.

Source: https://www.fema.gov/openfema-data-page/nfip-redacted-claims-v3
"""

from __future__ import annotations

import time

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


# Extra claim fields for unit-level validation (scripts/validate_units.py):
# censusGeoid is the 12-digit census block group; floodEvent / eventDesignationNumber
# attribute a claim to a named event; damage and value give a damage ratio.
UNIT_CLAIM_FIELDS = CLAIM_FIELDS + [
    "censusGeoid",
    "floodEvent",
    "eventDesignationNumber",
    "buildingDamageAmount",
    "buildingPropertyValue",
    "totalBuildingInsuranceCoverage",
]

POLICY_FIELDS = ["censusBlockGroupFips", "censusTract", "latitude", "longitude", "ratedFloodZone", "policyCount"]
POLICIES_URL = "https://www.fema.gov/api/open/v2/FimaNfipPolicies"


def _paginate(url: str, key: str, params: dict, limit: int | None, timeout: float,
              page_size: int = PAGE_SIZE, retries: int = 4) -> list[dict]:
    """GET pages of an OpenFEMA dataset until a short page (or `limit` rows).
    Retries transient errors (OpenFEMA returns 5xx under load) with backoff."""
    rows: list[dict] = []
    skip = 0
    while True:
        page_top = page_size if limit is None else min(page_size, limit - len(rows))
        if page_top <= 0:
            break
        for attempt in range(retries + 1):
            try:
                resp = httpx.get(url, params={**params, "$top": page_top, "$skip": skip, "$format": "json"},
                                 timeout=timeout)
                resp.raise_for_status()
                page = resp.json().get(key, [])
                break
            except (httpx.HTTPError, ValueError):
                if attempt == retries:
                    raise
                time.sleep(2 ** attempt)
        rows.extend(page)
        if len(page) < page_top:
            break
        skip += page_top
    return rows


def get_claims(
    state: str,
    county_codes: list[str],
    limit: int | None = None,
    timeout: float = 60.0,
    fields: list[str] | None = None,
    extra_filter: str | None = None,
) -> pd.DataFrame:
    """Fetch NFIP claims for a state + set of FEMA county codes, paginating
    until the API returns a short page or `limit` rows have been collected.
    Rows with no coordinates (redacted/withheld) are dropped.

    fields: columns to fetch (default CLAIM_FIELDS; UNIT_CLAIM_FIELDS adds
    census geography, event attribution and damage/value).
    extra_filter: an OData clause ANDed onto the state/county filter, e.g.
    "eventDesignationNumber eq 'FL0222'"."""
    fields = fields or CLAIM_FIELDS
    filter_ = _build_filter(state, county_codes)
    if extra_filter:
        filter_ = f"{filter_} and {extra_filter}"
    rows = _paginate(
        settings.nfip_base_url,
        "NfipClaims",
        {"$filter": filter_, "$select": ",".join(fields)},
        limit,
        timeout,
    )
    df = pd.DataFrame(rows, columns=fields)
    return df.dropna(subset=["latitude", "longitude"])


def get_policies_in_force(county_code: str, on_date: str, timeout: float = 120.0,
                          limit: int | None = None) -> pd.DataFrame:
    """NFIP policies in force in one county on a date (YYYY-MM-DD): effective
    on or before it and terminating after it. Used to turn claim counts into
    claim rates. Source: OpenFEMA FIMA NFIP Redacted Policies v2."""
    ts = f"{on_date}T00:00:00.000Z"
    filter_ = (f"countyCode eq '{county_code}' and policyEffectiveDate le '{ts}' "
               f"and policyTerminationDate gt '{ts}'")
    rows = _paginate(POLICIES_URL, "FimaNfipPolicies",
                     {"$filter": filter_, "$select": ",".join(POLICY_FIELDS)}, limit, timeout,
                     page_size=10_000)
    return pd.DataFrame(rows, columns=POLICY_FIELDS)


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
