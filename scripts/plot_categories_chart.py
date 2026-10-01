"""Render the MOM-category comparison (paper/data/categories/, produced by
validate_categories.py) as a light/dark PNG for paper/paper.md §6.3.

Left: USGS high-water-mark depth vs MOM depth for Category 1 and Category 4
(Ian's landfall category), with a 1:1 line. Right: block-group correlation of
mean MOM depth with claim rate and damage ratio, by category, with 95%
spatial-bootstrap CIs.

    python scripts/plot_categories_chart.py
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

DATA = Path("paper") / "data" / "categories"
FIGURES_DIR = Path("paper") / "figures"


def _style(ax, theme):
    ax.set_facecolor(theme["surface"])
    ax.tick_params(colors=theme["muted"], labelsize=8.5)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("bottom", "left"):
        ax.spines[spine].set_color(theme["axis"])
    ax.grid(color=theme["gridline"], linewidth=1, zorder=0)
    ax.set_axisbelow(True)


def render(points: pd.DataFrame, results: dict, theme: dict, out_path: Path) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.4), facecolor=theme["surface"])
    fig.suptitle("Which SLOSH MOM category matches Hurricane Ian in Lee County?",
                 color=theme["primary"], fontsize=12, fontweight="bold", x=0.02, ha="left")

    _style(ax1, theme)
    obs = points["height_above_gnd"]
    for cat, color, marker in ((4, theme["muted"], "s"), (1, theme["accent"], "o")):
        h = results["hwm"][str(cat)]
        ax1.scatter(obs, points[f"mom_cat{cat}_ft"], s=22, color=color, marker=marker, alpha=0.75,
                    edgecolors=theme["surface"], linewidths=0.5, zorder=2,
                    label=f"Category {cat}: bias {h['bias_ft']:+.1f} ft, RMSE {h['rmse_ft']:.1f} ft")
    top = float(max(obs.max(), points["mom_cat4_ft"].max())) + 1
    ax1.plot([0, top], [0, top], color=theme["primary"], linewidth=1, alpha=0.5, zorder=1)
    ax1.text(top * 0.97, top * 0.92, "1:1", color=theme["secondary"], fontsize=8.5, ha="right")
    ax1.set_xlabel("Observed high-water mark, height above ground (ft)", color=theme["secondary"], fontsize=9.5)
    ax1.set_ylabel("MOM depth at the mark (ft)", color=theme["secondary"], fontsize=9.5)
    ax1.set_title(f"USGS high-water marks (n = {len(points)})", color=theme["primary"], fontsize=10, pad=8)
    leg = ax1.legend(fontsize=8, frameon=False, loc="lower right")
    for t in leg.get_texts():
        t.set_color(theme["secondary"])

    _style(ax2, theme)
    cats = np.array([1, 2, 3, 4, 5])
    for key, label, offset, color in (("claim_rate", "Claim rate", -0.12, theme["accent"]),
                                      ("damage_ratio", "Damage ratio", 0.12, theme["muted"])):
        r = [results["units"][str(c)]["block_group"][key] for c in cats]
        est = np.array([x["pearson"] for x in r])
        lo = est - np.array([x["pearson_ci95"][0] for x in r])
        hi = np.array([x["pearson_ci95"][1] for x in r]) - est
        ax2.errorbar(cats + offset, est, yerr=[lo, hi], fmt="o", color=color, ecolor=color,
                     elinewidth=1.5, capsize=3, markersize=6, label=label, zorder=2)
    ax2.axhline(0, color=theme["axis"], linewidth=1)
    ax2.set_xticks(cats)
    ax2.set_xticklabels([f"Cat {c}" for c in cats])
    ax2.set_ylabel("Pearson r with mean MOM depth", color=theme["secondary"], fontsize=9.5)
    ax2.set_title("NFIP outcomes by block group (n = 457 / 209)", color=theme["primary"], fontsize=10, pad=8)
    leg = ax2.legend(fontsize=8.5, frameon=False, loc="upper right")
    for t in leg.get_texts():
        t.set_color(theme["secondary"])

    fig.text(0.02, 0.01, "Ian made landfall as a Category 4. Error bars: 95% spatial block-bootstrap CI.",
             color=theme["muted"], fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    fig.savefig(out_path, dpi=200, facecolor=theme["surface"])
    plt.close(fig)


def main() -> None:
    points = pd.read_csv(DATA / "hwm_points.csv")
    results = json.loads((DATA / "results.json").read_text(encoding="utf-8"))
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    for mode, theme in THEMES.items():
        out_path = FIGURES_DIR / f"categories-chart-{mode}.png"
        render(points, results, theme, out_path)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
