"""Unit-level validation against NFIP losses for Hurricane Ian, Lee County, FL.

Follow-up to validate_exposure_bins.py (paper §5-§6), addressing the
pre-submission review:
- B1: aggregate to census block groups and tracts (NFIP claims and policies
  carry census codes), not only the 0.1-degree grid.
- B2: claim *rate* = Ian claims / NFIP policies in force at landfall.
- B3: damage ratio = building damage / building property value.
- B4: score every building in the county (no capped sample).
- B5a: report insurance take-up (policies / buildings) and SFHA vs non-SFHA.
- B7: Pearson and Spearman with spatial block-bootstrap 95% CIs, plus
  Moran's I of the residuals.

The exposure measure is SLOSH MOM surge depth at each building's centroid.
That is all exposure_score reduces to for a historical event (paper §6).

    python scripts/validate_units.py            # uses cached inputs if present
    python scripts/validate_units.py --refresh  # re-download claims/policies/buildings

Outputs: paper/data/units/{block_group,tract,grid}.csv and results.json.
Cached inputs: data/cache/ (git-ignored).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial import cKDTree

from surge_exposure.data import nfip, overture, storm_surge

COUNTY_FIPS = "12071"  # Lee County, FL
COUNTY_BBOX = (-82.4, 26.2, -81.5, 26.9)  # same bound validate_exposure_bins.py uses
LANDFALL = "2022-09-28"
IAN_EDN = "FL0222"  # NFIP event designation number for Hurricane Ian in Florida
TIGER_2020_BG = Path("data/raw/tiger/tl_2020_12_bg.zip")
TIGER_2010_BG = Path("data/raw/tiger/tl_2010_12071_bg10.zip")
CACHE = Path("data/cache")
OUT = Path("paper/data/units")

# Units with too few insured buildings give noisy rates; keep them out of the correlations.
MIN_POLICIES = 20
MIN_BUILDINGS = 50
MIN_DAMAGE_CLAIMS = 5
BOOTSTRAP_REPS = 2000
SEED = 42


# ---------------------------------------------------------------- inputs

def load_block_groups() -> tuple[gpd.GeoDataFrame, dict[str, str]]:
    """2020 block groups for the county, plus a map from 2010-only codes to the
    2020 block group they overlap most. Some NFIP records still carry 2010 codes."""
    bg20 = gpd.read_file(TIGER_2020_BG)
    bg20 = bg20[bg20["COUNTYFP"] == COUNTY_FIPS[2:]][["GEOID", "geometry"]].to_crs("EPSG:4326")
    bg10 = gpd.read_file(TIGER_2010_BG)[["GEOID10", "geometry"]].to_crs("EPSG:4326")

    only10 = bg10[~bg10["GEOID10"].isin(set(bg20["GEOID"]))]
    utm = bg20.estimate_utm_crs()
    overlap = gpd.overlay(only10.to_crs(utm), bg20.to_crs(utm), how="intersection")
    overlap["area"] = overlap.geometry.area
    best = overlap.sort_values("area").groupby("GEOID10").tail(1)
    return bg20, dict(zip(best["GEOID10"], best["GEOID"]))


def to_2020(codes: pd.Series, crosswalk: dict[str, str], valid: set[str]) -> pd.Series:
    codes = codes.fillna("").astype(str).str[:12]
    return codes.where(codes.isin(valid), codes.map(crosswalk))


def load_claims(refresh: bool) -> pd.DataFrame:
    path = CACHE / "lee_claims_units.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)
    # OpenFEMA's countyCode is the full 5-digit FIPS code; filter to Ian server-side.
    claims = nfip.get_claims("FL", [COUNTY_FIPS], fields=nfip.UNIT_CLAIM_FIELDS,
                             extra_filter=f"eventDesignationNumber eq '{IAN_EDN}'")
    if claims.empty:
        raise RuntimeError("OpenFEMA returned no Ian claims for Lee County; check the filter")
    CACHE.mkdir(parents=True, exist_ok=True)
    claims.to_parquet(path)
    return claims


def load_policies(refresh: bool) -> pd.DataFrame:
    path = CACHE / f"lee_policies_{LANDFALL}.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)
    policies = nfip.get_policies_in_force(COUNTY_FIPS, LANDFALL)
    CACHE.mkdir(parents=True, exist_ok=True)
    policies.to_parquet(path)
    return policies


def load_buildings(refresh: bool) -> gpd.GeoDataFrame:
    """Every Overture building in the county bbox, as centroid points with surge depth."""
    path = CACHE / "lee_buildings_surge.parquet"
    if path.exists() and not refresh:
        return gpd.read_parquet(path)
    footprints = overture.get_buildings(COUNTY_BBOX)  # no limit: every building
    utm = footprints.estimate_utm_crs()
    points = gpd.GeoDataFrame(
        footprints[["id"]].copy(),
        geometry=footprints.geometry.to_crs(utm).centroid.to_crs("EPSG:4326"),
        crs="EPSG:4326",
    )
    points = storm_surge.sample_surge_class(points)
    CACHE.mkdir(parents=True, exist_ok=True)
    points.to_parquet(path)
    return points


# ---------------------------------------------------------------- aggregation

def is_sfha(zone: pd.Series) -> pd.Series:
    """FEMA Special Flood Hazard Areas: zones starting with A or V."""
    return zone.fillna("").str.upper().str[:1].isin(["A", "V"])


def aggregate(buildings, claims, policies, unit: str) -> pd.DataFrame:
    """One row per unit with exposure, claim, policy and damage measures."""
    b = buildings.groupby(unit).agg(
        buildings=("surge_ft", "size"),
        mean_surge_ft=("surge_ft", "mean"),
        share_surge_exposed=("surge_ft", lambda s: float((s > 0).mean())),
        lon=("lon", "mean"),
        lat=("lat", "mean"),
    )
    c = claims.assign(sfha=is_sfha(claims["ratedFloodZone"])).groupby(unit).agg(
        claims=("ian", "size"),
        claims_sfha=("sfha", "sum"),
        mean_damage_ratio=("damage_ratio", "mean"),
        damage_claims=("damage_ratio", "count"),
        mean_payout_usd=("payout", "mean"),
    )
    p = policies.assign(sfha=is_sfha(policies["ratedFloodZone"]))
    p_all = p.groupby(unit)["policyCount"].sum().rename("policies")
    p_sfha = p[p["sfha"]].groupby(unit)["policyCount"].sum().rename("policies_sfha")
    df = b.join([p_all, p_sfha], how="left").join(c, how="left").fillna(
        {"policies": 0, "policies_sfha": 0, "claims": 0, "claims_sfha": 0, "damage_claims": 0})
    df["claim_rate"] = df["claims"] / df["policies"].where(df["policies"] > 0)
    df["claim_rate_sfha"] = df["claims_sfha"] / df["policies_sfha"].where(df["policies_sfha"] > 0)
    df["claim_rate_non_sfha"] = (df["claims"] - df["claims_sfha"]) / (df["policies"] - df["policies_sfha"]).where(
        df["policies"] - df["policies_sfha"] > 0)
    df["take_up"] = df["policies"] / df["buildings"]
    return df.reset_index()


# ---------------------------------------------------------------- statistics

def block_bootstrap_ci(x, y, blocks, method: str, reps=BOOTSTRAP_REPS, seed=SEED):
    """95% CI for a correlation, resampling whole spatial blocks with replacement."""
    rng = np.random.default_rng(seed)
    x, y, blocks = np.asarray(x), np.asarray(y), np.asarray(blocks)
    groups = [np.flatnonzero(blocks == g) for g in np.unique(blocks)]
    corr = stats.spearmanr if method == "spearman" else stats.pearsonr
    draws = []
    for _ in range(reps):
        idx = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        if len(np.unique(x[idx])) > 2 and len(np.unique(y[idx])) > 2:
            draws.append(corr(x[idx], y[idx])[0])
    if not draws:
        return [float("nan"), float("nan")]
    return [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))]


def morans_i(values, lon, lat, k=8, perms=999, seed=SEED):
    """Moran's I with row-standardized k-nearest-neighbour weights and a permutation p-value."""
    z = np.asarray(values, float) - np.mean(values)
    pts = np.column_stack([np.asarray(lon) * np.cos(np.radians(np.mean(lat))), lat])
    _, nbrs = cKDTree(pts).query(pts, k=k + 1)
    nbrs = nbrs[:, 1:]

    def stat(v):
        return float((v * v[nbrs].mean(axis=1)).sum() / (v * v).sum())

    observed = stat(z)
    rng = np.random.default_rng(seed)
    null = [stat(rng.permutation(z)) for _ in range(perms)]
    p = (1 + sum(n >= observed for n in null)) / (perms + 1)
    return {"I": observed, "p_perm": float(p)}


