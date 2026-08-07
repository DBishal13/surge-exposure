from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Miami-Dade / South Florida coastal strip — FPL service territory, high storm-surge exposure.
# (min_lon, min_lat, max_lon, max_lat)
DEFAULT_DEMO_BBOX = (-80.20, 25.70, -80.10, 25.80)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SURGE_EXPOSURE_", env_file=".env")

    # Relative to the current working directory (repo root in local dev per
    # the README; /app in the container, matching the docker-compose volume
    # mount) rather than derived from this file's install location — a
    # non-editable install (e.g. inside a Docker image) lives under
    # site-packages, so `Path(__file__).parents[N]` doesn't point at the
    # project root there the way it does for an editable/dev install.
    data_dir: Path = Path("data")
    duckdb_path: Path = Path("data") / "cache" / "surge_exposure.duckdb"

    # Overture release version is resolved dynamically at query time from
    # https://stac.overturemaps.org/catalog.json (see data/overture.py) so
    # this never goes stale.
    overture_stac_catalog: str = "https://stac.overturemaps.org/catalog.json"
    overture_buildings_s3: str = (
        "s3://overturemaps-us-west-2/release/{release}/theme=buildings/type=building/*"
    )

    nwps_base_url: str = "https://api.water.noaa.gov/nwps/v1"
    nwm_fim_base_url: str = "https://maps.water.noaa.gov/server/rest/services/nwm/ana_inundation_extent/MapServer"

    storm_surge_geotiff: Path = Path("data") / "raw" / "US_SLOSH_MOM_Inundation_v4.tif"
    storm_surge_download_url: str = (
        "https://www.nhc.noaa.gov/gis/hazardmaps/US_SLOSH_MOM_Inundation_v4.zip"
    )

    nfip_base_url: str = "https://www.fema.gov/api/open/v3/NfipClaims"



settings = Settings()
