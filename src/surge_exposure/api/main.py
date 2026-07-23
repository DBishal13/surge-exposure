from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from surge_exposure.api.mapping import build_exposure_map
from surge_exposure.config import DEFAULT_DEMO_BBOX
from surge_exposure.pipeline import run_exposure_pipeline

app = FastAPI(
    title="SurgeExposure API",
    description="Storm-surge & flood exposure scoring for building footprints.",
)

STATIC_DIR = Path(__file__).parent / "static"

# Coastal, storm-surge-prone demo regions -- hand-picked so the frontend has
# working one-click examples without a geocoding round trip.
PRESET_LOCATIONS = [
    {"label": "Miami-Dade, FL", "bbox": DEFAULT_DEMO_BBOX},
    {"label": "Tampa, FL", "bbox": (-82.48, 27.90, -82.42, 27.96)},
    {"label": "New Orleans, LA", "bbox": (-90.10, 29.93, -90.02, 29.98)},
    {"label": "Galveston, TX", "bbox": (-94.85, 29.28, -94.78, 29.34)},
]

# Half-width/height (degrees) of the bbox built around a geocoded point --
# roughly a 5km square, small enough to keep the live Overture query fast.
GEOCODE_BBOX_HALF_SPAN = 0.025


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float]:
    if bbox is None:
        return DEFAULT_DEMO_BBOX
    parts = bbox.split(",")
    if len(parts) != 4:
        raise HTTPException(400, "bbox must be 'min_lon,min_lat,max_lon,max_lat'")
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    except ValueError as e:
        raise HTTPException(400, "bbox values must be numeric") from e
    return (min_lon, min_lat, max_lon, max_lat)


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/locations")
def locations() -> list[dict]:
    """Preset demo regions the frontend offers as one-click examples."""
    return PRESET_LOCATIONS


@app.get("/geocode")
def geocode(q: str = Query(..., min_length=2)) -> dict:
    """Resolve a free-text place name to a bbox via OpenStreetMap Nominatim."""
    resp = httpx.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": q, "format": "json", "limit": 1},
        headers={"User-Agent": "surge-exposure/0.1 (personal portfolio project)"},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise HTTPException(404, f"No location found for '{q}'")
    r = results[0]
    lat, lon = float(r["lat"]), float(r["lon"])
    span = GEOCODE_BBOX_HALF_SPAN
    return {
        "display_name": r["display_name"],
        "lat": lat,
        "lon": lon,
        "bbox": (lon - span, lat - span, lon + span, lat + span),
    }


@app.get("/exposure")
def exposure(
    bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    limit: int | None = Query(500, description="max buildings to score"),
) -> JSONResponse:
    parsed_bbox = _parse_bbox(bbox)
    gdf = run_exposure_pipeline(parsed_bbox, building_limit=limit)
    if gdf.empty:
        return JSONResponse({"type": "FeatureCollection", "features": []})
    return JSONResponse(json.loads(gdf.to_json()))


@app.get("/map", response_class=HTMLResponse)
def map_view(
    bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    limit: int | None = Query(300, description="max buildings to score"),
) -> str:
    parsed_bbox = _parse_bbox(bbox)
    gdf = run_exposure_pipeline(parsed_bbox, building_limit=limit)
    fmap = build_exposure_map(gdf)
    return fmap.get_root().render()
