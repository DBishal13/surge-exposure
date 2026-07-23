"""Bake exposure scores + a colorized storm-surge-extent PNG for a curated
set of coastal/beach demo regions, for the static GitHub Pages showcase in
docs/. This is a one-off local build step, not part of the served app.

Run against the already-cached SLOSH raster (see README for how to fetch it):

    source .venv/bin/activate
    python scripts/precompute_regions.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.windows import bounds as window_bounds
from rasterio.windows import from_bounds

from surge_exposure.config import settings
from surge_exposure.pipeline import run_exposure_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DATA = REPO_ROOT / "docs" / "data"

# Tight bboxes hugging the actual coastline/beach rather than whole cities --
# a city-wide box is mostly inland "none" buildings, which makes for a
# boring demo. (min_lon, min_lat, max_lon, max_lat)
REGIONS = [
    {"slug": "south-beach-miami", "label": "South Beach, Miami, FL", "bbox": (-80.140, 25.765, -80.125, 25.800)},
    {"slug": "clearwater-beach", "label": "Clearwater Beach, FL", "bbox": (-82.835, 27.965, -82.815, 27.985)},
    {"slug": "fort-myers-beach", "label": "Fort Myers Beach, FL", "bbox": (-81.965, 26.435, -81.930, 26.470)},
    {"slug": "french-quarter-nola", "label": "French Quarter, New Orleans, LA", "bbox": (-90.075, 29.955, -90.055, 29.970)},
    {"slug": "galveston-seawall", "label": "Galveston Seawall, TX", "bbox": (-94.820, 29.280, -94.780, 29.300)},
    {"slug": "charleston-battery", "label": "Charleston Battery, SC", "bbox": (-79.945, 32.760, -79.920, 32.790)},
    {"slug": "outer-banks-nags-head", "label": "Nags Head, Outer Banks, NC", "bbox": (-75.665, 35.930, -75.610, 35.980)},
    {"slug": "ocean-city-md", "label": "Ocean City, MD", "bbox": (-75.100, 38.320, -75.075, 38.360)},
]

BUILDING_LIMIT = 1000

# Same status-severity palette as the app (references/palette.md status
# roles): good -> warning -> serious -> critical by surge depth band.
DEPTH_BANDS = [
    (1, 3, "0ca30c"),    # ~0.5-2.5ft -> good
    (4, 6, "fab219"),    # ~3.5-5.5ft -> warning
    (7, 10, "ec835a"),   # ~6.5-9.5ft -> serious
    (11, 21, "d03b3b"),  # ~10.5ft+   -> critical
]
OVERLAY_ALPHA = 110


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def render_surge_png(bbox: tuple[float, float, float, float], out_path: Path) -> tuple[float, float, float, float]:
    """Crop the SLOSH raster to bbox and render a translucent depth-band PNG
    (transparent where there's no inundation). Returns the exact bounds of
    the rendered window (pixel-snapped, so not identical to `bbox`) for
    accurate Leaflet ImageOverlay placement."""
    with rasterio.open(settings.storm_surge_geotiff) as src:
        window = from_bounds(*bbox, transform=src.transform)
        classes = src.read(1, window=window)
        actual_bounds = window_bounds(window, transform=src.transform)

    rgba = np.zeros((*classes.shape, 4), dtype=np.uint8)
    for lo, hi, hex_color in DEPTH_BANDS:
        mask = (classes >= lo) & (classes <= hi)
        rgba[mask, :3] = _hex_to_rgb(hex_color)
        rgba[mask, 3] = OVERLAY_ALPHA

    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(out_path)
    return actual_bounds


def main() -> None:
    if not settings.storm_surge_geotiff.exists():
        raise SystemExit(
            f"{settings.storm_surge_geotiff} not found -- run "
            "`python -m surge_exposure.data.storm_surge` first."
        )

    manifest = []
    for region in REGIONS:
        slug, label, bbox = region["slug"], region["label"], region["bbox"]
        print(f"[{slug}] scoring buildings...")
        gdf = run_exposure_pipeline(bbox, building_limit=BUILDING_LIMIT)

        geojson_path = DOCS_DATA / f"{slug}.geojson"
        geojson_path.parent.mkdir(parents=True, exist_ok=True)
        geojson_path.write_text(gdf.to_json() if not gdf.empty else '{"type":"FeatureCollection","features":[]}')

        print(f"[{slug}] rendering surge overlay...")
        png_path = DOCS_DATA / f"{slug}-surge.png"
        surge_bounds = render_surge_png(bbox, png_path)

        counts = gdf["exposure_category"].value_counts().to_dict() if not gdf.empty else {}
        manifest.append(
            {
                "slug": slug,
                "label": label,
                "bbox": list(bbox),
                "surge_png": png_path.name,
                "surge_bounds": list(surge_bounds),  # (min_lon, min_lat, max_lon, max_lat)
                "building_count": len(gdf),
                "category_counts": counts,
            }
        )
        print(f"[{slug}] {len(gdf)} buildings, categories={counts}")

    (DOCS_DATA / "regions.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nWrote {len(manifest)} regions to {DOCS_DATA}")


if __name__ == "__main__":
    main()
