"""Render the Lee County NFIP validation results (paper/data/lee_county_grid.csv,
produced by validate_exposure_bins.py) as a light/dark scatter-pair PNG for
paper/paper.md and the README.

Two panels sharing an x-axis (mean exposure score per grid cell) rather than one
dual-axis chart, since claim count and mean payout are different-scale measures.

Run after validate_exposure_bins.py has produced the CSV:

    python scripts/plot_validation_chart.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = REPO_ROOT / "paper" / "data" / "lee_county_grid.csv"
FIGURES_DIR = REPO_ROOT / "paper" / "figures"

PANELS = [
    ("claim_count", "Claim count", "{x:,.0f}"),
    ("mean_amount_paid", "Mean claim payout ($)", "${x:,.0f}"),
]

THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "primary": "#0b0b0b",
        "secondary": "#52514e",
        "muted": "#898781",
        "gridline": "#e1e0d9",
        "axis": "#c3c2b7",
        "accent": "#2a78d6",
    },
    "dark": {
        "surface": "#1a1a19",
        "primary": "#ffffff",
        "secondary": "#c3c2b7",
        "muted": "#898781",
        "gridline": "#2c2c2a",
        "axis": "#383835",
        "accent": "#3987e5",
    },
}

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Segoe UI", "system-ui", "DejaVu Sans"]


def _corr(df: pd.DataFrame, col: str) -> float:
    return float(np.corrcoef(df["mean_exposure_score"], df[col])[0, 1])


def render(df: pd.DataFrame, theme: dict, out_path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(9, 4), facecolor=theme["surface"])
    fig.suptitle(
        "Lee County, FL — exposure score vs. real NFIP claims (5 grid cells)",
        color=theme["primary"],
        fontsize=12,
        fontweight="bold",
        x=0.02,
        ha="left",
    )

    for ax, (col, title, fmt) in zip(axes, PANELS):
        ax.set_facecolor(theme["surface"])
        r = _corr(df, col)

        x = df["mean_exposure_score"].to_numpy()
        y = df[col].to_numpy()
        slope, intercept = np.polyfit(x, y, 1)
        x_line = np.linspace(x.min(), x.max(), 2)
        ax.plot(x_line, slope * x_line + intercept, color=theme["accent"], linewidth=2, alpha=0.45, zorder=1)

        ax.scatter(
            x, y, s=110, color=theme["accent"],
            edgecolors=theme["surface"], linewidths=2, zorder=2,
        )

        ax.set_title(f"{title}  (r = {r:.2f})", color=theme["primary"], fontsize=11, pad=10)
        ax.set_xlabel("Mean exposure score", color=theme["secondary"], fontsize=10)

        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _, fmt=fmt: fmt.format(x=v)))
        ax.tick_params(colors=theme["muted"], labelsize=9)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("bottom", "left"):
            ax.spines[spine].set_color(theme["axis"])
        ax.grid(axis="y", color=theme["gridline"], linewidth=1, zorder=0)
        ax.set_axisbelow(True)

    fig.tight_layout(rect=(0, 0, 1, 0.90))
    fig.savefig(out_path, dpi=200, facecolor=theme["surface"])
    plt.close(fig)


def main() -> None:
    df = pd.read_csv(CSV_PATH)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    for mode, theme in THEMES.items():
        out_path = FIGURES_DIR / f"validation-chart-{mode}.png"
        render(df, theme, out_path)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
