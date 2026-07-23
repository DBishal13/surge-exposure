FROM python:3.11-slim

WORKDIR /app

# rasterio/geopandas/duckdb ship self-contained manylinux wheels (bundled
# GDAL/GEOS/PROJ), so no system GDAL packages are needed — but rasterio's
# Linux wheel still dynamically links against system libexpat, which
# python:3.11-slim doesn't include by default.
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

# The NOAA storm-surge raster (~1.6GB download, ~750MB cached) is fetched
# lazily on first use into /app/data — mount that as a volume so it
# survives container restarts instead of being baked into the image.
VOLUME ["/app/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

CMD ["uvicorn", "surge_exposure.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
