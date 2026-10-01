"""Render the unit-level validation results (paper/data/units/, produced by
validate_units.py) as a light/dark PNG for paper/paper.md §6.2.

Two rows (claim rate, damage ratio) by three columns (block group, tract,
0.1° grid), each a scatter of the outcome against mean SLOSH MOM depth, with
Pearson r and its spatial-bootstrap 95% CI from results.json. The units
included are the same as in the analysis (same thresholds).

    python scripts/plot_units_chart.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_validation_chart import THEMES  # noqa: E402
from validate_units import MIN_BUILDINGS, MIN_DAMAGE_CLAIMS, MIN_POLICIES, OUT  # noqa: E402

FIGURES_DIR = OUT.parents[1] / "figures"
UNITS = [("block_group", "Block group"), ("tract", "Tract"), ("grid", "0.1° grid")]
ROWS = [
    ("claim_rate", "claim_rate", "Claim rate (claims ÷ policies)"),
    ("mean_damage_ratio", "damage_ratio", "Mean damage ratio"),
]


def _included(df: pd.DataFrame, col: str) -> pd.DataFrame:
    keep = (df["policies"] >= MIN_POLICIES) & (df["buildings"] >= MIN_BUILDINGS) & df[col].notna()
    if col == "mean_damage_ratio":
        keep &= df["damage_claims"] >= MIN_DAMAGE_CLAIMS
    return df[keep]


def render(results: dict, theme: dict, out_path: Path) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(11, 6.6), facecolor=theme["surface"], sharex="col")
    fig.suptitle(
        "Lee County, FL: SLOSH MOM depth vs Hurricane Ian NFIP outcomes",
        color=theme["primary"], fontsize=12, fontweight="bold", x=0.02, ha="left",
    )
    for j, (unit, unit_label) in enumerate(UNITS):
        df = pd.read_csv(OUT / f"{unit}.csv")
        for i, (col, key, ylabel) in enumerate(ROWS):
            ax = axes[i, j]
            ax.set_facecolor(theme["surface"])
            d = _included(df, col)
            x, y = d["mean_surge_ft"].to_numpy(), d[col].to_numpy()
            size = 110 if unit == "grid" else (28 if unit == "tract" else 14)
            ax.scatter(x, y, s=size, color=theme["accent"], alpha=0.55 if unit != "grid" else 0.9,
                       edgecolors=theme["surface"], linewidths=0.6 if unit != "grid" else 2, zorder=2)
            slope, intercept = np.polyfit(x, y, 1)
            xl = np.linspace(x.min(), x.max(), 2)
            ax.plot(xl, slope * xl + intercept, color=theme["primary"], linewidth=1.5, alpha=0.6, zorder=3)

            r = results["units"][unit][key]
            lo, hi = r["pearson_ci95"]
            ax.set_title(f"{unit_label}  r = {r['pearson']:.2f} [{lo:.2f}, {hi:.2f}]  n = {r['n']}",
                         color=theme["primary"], fontsize=9.5, pad=8)
            if j == 0:
                ax.set_ylabel(ylabel, color=theme["secondary"], fontsize=9.5)
            if i == 1:
                ax.set_xlabel("Mean MOM surge depth (ft)", color=theme["secondary"], fontsize=9.5)
            ax.tick_params(colors=theme["muted"], labelsize=8.5)
            for spine in ("top", "right"):
                ax.spines[spine].set_visible(False)
            for spine in ("bottom", "left"):
                ax.spines[spine].set_color(theme["axis"])
            ax.grid(axis="y", color=theme["gridline"], linewidth=1, zorder=0)
            ax.set_axisbelow(True)

    fig.text(0.02, 0.01, "Brackets: 95% spatial block-bootstrap CI. Units below the inclusion "
             "thresholds in §5.5 are omitted.", color=theme["muted"], fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    fig.savefig(out_path, dpi=200, facecolor=theme["surface"])
    plt.close(fig)


def main() -> None:
    results = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    for mode, theme in THEMES.items():
        out_path = FIGURES_DIR / f"units-chart-{mode}.png"
        render(results, theme, out_path)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
