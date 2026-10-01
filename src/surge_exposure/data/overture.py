"""Fetch building footprints for a bounding box directly from Overture Maps'
public GeoParquet on S3, using DuckDB's spatial + httpfs extensions.

No download or account needed — the bbox struct column on each Overture
parquet file lets DuckDB push the filter down and only pull the row groups
that overlap the requested area.
"""

from __future__ import annotations

import duckdb
import geopandas as gpd

from surge_exposure.config import settings

BBox = tuple[float, float, float, float]


def _connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL spatial; INSTALL httpfs;")
    con.execute("LOAD spatial; LOAD httpfs;")
    con.execute("SET s3_region='us-west-2';")
    return con


def _latest_release(con: duckdb.DuckDBPyConnection) -> str:
    """Resolve the current release version from Overture's STAC catalog so
    queries never go stale as new releases ship."""
    return con.execute(
        f"SELECT latest FROM '{settings.overture_stac_catalog}'"
    ).fetchone()[0]


def limit_clause(limit: int | None, sample: str = "first", seed: int = 42) -> str:
    """SQL that caps the number of buildings returned.

    sample="first" keeps whatever rows DuckDB's scan reaches first. That is fast,
    and fine for drawing a map, but the scan order over Overture's partitioned
    GeoParquet is not spatially uniform, so the rows cluster in part of the
    bbox (see paper §5.3). sample="random" orders rows by a seeded hash of the
    building id before limiting: a deterministic, spatially unbiased sample, at
    the cost of reading every matching row first. Use it for anything that
    averages over the sample, such as the validation study.
    """
    if not limit:
        return ""
    if sample == "first":
        return f"LIMIT {int(limit)}"
    if sample == "random":
        return f"ORDER BY hash(id || '{int(seed)}') LIMIT {int(limit)}"
    raise ValueError(f"sample must be 'first' or 'random', not {sample!r}")


def get_buildings(
    bbox: BBox, limit: int | None = None, sample: str = "first", seed: int = 42
) -> gpd.GeoDataFrame:
    """Return Overture building footprints intersecting bbox as a GeoDataFrame.

    bbox: (min_lon, min_lat, max_lon, max_lat) in EPSG:4326.
    limit / sample / seed: optional cap on the number of buildings; see
    limit_clause for why sample="random" matters for statistics.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    con = _connect()
    release = _latest_release(con)
    buildings_url = settings.overture_buildings_s3.format(release=release)
    query = f"""
        SELECT
            id,
            names.primary AS name,
            subtype,
            class,
            height,
            num_floors,
            ST_AsWKB(geometry) AS geometry_wkb
        FROM read_parquet(
            '{buildings_url}',
            filename = true,
            hive_partitioning = 1
        )
        WHERE bbox.xmin <= {max_lon} AND bbox.xmax >= {min_lon}
          AND bbox.ymin <= {max_lat} AND bbox.ymax >= {min_lat}
        {limit_clause(limit, sample, seed)}
    """
    df = con.execute(query).fetch_df()
    con.close()

    gdf = gpd.GeoDataFrame(
        df.drop(columns=["geometry_wkb"]),
        geometry=gpd.GeoSeries.from_wkb(df["geometry_wkb"].apply(bytes)),
        crs="EPSG:4326",
    )
    return gdf


if __name__ == "__main__":
    from surge_exposure.config import DEFAULT_DEMO_BBOX

    buildings = get_buildings(DEFAULT_DEMO_BBOX, limit=25)
    print(buildings[["id", "subtype", "class", "height"]])
    print(f"{len(buildings)} buildings fetched")
