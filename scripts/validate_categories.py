"""Which SLOSH MOM category best matches Hurricane Ian in Lee County?

Two checks for each of NOAA's high-tide MOM rasters, Category 1-5
(scripts/fetch_mom_categories.py downloads them to data/raw/mom/):

1. Observed surge: MOM depth vs USGS high-water-mark height above ground
   (STN event 325, coastal marks of fair quality or better).
2. Insured losses: re-score every Lee County building with that category and
   rerun the unit-level claim-rate / damage-ratio correlations of
   validate_units.py.

Outputs paper/data/categories/{hwm_points.csv,results.json}.

    python scripts/validate_categories.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import httpx
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_units import (  # noqa: E402
    MIN_BUILDINGS, MIN_DAMAGE_CLAIMS, MIN_POLICIES, correlate, prepare, unit_table,
)

from surge_exposure.data import storm_surge  # noqa: E402

MOM_DIR = Path("data") / "raw" / "mom"
HWM_PATH = Path("data") / "raw" / "usgs" / "ian_hwms_fl.json"
HWM_URL = "https://stn.wim.usgs.gov/STNServices/HWMs/FilteredHWMs.json?Event=325&States=FL"
OUT = Path("paper") / "data" / "categories"
CATEGORIES = [1, 2, 3, 4, 5]
GOOD_QUALITY = {1, 2, 3}  # Excellent (±0.05 ft), Good (±0.10 ft), Fair (±0.20 ft)


def load_hwms() -> gpd.GeoDataFrame:
    if not HWM_PATH.exists():
        HWM_PATH.parent.mkdir(parents=True, exist_ok=True)
        HWM_PATH.write_bytes(httpx.get(HWM_URL, timeout=120).content)
    d = pd.DataFrame(json.loads(HWM_PATH.read_text(encoding="utf-8")))
    d = d[d["countyName"].str.contains("Lee", na=False) & d["hwm_environment"].eq("Coastal")
          & d["hwm_quality_id"].isin(GOOD_QUALITY) & d["height_above_gnd"].notna()]
    return gpd.GeoDataFrame(d, geometry=gpd.points_from_xy(d["longitude_dd"], d["latitude_dd"]), crs=4326)


def hwm_metrics(obs: pd.Series, mom: pd.Series) -> dict:
    err = mom - obs
    return {
        "n": int(len(obs)),
        "observed_mean_ft": float(obs.mean()),
        "mom_mean_ft": float(mom.mean()),
        "bias_ft": float(err.mean()),
        "mae_ft": float(err.abs().mean()),
        "rmse_ft": float(np.sqrt((err ** 2).mean())),
        "pearson": float(stats.pearsonr(mom, obs)[0]),
        "spearman": float(stats.spearmanr(mom, obs)[0]),
        "share_mom_dry": float((mom == 0).mean()),
        "share_within_1ft": float((err.abs() <= 1.0).mean()),
    }


def summarize(r: dict) -> str:
    if "pearson" not in r:
        return f"n={r['n']} (too few)"
    lo, hi = r["pearson_ci95"]
    return f"n={r['n']:<4} r={r['pearson']:+.2f} [{lo:+.2f},{hi:+.2f}] rho={r['spearman']:+.2f}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    hwms = load_hwms()
    buildings, claims, policies, _ = prepare()
    results = {"hwm": {}, "units": {}}

    for cat in CATEGORIES:
        raster = MOM_DIR / f"cat{cat}.tif"
        sampled = storm_surge.sample_surge_class(hwms, raster_path=raster)
        hwms[f"mom_cat{cat}_ft"] = sampled["surge_ft"].to_numpy()
        results["hwm"][cat] = hwm_metrics(hwms["height_above_gnd"], hwms[f"mom_cat{cat}_ft"])

        b = buildings.drop(columns=["surge_class", "surge_ft"])
        b = storm_surge.sample_surge_class(b, raster_path=raster)
        results["units"][cat] = {}
        for unit in ("block_group", "tract", "grid"):
            df = unit_table(b, claims, policies, unit)
            enough = (df["policies"] >= MIN_POLICIES) & (df["buildings"] >= MIN_BUILDINGS)
            results["units"][cat][unit] = {
                "claim_rate": correlate(df, "claim_rate", "block", enough),
                "damage_ratio": correlate(df, "mean_damage_ratio", "block",
                                          enough & (df["damage_claims"] >= MIN_DAMAGE_CLAIMS)),
                "claim_rate_non_sfha": correlate(df, "claim_rate_non_sfha", "block",
                                                 (df["policies"] - df["policies_sfha"]) >= MIN_POLICIES),
                "share_buildings_wet": float((b["surge_ft"] > 0).mean()),
            }

        h = results["hwm"][cat]
        print(f"\n== Category {cat}: HWM bias {h['bias_ft']:+.2f} ft, RMSE {h['rmse_ft']:.2f}, "
              f"r {h['pearson']:.2f}, within 1 ft {h['share_within_1ft']:.0%}, dry at {h['share_mom_dry']:.0%} of marks")
        for unit, res in results["units"][cat].items():
            print(f"  {unit:<12} claim_rate {summarize(res['claim_rate'])} | "
                  f"damage_ratio {summarize(res['damage_ratio'])}")

    cols = ["hwm_id", "latitude_dd", "longitude_dd", "hwmTypeName", "hwmQualityName", "elev_ft",
            "height_above_gnd"] + [f"mom_cat{c}_ft" for c in CATEGORIES]
    hwms[cols].to_csv(OUT / "hwm_points.csv", index=False)
    (OUT / "results.json").write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT / 'hwm_points.csv'} and {OUT / 'results.json'}")


if __name__ == "__main__":
    main()
