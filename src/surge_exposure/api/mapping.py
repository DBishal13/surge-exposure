from __future__ import annotations

import folium
import geopandas as gpd

CATEGORY_COLORS = {
    "severe": "#8b0000",
    "high": "#e34a33",
    "moderate": "#fdbb84",
    "low": "#fee8c8",
    "none": "#2c7fb8",
}


def build_exposure_map(gdf: gpd.GeoDataFrame) -> folium.Map:
    if gdf.empty:
        return folium.Map(location=[25.75, -80.15], zoom_start=12)

    centroid = gdf.geometry.union_all().centroid
    fmap = folium.Map(location=[centroid.y, centroid.x], zoom_start=14, tiles="cartodbpositron")

    for _, row in gdf.iterrows():
        color = CATEGORY_COLORS.get(row.get("exposure_category", "none"), "#999999")
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda _f, color=color: {
                "fillColor": color,
                "color": color,
                "weight": 1,
                "fillOpacity": 0.7,
            },
            tooltip=(
                f"exposure: {row.get('exposure_category')} "
                f"({row.get('exposure_score'):.2f}) | "
                f"surge: {row.get('surge_ft', 0):.0f}ft | "
                f"flood_active: {row.get('flood_active', False)}"
            ),
        ).add_to(fmap)

    legend_html = "".join(
        f'<div><span style="background:{c};width:12px;height:12px;'
        f'display:inline-block;margin-right:4px;"></span>{cat}</div>'
        for cat, c in CATEGORY_COLORS.items()
    )
    fmap.get_root().html.add_child(
        folium.Element(
            f'<div style="position:fixed;bottom:20px;left:20px;z-index:1000;'
            f'background:white;padding:8px;border-radius:4px;font-size:12px;'
            f'box-shadow:0 1px 4px rgba(0,0,0,0.3);">{legend_html}</div>'
        )
    )
    return fmap
