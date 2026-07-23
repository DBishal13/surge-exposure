from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from surge_exposure.api.mapping import build_exposure_map
from surge_exposure.config import DEFAULT_DEMO_BBOX
from surge_exposure.pipeline import run_exposure_pipeline

app = FastAPI(
    title="SurgeExposure API",
    description="Storm-surge & flood exposure scoring for building footprints.",
)


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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


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
