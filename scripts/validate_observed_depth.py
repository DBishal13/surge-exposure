"""Observed Hurricane Ian flood depth at every Lee County building, from USGS
high-water marks, and a rerun of the unit-level claim analysis with it.

1. Ground: USGS 3DEP ~10 m DEM (NAVD88 m), fetched in tiles from the 3DEP
   ImageServer and sampled at each building centroid.
2. Water surface: inverse-distance-weighted interpolation of the marks'
   surveyed water-surface elevations (NAVD88 ft; k nearest marks within
   MAX_DIST_M). Buildings farther than MAX_DIST_M from every mark are left
   without an observed depth.
3. Observed depth = max(0, water surface - ground).
4. Checks the method by leave-one-out at the marks (predicted vs surveyed
   height above ground), next to Category 1 MOM's error at the same marks.
5. Reruns the block-group/tract correlations with observed depth and with
   Category 1 MOM depth on exactly the same well-covered units.

Outputs paper/data/observed/{hwm_loo.csv,results.json}.

    python scripts/validate_observed_depth.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import rasterio
from rasterio.merge import merge
from scipy import stats
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_categories import load_hwms  # noqa: E402
from validate_units import (  # noqa: E402
    COUNTY_BBOX, MIN_BUILDINGS, MIN_DAMAGE_CLAIMS, MIN_POLICIES, correlate, prepare, unit_table,
)

from surge_exposure.data import storm_surge  # noqa: E402

DEM_DIR = Path("data") / "raw" / "dem"
DEM_PATH = DEM_DIR / "lee_3dep_10m.tif"
DEM_URL = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
DEM_RES_DEG = 1 / 10800  # 1/3 arc-second, ~10 m
TILE_PX = 2000
OUT = Path("paper") / "data" / "observed"
UTM = "EPSG:32617"
M_PER_FT = 0.3048
IDW_K = 8
IDW_POWER = 2
MAX_DIST_M = [2000, 5000]  # main result uses the first; the second is a sensitivity check
MIN_COVERAGE = 0.8  # share of a unit's buildings that need an observed depth


# ---------------------------------------------------------------- ground

def fetch_dem() -> Path:
    if DEM_PATH.exists():
        return DEM_PATH
    DEM_DIR.mkdir(parents=True, exist_ok=True)
    min_lon, min_lat, max_lon, max_lat = COUNTY_BBOX
    step = TILE_PX * DEM_RES_DEG
    tiles = []
    with httpx.Client(timeout=300) as client:
        for i, lon in enumerate(np.arange(min_lon, max_lon, step)):
            for j, lat in enumerate(np.arange(min_lat, max_lat, step)):
                tile = DEM_DIR / f"tile_{i}_{j}.tif"
                if not tile.exists():
                    params = {"bbox": f"{lon},{lat},{lon + step},{lat + step}", "bboxSR": 4326, "imageSR": 4326,
                              "size": f"{TILE_PX},{TILE_PX}", "format": "tiff", "pixelType": "F32",
                              "interpolation": "RSP_BilinearInterpolation", "f": "image"}
                    resp = client.get(DEM_URL, params=params)
                    resp.raise_for_status()
                    tile.write_bytes(resp.content)
                tiles.append(tile)
    srcs = [rasterio.open(t) for t in tiles]
    mosaic, transform = merge(srcs)
    profile = srcs[0].profile | {"height": mosaic.shape[1], "width": mosaic.shape[2], "transform": transform,
                                 "compress": "deflate", "tiled": True, "crs": "EPSG:4326"}
    for s in srcs:
        s.close()
    with rasterio.open(DEM_PATH, "w", **profile) as dst:
        dst.write(mosaic)
    for t in tiles:
        t.unlink()
    return DEM_PATH


def ground_ft(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    with rasterio.open(fetch_dem()) as dem:
        vals = np.array([v[0] for v in dem.sample(zip(lon, lat))], dtype=float)
        if dem.nodata is not None:
            vals[vals == dem.nodata] = np.nan
    vals[(vals < -50) | (vals > 500)] = np.nan
    return vals / M_PER_FT


# ---------------------------------------------------------------- water surface

def idw(tree: cKDTree, values: np.ndarray, xy: np.ndarray, max_dist: float,
        exclude_self: bool = False) -> np.ndarray:
    """IDW of `values` at `xy` from the k nearest marks within max_dist (NaN if none)."""
    k = IDW_K + (1 if exclude_self else 0)
    dist, idx = tree.query(xy, k=k, distance_upper_bound=max_dist)
    if exclude_self:
        dist, idx = dist[:, 1:], idx[:, 1:]
    valid = np.isfinite(dist)
    w = np.where(valid, 1.0 / np.maximum(dist, 1.0) ** IDW_POWER, 0.0)
    v = np.where(valid, values[np.minimum(idx, len(values) - 1)], 0.0)
    wsum = w.sum(axis=1)
    out = np.full(len(xy), np.nan)
    ok = wsum > 0
    out[ok] = (w[ok] * v[ok]).sum(axis=1) / wsum[ok]
    return out


def project(lon, lat) -> np.ndarray:
    from pyproj import Transformer
    x, y = Transformer.from_crs(4326, UTM, always_xy=True).transform(np.asarray(lon), np.asarray(lat))
    return np.column_stack([x, y])


def err_stats(pred: np.ndarray, obs: np.ndarray) -> dict:
    ok = np.isfinite(pred) & np.isfinite(obs)
    e = pred[ok] - obs[ok]
    return {"n": int(ok.sum()), "bias_ft": float(e.mean()), "mae_ft": float(np.abs(e).mean()),
            "rmse_ft": float(np.sqrt((e ** 2).mean())), "pearson": float(stats.pearsonr(pred[ok], obs[ok])[0]),
            "share_within_1ft": float((np.abs(e) <= 1).mean())}


# ---------------------------------------------------------------- main

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    hwms = load_hwms().reset_index(drop=True)
    hwms = storm_surge.sample_surge_class(hwms, raster_path=Path("data/raw/mom/cat1.tif"))
    hwms["survey_ground_ft"] = hwms["elev_ft"] - hwms["height_above_gnd"]
    hwms["dem_ground_ft"] = ground_ft(hwms["longitude_dd"].to_numpy(), hwms["latitude_dd"].to_numpy())
    mark_xy = project(hwms["longitude_dd"], hwms["latitude_dd"])
    tree = cKDTree(mark_xy)
    wse = hwms["elev_ft"].to_numpy(float)

    results = {"dem_vs_survey_ground": err_stats(hwms["dem_ground_ft"].to_numpy(), hwms["survey_ground_ft"].to_numpy()),
               "loo": {}, "units": {}}
    for max_dist in MAX_DIST_M:
        loo_wse = idw(tree, wse, mark_xy, max_dist, exclude_self=True)
        hwms[f"loo_depth_{max_dist}"] = np.maximum(loo_wse - hwms["dem_ground_ft"], 0)
        results["loo"][max_dist] = {
            "observed_interp": err_stats(hwms[f"loo_depth_{max_dist}"].to_numpy(), hwms["height_above_gnd"].to_numpy()),
            "mom_cat1_same_marks": err_stats(
                np.where(np.isfinite(hwms[f"loo_depth_{max_dist}"]), hwms["surge_ft"], np.nan),
                hwms["height_above_gnd"].to_numpy()),
        }
    hwms.drop(columns="geometry").to_csv(OUT / "hwm_loo.csv", index=False)

    buildings, claims, policies, _ = prepare()
    b_xy = project(buildings["lon"], buildings["lat"])
    b_ground = ground_ft(buildings["lon"].to_numpy(), buildings["lat"].to_numpy())

    for max_dist in MAX_DIST_M:
        obs_depth = np.maximum(idw(tree, wse, b_xy, max_dist) - b_ground, 0)
        covered = np.isfinite(obs_depth)
        res = {"buildings_covered": int(covered.sum()), "share_buildings_covered": float(covered.mean())}
        for unit in ("block_group", "tract"):
            cov = pd.Series(covered, index=buildings.index).groupby(buildings[unit]).mean()
            good_units = set(cov[cov >= MIN_COVERAGE].index)
            b_units = buildings[buildings[unit].isin(good_units)]
            obs_b = b_units.assign(surge_ft=obs_depth[buildings[unit].isin(good_units).to_numpy()])
            obs_b = obs_b[np.isfinite(obs_b["surge_ft"])]
            tables = {"observed": unit_table(obs_b, claims, policies, unit),
                      "mom_cat1": unit_table(b_units, claims, policies, unit)}
            res[unit] = {"units_covered": len(good_units)}
            for name, df in tables.items():
                df = df.set_index(unit)
                enough = (df["policies"] >= MIN_POLICIES) & (df["buildings"] >= MIN_BUILDINGS)
                res[unit][name] = {
                    "claim_rate": correlate(df.reset_index(), "claim_rate", "block", enough.to_numpy()),
                    "damage_ratio": correlate(df.reset_index(), "mean_damage_ratio", "block",
                                              (enough & (df["damage_claims"] >= MIN_DAMAGE_CLAIMS)).to_numpy()),
                }
            # Which depth carries the signal when both enter one regression (standardized)?
            o = tables["observed"].set_index(unit)
            m = tables["mom_cat1"].set_index(unit)
            j = o[["mean_surge_ft", "claim_rate", "policies", "buildings"]].join(
                m[["mean_surge_ft"]].rename(columns={"mean_surge_ft": "mom_ft"}), how="inner")
            j = j[(j["policies"] >= MIN_POLICIES) & (j["buildings"] >= MIN_BUILDINGS)].dropna()
            z = (j - j.mean()) / j.std()
            X = np.column_stack([np.ones(len(z)), z["mean_surge_ft"], z["mom_ft"]])
            beta, *_ = np.linalg.lstsq(X, z["claim_rate"], rcond=None)
            res[unit]["joint_std_beta_claim_rate"] = {"observed": float(beta[1]), "mom_cat1": float(beta[2]),
                                                      "n": int(len(z)),
                                                      "r_observed_vs_mom": float(np.corrcoef(j["mean_surge_ft"], j["mom_ft"])[0, 1])}
        results["units"][max_dist] = res

    (OUT / "results.json").write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")

    g = results["dem_vs_survey_ground"]
    print(f"DEM vs surveyed ground at marks: bias {g['bias_ft']:+.2f} ft, RMSE {g['rmse_ft']:.2f} ft (n={g['n']})")
    for max_dist in MAX_DIST_M:
        lo, mo = results["loo"][max_dist]["observed_interp"], results["loo"][max_dist]["mom_cat1_same_marks"]
        print(f"\n== max distance {max_dist} m")
        print(f"  leave-one-out at marks: interpolated bias {lo['bias_ft']:+.2f} RMSE {lo['rmse_ft']:.2f} r {lo['pearson']:.2f} "
              f"| MOM cat1 bias {mo['bias_ft']:+.2f} RMSE {mo['rmse_ft']:.2f} r {mo['pearson']:.2f} (n={lo['n']})")
        res = results["units"][max_dist]
        print(f"  buildings covered: {res['buildings_covered']:,} ({res['share_buildings_covered']:.0%})")
        for unit in ("block_group", "tract"):
            u = res[unit]
            for name in ("observed", "mom_cat1"):
                for key in ("claim_rate", "damage_ratio"):
                    r = u[name][key]
                    txt = (f"n={r['n']:<4} r={r['pearson']:+.2f} [{r['pearson_ci95'][0]:+.2f},{r['pearson_ci95'][1]:+.2f}] "
                           f"rho={r['spearman']:+.2f}") if "pearson" in r else f"n={r['n']} (too few)"
                    print(f"  {unit:<12} {name:<9} {key:<13} {txt}")
            jb = u["joint_std_beta_claim_rate"]
            print(f"  {unit:<12} joint std beta (claim rate): observed {jb['observed']:+.2f}, MOM {jb['mom_cat1']:+.2f}, "
                  f"r(obs, MOM) {jb['r_observed_vs_mom']:.2f}, n={jb['n']}")


if __name__ == "__main__":
    main()