def correlate(df: pd.DataFrame, y: str, blocks: str, n_filter: pd.Series) -> dict:
    d = df[n_filter & df[y].notna() & np.isfinite(df[y])]
    if len(d) < 8:
        return {"n": int(len(d))}
    x = d["mean_surge_ft"]
    pr, pp = stats.pearsonr(x, d[y])
    sr, sp = stats.spearmanr(x, d[y])
    slope, intercept = np.polyfit(x, d[y], 1)
    resid = d[y] - (slope * x + intercept)
    return {
        "n": int(len(d)),
        "blocks": int(d[blocks].nunique()),
        "pearson": float(pr), "pearson_ci95": block_bootstrap_ci(x, d[y], d[blocks], "pearson"),
        "spearman": float(sr), "spearman_ci95": block_bootstrap_ci(x, d[y], d[blocks], "spearman"),
        "naive_p_pearson": float(pp), "naive_p_spearman": float(sp),
        "residual_morans_i": morans_i(resid, d["lon"], d["lat"]),
    }


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--refresh", action="store_true", help="re-download cached inputs")
    args = ap.parse_args()

    bg20, crosswalk = load_block_groups()
    valid = set(bg20["GEOID"])

    buildings = load_buildings(args.refresh)
    buildings = gpd.sjoin(buildings, bg20.rename(columns={"GEOID": "block_group"}), predicate="within", how="inner")
    buildings["lon"], buildings["lat"] = buildings.geometry.x, buildings.geometry.y

    claims = load_claims(args.refresh)
    claims["ian"] = claims["eventDesignationNumber"].eq(IAN_EDN)
    n_all = len(claims)
    claims = claims[claims["ian"]].copy()
    value = pd.to_numeric(claims["buildingPropertyValue"], errors="coerce")
    damage = pd.to_numeric(claims["buildingDamageAmount"], errors="coerce")
    claims["damage_ratio"] = (damage / value.where(value > 0)).clip(upper=1.0)
    claims["payout"] = (pd.to_numeric(claims["amountPaidOnBuildingClaim"], errors="coerce").fillna(0)
                        + pd.to_numeric(claims["amountPaidOnContentsClaim"], errors="coerce").fillna(0))
    claims["block_group"] = to_2020(claims["censusGeoid"], crosswalk, valid)

    policies = load_policies(args.refresh)
    policies["block_group"] = to_2020(policies["censusBlockGroupFips"], crosswalk, valid)

    coverage = {
        "claims_fetched": int(n_all),
        "claims_ian": int(len(claims)),
        "claims_ian_with_block_group": int(claims["block_group"].notna().sum()),
        "claims_ian_with_damage_ratio": int(claims["damage_ratio"].notna().sum()),
        "policies_records": int(len(policies)),
        "policies_units": int(policies["policyCount"].sum()),
        "policies_with_block_group": float(policies.loc[policies["block_group"].notna(), "policyCount"].sum()
                                           / policies["policyCount"].sum()),
        "buildings_in_county": int(len(buildings)),
        "block_groups_2020": int(len(bg20)),
        "crosswalked_2010_codes": int(len(crosswalk)),
    }

    for frame in (buildings, claims, policies):
        frame["tract"] = frame["block_group"].str[:11]
    for frame, lat, lon in ((buildings, "lat", "lon"), (claims, "latitude", "longitude"),
                            (policies, "latitude", "longitude")):
        frame["grid"] = frame[lat].round(1).astype(str) + "," + frame[lon].round(1).astype(str)

    results = {"coverage": coverage, "units": {}}
    OUT.mkdir(parents=True, exist_ok=True)
    for unit in ("block_group", "tract", "grid"):
        df = aggregate(buildings, claims.dropna(subset=[unit]), policies.dropna(subset=[unit]), unit)
        # Spatial blocks for the bootstrap: the 0.1-degree cell each unit's centre falls in
        # (a coarser 0.2-degree cell for the grid unit itself).
        step = 0.2 if unit == "grid" else 0.1
        df["block"] = ((df["lat"] / step).round().astype(int).astype(str) + "," +
                       (df["lon"] / step).round().astype(int).astype(str))
        df.to_csv(OUT / f"{unit}.csv", index=False)

        enough = (df["policies"] >= MIN_POLICIES) & (df["buildings"] >= MIN_BUILDINGS)
        take_up_tercile = pd.qcut(df.loc[enough, "take_up"], 3, labels=["low", "mid", "high"])
        res = {
            "units_total": int(len(df)),
            "units_used": int(enough.sum()),
            "claim_rate": correlate(df, "claim_rate", "block", enough),
            "damage_ratio": correlate(df, "mean_damage_ratio", "block", enough & (df["damage_claims"] >= MIN_DAMAGE_CLAIMS)),
            "payout_usd": correlate(df, "mean_payout_usd", "block", enough & (df["damage_claims"] >= MIN_DAMAGE_CLAIMS)),
            "claim_count_raw": correlate(df, "claims", "block", enough),
            "claim_rate_sfha": correlate(df, "claim_rate_sfha", "block", df["policies_sfha"] >= MIN_POLICIES),
            "claim_rate_non_sfha": correlate(df, "claim_rate_non_sfha", "block",
                                             (df["policies"] - df["policies_sfha"]) >= MIN_POLICIES),
            "claim_rate_by_take_up": {
                t: correlate(df, "claim_rate", "block", enough & (df.index.isin(take_up_tercile[take_up_tercile == t].index)))
                for t in ("low", "mid", "high")
            },
        }
        results["units"][unit] = res
        print(f"\n== {unit}: {res['units_used']} of {res['units_total']} units used")
        for key in ("claim_rate", "damage_ratio", "payout_usd", "claim_count_raw", "claim_rate_sfha", "claim_rate_non_sfha"):
            r = res[key]
            if "pearson" in r:
                print(f"  {key:<20} n={r['n']:<4} r={r['pearson']:+.2f} {r['pearson_ci95']}  "
                      f"rho={r['spearman']:+.2f} {r['spearman_ci95']}  Moran I(resid)={r['residual_morans_i']['I']:+.2f}")
            else:
                print(f"  {key:<20} n={r['n']} (too few units)")

    (OUT / "results.json").write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    print(f"\ncoverage: {json.dumps(coverage, indent=1)}")


if __name__ == "__main__":
    main()
