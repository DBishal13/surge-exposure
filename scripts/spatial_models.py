"""Spatially corrected inference for the unit-level results (paper §6.2).

For block groups and tracts (paper/data/units/*.csv from validate_units.py),
and for claim rate and damage ratio vs mean MOM depth:

- Dutilleul's (1993) modified t-test: the correlation's significance with an
  effective sample size that accounts for spatial autocorrelation in both
  variables (Clifford, Richardson & Hemon 1989).
- A spatial error model (spreg.ML_Error, 8-nearest-neighbour row-standardized
  weights), whose depth coefficient is compared with plain OLS.

Writes paper/data/units/spatial_models.json.

    python scripts/spatial_models.py
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from libpysal.weights import KNN
from scipy import stats
from scipy.spatial.distance import pdist, squareform
from spreg import OLS, ML_Error

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_units import MIN_BUILDINGS, MIN_DAMAGE_CLAIMS, MIN_POLICIES, OUT  # noqa: E402

N_CLASSES = 13
K_NEIGHBOURS = 8


def _xy_km(lon, lat) -> np.ndarray:
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    return np.column_stack([lon * 111.32 * np.cos(np.radians(lat.mean())), lat * 110.57])


def autocorrelation_matrix(z: np.ndarray, dist: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Pairwise autocorrelation matrix from a Moran's I correlogram: each pair
    gets the coefficient of its distance class; pairs beyond the last class
    get 0, and the diagonal is 1."""
    z = (z - z.mean()) / z.std()
    n = len(z)
    cls = np.digitize(dist, edges) - 1  # -1 below first edge (only the diagonal, d=0), len(edges)-1 beyond
    R = np.zeros((n, n))
    zz = np.outer(z, z)
    off = ~np.eye(n, dtype=bool)
    for k in range(len(edges) - 1):
        mask = (cls == k) & off
        if mask.any():
            R[mask] = zz[mask].mean()
    np.fill_diagonal(R, 1.0)
    return R


def dutilleul(x, y, lon, lat, n_classes: int = N_CLASSES) -> dict:
    """Modified t-test for Pearson r between two spatially autocorrelated
    variables. Effective sample size M = 1 + N^2 / tr(Rx Ry), with Rx, Ry
    estimated from correlograms over equal-width distance classes up to half
    the maximum pairwise distance."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    dist = squareform(pdist(_xy_km(lon, lat)))
    edges = np.linspace(1e-9, dist.max() / 2, n_classes + 1)
    rx = autocorrelation_matrix(x, dist, edges)
    ry = autocorrelation_matrix(y, dist, edges)
    m = 1 + n ** 2 / np.trace(rx @ ry)
    m = float(min(max(m, 3.0), n))
    r = float(np.corrcoef(x, y)[0, 1])
    f = (m - 2) * r ** 2 / (1 - r ** 2)
    return {"n": n, "r": r, "effective_n": m, "F": float(f), "p": float(stats.f.sf(f, 1, m - 2))}


def spatial_error(x, y, lon, lat) -> dict:
    pts = _xy_km(lon, lat)
    w = KNN.from_array(pts, k=K_NEIGHBOURS)
    w.transform = "r"
    X = np.asarray(x, float).reshape(-1, 1)
    Y = np.asarray(y, float).reshape(-1, 1)
    ols = OLS(Y, X, w=w, spat_diag=True, moran=True, name_x=["depth"], name_y="y")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        err = ML_Error(Y, X, w=w, name_x=["depth"], name_y="y")
    # Coefficients are per foot of mean depth; also give the standardized slope.
    sx, sy = float(np.std(X)), float(np.std(Y))
    return {
        "ols_beta": float(ols.betas[1, 0]), "ols_se": float(ols.std_err[1]),
        "ols_residual_moran_i": float(ols.moran_res[0]), "ols_residual_moran_p": float(ols.moran_res[2]),
        "sem_beta": float(err.betas[1, 0]), "sem_se": float(err.std_err[1]),
        "sem_z_p": float(err.z_stat[1][1]), "sem_lambda": float(err.betas[-1, 0]),
        "sem_pseudo_r2": float(err.pr2),
        "ols_std_beta": float(ols.betas[1, 0]) * sx / sy, "sem_std_beta": float(err.betas[1, 0]) * sx / sy,
    }


def main() -> None:
    results = {}
    for unit in ("block_group", "tract"):
        df = pd.read_csv(OUT / f"{unit}.csv")
        enough = (df["policies"] >= MIN_POLICIES) & (df["buildings"] >= MIN_BUILDINGS)
        results[unit] = {}
        for key, col, extra in (("claim_rate", "claim_rate", None),
                                ("damage_ratio", "mean_damage_ratio", df["damage_claims"] >= MIN_DAMAGE_CLAIMS)):
            mask = enough & df[col].notna() & (extra if extra is not None else True)
            d = df[mask]
            res = {"dutilleul": dutilleul(d["mean_surge_ft"], d[col], d["lon"], d["lat"]),
                   "spatial_error": spatial_error(d["mean_surge_ft"], d[col], d["lon"], d["lat"])}
            results[unit][key] = res
            du, se = res["dutilleul"], res["spatial_error"]
            print(f"{unit:<12} {key:<13} n={du['n']:<4} r={du['r']:+.2f}  Dutilleul effective n={du['effective_n']:.0f} "
                  f"p={du['p']:.2g} | OLS b={se['ols_beta']:.4f} (resid I={se['ols_residual_moran_i']:.2f}) "
                  f"SEM b={se['sem_beta']:.4f}±{se['sem_se']:.4f} p={se['sem_z_p']:.2g} lambda={se['sem_lambda']:.2f} "
                  f"std b {se['ols_std_beta']:.2f}->{se['sem_std_beta']:.2f}")
    (OUT / "spatial_models.json").write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {OUT / 'spatial_models.json'}")


if __name__ == "__main__":
    main()
