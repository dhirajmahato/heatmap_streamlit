import streamlit as st
import pandas as pd
import folium
import json
from folium.plugins import HeatMap
from shapely.geometry import LineString, Point
from streamlit_folium import st_folium
import os
import ast

# -------------------- Data Processing Functions --------------------

def read_geolocations_from_excel(file):
    df = pd.read_excel(file)
    normalized_columns = {col.lower().strip().replace(" ", ""): col for col in df.columns}

    lat_col = next((original for norm, original in normalized_columns.items() if "lat" in norm), None)
    lon_col = next((original for norm, original in normalized_columns.items() if "lon" in norm), None)

    if lat_col and lon_col:
        return list(df[[lat_col, lon_col]].itertuples(index=False, name=None))
    else:
        st.error("❌ The Excel file must contain latitude and longitude columns (e.g., 'Latitude', 'Longitude').")
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
        station_point = Point(station["location"][1], station["location"][0])

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

        layer.add_to(m)


def add_hyderabad_metro(map_obj, lines_file, stations_file):
    df_lines = pd.read_csv(lines_file)
    df_stations = pd.read_csv(stations_file)

    lines_group = folium.FeatureGroup(name='Hyderabad Metro Lines')
    for _, row in df_lines.iterrows():
        coords = row['coords']
        if isinstance(coords, str):
            coords = ast.literal_eval(coords)
        coords = [[lat, lon] for lat, lon in coords]
        folium.PolyLine(
            coords, color=row.get('Color', 'blue'), weight=5, opacity=0.7
        ).add_to(lines_group)
    lines_group.add_to(map_obj)

    stations_group = folium.FeatureGroup(name='Hyderabad Metro Stations')
    for _, row in df_stations.iterrows():
        coords = row['coords']
        if isinstance(coords, str):
            coords = ast.literal_eval(coords)
        coords = [coords[0], coords[1]]
        folium.CircleMarker(
            location=coords,
            radius=5,
            color='black',
            fill=True,
            fill_color=row.get('color', 'blue'),
            fill_opacity=0.7,
            popup=row.get('Station', 'Unknown Station')
        ).add_to(stations_group)
    stations_group.add_to(map_obj)


def add_concentric_circles(map_obj, lat, lon, radii_meters=[10000, 20000, 30000], label="Office", layer_name="Office Range"):
    layer = folium.FeatureGroup(name=layer_name, show=True)

    folium.Marker(
        location=[lat, lon],
        popup="🏢 Office Location",
        icon=folium.Icon(color="darkred", icon="building", prefix="fa")
    ).add_to(layer)

    for r in radii_meters:
        folium.Circle(
            location=[lat, lon],
            radius=r,
            color='blue',
            fill=False,
            weight=2,
            opacity=0.5,
            dash_array="10,10"
        ).add_to(layer)

    layer.add_to(map_obj)


# -------------------- Flexible Map Function --------------------

def create_flexible_map(
    geolocations=None,
    metro_groups=None,
    zoom_start=12,
    radius=15,
    blur=20,
    max_intensity=100,
    office_marker=None,
    hyd_files=None,
    map_type="heatmap"
):
    if not geolocations and not metro_groups and not office_marker and not hyd_files:
        return None

    start_location = (
        geolocations[0] if geolocations else
        (office_marker["lat"], office_marker["lon"]) if office_marker else
        metro_groups[0]["line"][0]
    )

    m = folium.Map(location=start_location, zoom_start=zoom_start, tiles="CartoDB positron", control_scale=True)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)

    # ------------------------------------------------------------------------- Choose Heatmap or Points ------------------------------------------------------------------
    if geolocations:
        if map_type.lower() == "heatmap":
            layer = folium.FeatureGroup(name="Pickup Heatmap", show=True)
            HeatMap(
                geolocations,
                radius=radius,
                blur=blur,
                max_intensity=max_intensity
            ).add_to(layer)
            layer.add_to(m)
        elif map_type.lower() == "points":
            layer = folium.FeatureGroup(name="Pickup Points", show=True)
            for lat, lon in geolocations:
                folium.CircleMarker(
                    location=(lat, lon),
                    radius=5,
                    color="black",
                    weight=1.5,
                    fill=True,
                    fill_color="red",
                    fill_opacity=0.8
                ).add_to(layer)
            layer.add_to(m)

    # --- Metro Layers ---
    if metro_groups:
        add_metro_layers(m, metro_groups)

    # --- Hyderabad Metro ---
    if hyd_files:
        lines_file, stations_file = hyd_files
        add_hyderabad_metro(m, lines_file, stations_file)

    # --- Office Marker ---
    if office_marker:
        add_concentric_circles(
            m,
            office_marker["lat"],
            office_marker["lon"],
            label=office_marker.get("label", "Office"),
            radii_meters=office_marker.get("radii", [10000, 20000, 30000]),
            layer_name=office_marker.get("layer_name", "Office Range")
        )

    folium.LayerControl(collapsed=True).add_to(m)
    return m


