"""Client for NOAA's National Water Prediction Service (NWPS) API.

https://api.water.noaa.gov/nwps/v1 — official streamflow forecasts, gauge
observations, and CatFIM (Categorical Flood Inundation Mapping) status for
river gauges. Per NOAA, this API is "not supported 24/7 and may be modified
without advance notice" — callers should cache responses locally.
"""

from __future__ import annotations

import httpx

from surge_exposure.config import settings

BBox = tuple[float, float, float, float]


class NWPSClient:
    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        self.base_url = base_url or settings.nwps_base_url
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "NWPSClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def gauges_in_bbox(self, bbox: BBox, catfim: bool = False) -> list[dict]:
        """Return gauge metadata for gauges within bbox.

        bbox: (min_lon, min_lat, max_lon, max_lat). NWPS expects the four
        bounds as separate bbox.xmin/ymin/xmax/ymax query params (EPSG:4326)
        rather than a single comma-joined value.
        """
        min_lon, min_lat, max_lon, max_lat = bbox
        params = {
            "bbox.xmin": min_lon,
            "bbox.ymin": min_lat,
            "bbox.xmax": max_lon,
            "bbox.ymax": max_lat,
            "srid": "EPSG_4326",
        }
        if catfim:
            params["catfim"] = "true"
        resp = self._client.get("/gauges", params=params)
        resp.raise_for_status()
        return resp.json().get("gauges", [])

    def gauge(self, identifier: str) -> dict:
        resp = self._client.get(f"/gauges/{identifier}")
        resp.raise_for_status()
        return resp.json()

    def gauge_stageflow(self, identifier: str, product: str | None = None) -> dict:
        """product: 'observed' or 'forecast' (omit for both)."""
        path = f"/gauges/{identifier}/stageflow"
        if product:
            path += f"/{product}"
        resp = self._client.get(path)
        resp.raise_for_status()
        return resp.json()

    def reach_streamflow(self, reach_id: str, series: str = "short_range") -> dict:
        """series: analysis_assimilation | short_range | medium_range |
        long_range | medium_range_blend."""
        resp = self._client.get(
            f"/reaches/{reach_id}/streamflow", params={"series": series}
        )
        resp.raise_for_status()
        return resp.json()


if __name__ == "__main__":
    from surge_exposure.config import DEFAULT_DEMO_BBOX

    with NWPSClient() as client:
        gauges = client.gauges_in_bbox(DEFAULT_DEMO_BBOX)
        print(f"{len(gauges)} gauges found in demo bbox")
        for g in gauges[:5]:
            print(g.get("lid"), g.get("name"))
