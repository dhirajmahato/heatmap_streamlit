import streamlit as st
import pandas as pd
import folium
import json
from folium.plugins import HeatMap
from shapely.geometry import LineString, Point
from streamlit_folium import st_folium

# -------------------- Data Processing Functions --------------------

def read_geolocations_from_excel(file):
    df = pd.read_excel(file)
    if "latitude" in df.columns and "longitude" in df.columns:
        return list(df[["latitude", "longitude"]].itertuples(index=False, name=None))
    else:
        st.error("The Excel file must contain 'latitude' and 'longitude' columns.")
        return []

def read_metro_data_from_geojson(file):
    data = json.load(file)
    metro_lines = []
    all_stations = []

    for feature in data["features"]:
        geometry_type = feature["geometry"]["type"]
        coordinates = feature["geometry"]["coordinates"]
        props = feature["properties"]
        color = props.get("description", "blue")
        name = props.get("name") or props.get("Name")

        if geometry_type == "LineString":
            line_coords = [(lat, lon) for lon, lat, *_ in coordinates]
            metro_lines.append({
                "name": name or f"Metro Line {len(metro_lines) + 1}",
                "color": color,
                "line": line_coords,
                "stations": []
            })

        elif geometry_type == "Point":
            all_stations.append({
                "location": (coordinates[1], coordinates[0]),
                "name": name or "Unknown Station"
            })

    return metro_lines, all_stations

def assign_stations_to_closest_line(metro_lines, stations):
    for station in stations:
        min_distance = float("inf")
        closest_line = None
        station_point = Point(station["location"][1], station["location"][0])  # (lon, lat)

        for line in metro_lines:
            line_geom = LineString([(lon, lat) for lat, lon in line["line"]])
            distance = station_point.distance(line_geom)
            if distance < min_distance:
                min_distance = distance
                closest_line = line

        if closest_line:
            closest_line["stations"].append(station)

    return metro_lines

def add_metro_layers(m, metro_groups):
    for group in metro_groups:
        layer = folium.FeatureGroup(name=group["name"], show=True)

        folium.PolyLine(
            group["line"], color=group["color"], weight=4, opacity=1.0
        ).add_to(layer)

        for station in group["stations"]:
            folium.CircleMarker(
                location=station["location"],
                radius=5,
                color="black",
                fill=True,
                fill_color=group["color"],
                fill_opacity=0.8
            ).add_to(layer)

        layer.add_to(m)

def create_flexible_map(geolocations=None, metro_groups=None, zoom_start=12, radius=15, blur=20, max_intensity=100):
    if not geolocations and not metro_groups:
        return None

    start_location = (geolocations[0] if geolocations else metro_groups[0]["line"][0])
    m = folium.Map(location=start_location, zoom_start=zoom_start, tiles="CartoDB positron", control_scale=True)

    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)

    if geolocations:
        heatmap_layer = folium.FeatureGroup(name="Pickup Heatmap", show=True)
        HeatMap(
            geolocations,
            radius=radius,
            blur=blur,
            max_intensity=max_intensity
        ).add_to(heatmap_layer)
        heatmap_layer.add_to(m)

    if metro_groups:
        add_metro_layers(m, metro_groups)

    folium.LayerControl(collapsed=True).add_to(m)
    return m

# -------------------- Streamlit UI --------------------

st.set_page_config(page_title="Metro Heatmap Viewer", layout="wide")
st.title("📍 Metro Station & Pickup Heatmap Visualizer")

excel_file = st.file_uploader("📄 Upload Excel File (with 'latitude' and 'longitude' columns)", type=["xlsx"])
geojson_file = st.file_uploader("🗺️ Upload Metro GeoJSON File", type=["geojson", "json"])

col1, col2, col3 = st.columns(3)
with col1:
    zoom = st.slider("Zoom Level", 5, 20, 12)
with col2:
    radius = st.slider("Heatmap Radius", 1, 50, 20)
with col3:
    blur = st.slider("Heatmap Blur", 1, 50, 17)

max_intensity = st.slider("Max Heat Intensity", 10, 500, 100)

geolocations = []
metro_groups = []

if excel_file:
    geolocations = read_geolocations_from_excel(excel_file)

if geojson_file:
    metro_lines, all_stations = read_metro_data_from_geojson(geojson_file)
    metro_groups = assign_stations_to_closest_line(metro_lines, all_stations)

if geolocations or metro_groups:
    result_map = create_flexible_map(
        geolocations,
        metro_groups,
        zoom_start=zoom,
        radius=radius,
        blur=blur,
        max_intensity=max_intensity
    )
    if result_map:
        st_folium(result_map, width=1000, height=700)
else:
    st.info("Please upload at least one file to see the map.")