# ----------------------------------------------------------------------------------------------- Streamlit UI ------------------------------------------------------------------------

st.set_page_config(page_title="Metro Heatmap Viewer", layout="wide")
st.title("📍 Metro Station & Pickup Visualizer")

excel_file = st.file_uploader("📄 Upload Excel File (with 'latitude' and 'longitude' columns)", type=["xlsx"])

col1, col2, col3 = st.columns(3)
with col1:
    zoom = st.slider("Zoom Level", 5, 20, 12)
with col2:
    radius = st.slider("Heatmap Radius", 1, 50, 20)
with col3:
    blur = st.slider("Heatmap Blur", 1, 50, 17)

max_intensity = st.slider("Max Heat Intensity", 10, 500, 100)

# 🔘 Choose Map Type
map_type = st.radio("Select Map Type", ["Heatmap", "Points"], horizontal=True)

# Metro options
st.markdown("### 🚇 Optional: Add Metro Lines")
with st.expander("Add Metro Markers"):
    show_Bangalore_metro = st.checkbox("Show Bangalore Metro Lines", value=False)
    show_Hyderbad_metro = st.checkbox("Show Hyderabad Metro", value=False)

# Office Marker
st.markdown("### 🏢 Optional: Add Office Marker with Distance Rings")
with st.expander("Add Office Marker"):
    
    coords = st.text_input("Latitude, Longitude", value="0.0, 0.0")
    # Parse values safely
    try:
        office_lat, office_lon = map(float, coords.split(","))
    except ValueError:
        st.error("Please enter coordinates in the format: latitude, longitude")
        office_lat, office_lon = None, None

    ring_input = st.text_input("Enter radii in meters (comma-separated)", value="10000,20000,30000")
    try:
        user_radii = [int(x.strip()) for x in ring_input.split(",") if x.strip().isdigit()]
    except:
        user_radii = [10000, 20000, 30000]
    
show_office = st.checkbox("Show Office Marker & Distance Rings", value=False)

# ------------------------------------------------------------------------------------------------------------ Data loading -------------------------------------------------------------------
geolocations = read_geolocations_from_excel(excel_file) if excel_file else []

metro_groups = []
if show_Bangalore_metro:
    try:
        with open("metro-lines-stations.geojson", "r") as f:
            metro_lines, all_stations = read_metro_data_from_geojson(f)
            metro_groups = assign_stations_to_closest_line(metro_lines, all_stations)
    except FileNotFoundError:
        st.error("⚠️ 'metro-lines-stations.geojson' file not found.")

hyd_files = None
if show_Hyderbad_metro:
    parent_dir = os.getcwd()
    lines_file = os.path.join(parent_dir, "Hyd_metro_polyline.csv")
    stations_file = os.path.join(parent_dir, "Hyd_metro_stations.csv")
    if os.path.exists(lines_file) and os.path.exists(stations_file):
        hyd_files = (lines_file, stations_file)
    else:
        st.error("⚠️ Hyderabad Metro CSV files not found.")

office_marker = None
if show_office and office_lat != 0.0 and office_lon != 0.0:
    office_marker = {
        "lat": office_lat,
        "lon": office_lon,
        "label": "Office",
        "radii": user_radii,
        "layer_name": "Office Range"
    }

# -------------------------------------------------------------------------------- Map rendering ---------------------------------------------------------------------------------
if geolocations or metro_groups or office_marker or hyd_files:
    result_map = create_flexible_map(
        geolocations=geolocations,
        metro_groups=metro_groups,
        zoom_start=zoom,
        radius=radius,
        blur=blur,
        max_intensity=max_intensity,
        office_marker=office_marker,
        hyd_files=hyd_files,
        map_type=map_type.lower()
    )
    if result_map:
        st_folium(result_map, width="100%", height=1000)
else:
    st.info("📂 Please upload data or enable metro/office markers to view the map.")


