# app.py
import streamlit as st
import pandas as pd
import numpy as np
import folium
from folium.plugins import HeatMap
from folium import FeatureGroup
from shapely.geometry import LineString, Point
from streamlit_folium import st_folium
import json
import os
import ast
from typing import List, Tuple, Dict, Optional

# ----------------------------- Utility / Parsing Functions -----------------------------

def find_lat_lon_columns(df: pd.DataFrame) -> Tuple[Optional[str], Optional[str]]:
    """
    Find likely latitude and longitude column names (case/space insensitive).
    Returns original column names (or (None, None) if not found).
    Searches for variations: lat, latitude, long, lon, longitude
    """
    normalized = {col.lower().strip().replace(" ", "").replace("_", ""): col for col in df.columns}
    
    # Search for latitude variations
    lat_patterns = ["latitude", "lat"]
    lat_col = None
    for pattern in lat_patterns:
        lat_col = next((orig for norm, orig in normalized.items() if pattern in norm), None)
        if lat_col:
            break
    
    # Search for longitude variations
    lon_patterns = ["longitude", "long", "lon", "lng"]
    lon_col = None
    for pattern in lon_patterns:
        lon_col = next((orig for norm, orig in normalized.items() if pattern in norm), None)
        if lon_col:
            break
    
    return lat_col, lon_col

def read_geolocations_from_file(file) -> pd.DataFrame:
    """
    Read CSV or Excel file and return dataframe with normalized lat/lon columns named 'lat' and 'lon'.
    Supports both .csv and .xlsx/.xls files.
    Case-insensitive column detection for latitude/longitude variations.
    If missing, raises ValueError.
    """
    # Get file extension
    file_name = file.name if hasattr(file, 'name') else str(file)
    file_ext = file_name.lower().split('.')[-1]
    
    # Read file based on extension
    try:
        if file_ext == 'csv':
            df = pd.read_csv(file)
        elif file_ext in ['xlsx', 'xls']:
            df = pd.read_excel(file)
        else:
            raise ValueError(f"Unsupported file format: .{file_ext}. Please upload CSV or Excel files.")
    except Exception as e:
        raise ValueError(f"Error reading file: {str(e)}")
    
    # Find lat/lon columns
    lat_col, lon_col = find_lat_lon_columns(df)
    
    if not lat_col or not lon_col:
        available_cols = ", ".join(df.columns.tolist())
        raise ValueError(
            f"Could not find latitude and longitude columns in the file.\n"
            f"Available columns: {available_cols}\n"
            f"Please ensure your file has columns like 'Latitude'/'Lat' and 'Longitude'/'Lon'/'Long'."
        )
    
    df2 = df.copy()
    df2 = df2.rename(columns={lat_col: "lat", lon_col: "lon"})
    
    # Convert to numeric, coercing errors
    df2["lat"] = pd.to_numeric(df2["lat"], errors='coerce')
    df2["lon"] = pd.to_numeric(df2["lon"], errors='coerce')
    
    # Drop rows with missing coords
    initial_count = len(df2)
    df2 = df2.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    dropped_count = initial_count - len(df2)
    
    if dropped_count > 0:
        print(f"Note: Dropped {dropped_count} rows with invalid or missing coordinates.")
    
    if len(df2) == 0:
        raise ValueError("No valid coordinate data found in the file after cleaning.")
    
    return df2

def parse_coords_input(coords: str) -> Tuple[Optional[float], Optional[float]]:
    """Parse 'lat, lon' text input into floats. Returns (None, None) on error."""
    try:
        lat, lon = map(float, [c.strip() for c in coords.split(",")])
        return lat, lon
    except Exception:
        return None, None

def parse_radii_input(radii_str: str) -> List[int]:
    """
    Parse comma-separated radii in meters.
    Ignore non-numeric tokens. Return sorted unique integer list.
    """
    try:
        parts = [p.strip() for p in radii_str.split(",")]
        radii = []
        for p in parts:
            if p == "":
                continue
            # allow floats and ints, convert to int meters
            try:
                val = float(p)
                if val >= 0:
                    radii.append(int(round(val)))
            except:
                # ignore invalid token
                continue
        radii = sorted(set(radii))
        if not radii:
            raise ValueError("No valid radii parsed")
        return radii
    except Exception:
        # fallback defaults
        return [10000, 20000, 30000]

# ----------------------------- Fast Distance Computation -----------------------------

def haversine_vectorized(lat1, lon1, lat2_arr, lon2_arr):
    """
    Vectorized haversine distance (in kilometers) between a single point (lat1, lon1)
    and arrays of lat2_arr, lon2_arr. All inputs in degrees.
    Returns numpy array of distances in kilometers.
    """
    # convert to radians
    lat1_r = np.radians(lat1)
    lon1_r = np.radians(lon1)
    lat2_r = np.radians(lat2_arr)
    lon2_r = np.radians(lon2_arr)

    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r

    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * (np.sin(dlon / 2.0) ** 2)
    c = 2 * np.arcsin(np.minimum(1, np.sqrt(a)))
    R = 6371.0088  # Earth's radius in km (mean)
    return R * c  # in km

# ----------------------------- Binning & Color Mapping -----------------------------

def make_bins_from_radii(radii_meters: List[int]) -> List[Tuple[float, float]]:
    """
    Convert radii (meters) to distance bins in kilometers.
    Returns list of (low_km, high_km) for each bucket.
    Example: radii [10000,20000] => [(0,10),(10,20),(20,inf)]
    """
    radii_km = [r/1000.0 for r in sorted(radii_meters)]
    bins = []
    prev = 0.0
    for r in radii_km:
        bins.append((prev, r))
        prev = r
    bins.append((prev, float("inf")))
    return bins

def bucketize_distances(dist_km: np.ndarray, bins: List[Tuple[float,float]]) -> np.ndarray:
    """
    Given distance array (km) and bins list (low,high), return integer bucket index array.
    """
    # vectorized approach: iterate over bins and assign
    bucket_idxs = np.full(dist_km.shape, -1, dtype=int)
    for i, (low, high) in enumerate(bins):
        mask = (dist_km >= low) & (dist_km < high)
        bucket_idxs[mask] = i
    return bucket_idxs

def make_color_palette(n: int) -> List[str]:
    """
    Return n distinct colors. Uses a simple palette cycle; extend as needed.
    Prioritize speed: no external libs.
    """
    base = [
        "#1a9850",  # green
        "#fee08b",  # yellow-ish
        "#fdae61",  # orange
        "#f46d43",  # deep orange
        "#d73027",  # red
        "#542788",  # purple
        "#4575b4",  # blue
        "#000000",  # black
        "#2b8cbe",  # teal
        "#66c2a5",  # light green
    ]
    if n <= len(base):
        return base[:n]
    # expand by cycling if more buckets than base
    colors = [base[i % len(base)] for i in range(n)]
    return colors

def bucket_labels_from_bins(bins: List[Tuple[float,float]]) -> List[str]:
    """Human readable labels for bins, in km with 1 decimal if needed."""
    labels = []
    for low, high in bins:
        if high == float("inf"):
            labels.append(f">{low:.2f} km")
        else:
            labels.append(f"{low:.2f}–{high:.2f} km")
    return labels

# ----------------------------- Metro / Hyderabad Parsing (kept modular) -----------------------------

def read_metro_data_from_geojson(file):
    data = json.load(file)
    metro_lines = []
    all_stations = []

    for feature in data["features"]:
        geometry_type = feature["geometry"]["type"]
        coordinates = feature["geometry"]["coordinates"]
        props = feature.get("properties", {})
        color = props.get("description", "blue")
        name = props.get("name") or props.get("Name")

        if geometry_type == "LineString":
            # GeoJSON: coordinates are [lon, lat, ...]
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
        layer = FeatureGroup(name=group["name"], show=True)

        # Add metro line
        folium.PolyLine(
            group["line"],
            color=group["color"],
            weight=4,
            opacity=1.0
        ).add_to(layer)

        # Add stations
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


def add_hyderabad_metro(map_obj, lines_file, stations_file):
    df_lines = pd.read_csv(lines_file)
    df_stations = pd.read_csv(stations_file)

    lines_group = FeatureGroup(name='Hyderabad Metro Lines')
    for _, row in df_lines.iterrows():
        coords = row['coords']
        if isinstance(coords, str):
            coords = ast.literal_eval(coords)
        coords = [[lat, lon] for lat, lon in coords]
        folium.PolyLine(coords, color=row.get('Color', 'blue'), weight=5, opacity=0.7).add_to(lines_group)
    lines_group.add_to(map_obj)

    stations_group = FeatureGroup(name='Hyderabad Metro Stations')
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

# ----------------------------- Map Drawing Helpers -----------------------------

def add_concentric_circles(map_obj, lat, lon, radii_meters=[10000, 20000, 30000], label="Office", layer_name="Office Range", color="#3186cc"):
    """
    Add marker + concentric circle outlines to map_obj. color parameter for circle lines.
    """
    layer = FeatureGroup(name=layer_name, show=True)
    folium.Marker(
        location=[lat, lon],
        popup=f"🏢 {label}",
        icon=folium.Icon(color="darkred", icon="building", prefix="fa")
    ).add_to(layer)

    for r in radii_meters:
        folium.Circle(
            location=[lat, lon],
            radius=int(r),
            color=color,
            fill=False,
            weight=2,
            opacity=0.6,
            dash_array="8,6"
        ).add_to(layer)

    layer.add_to(map_obj)

def add_colored_points_layer(map_obj, df: pd.DataFrame, lat_col: str, lon_col: str,
                             fill_colors: List[str], bucket_idxs: np.ndarray,
                             bucket_labels: List[str], layer_name="Points by Distance"):
    """
    Add circle markers to map, colored by bucket index. Assumes bucket_idxs length matches df.
    Returns a dictionary with bucket counts for display.
    """
    layer = FeatureGroup(name=layer_name, show=True)

    # Iterate row-wise here: unavoidable for folium markers; keep it as light as possible.
    for i, row in df.iterrows():
        bidx = int(bucket_idxs[i]) if i < len(bucket_idxs) else -1
        # fallback color:
        fill_color = fill_colors[bidx] if (0 <= bidx < len(fill_colors)) else "#3186cc"
        popup_html = (
            f"<b>Record:</b><br>"
            f"{row.to_dict()}<br>"
            f"<b>Distance (km):</b> {row.get('distance_km', np.nan):.3f}<br>"
            f"<b>Range:</b> {bucket_labels[bidx] if (0 <= bidx < len(bucket_labels)) else 'N/A'}"
        )
        folium.CircleMarker(
            location=(row[lat_col], row[lon_col]),
            radius=5,
            color="black",
            weight=1,
            fill=True,
            fill_color=fill_color,
            fill_opacity=0.9,
            popup=popup_html
        ).add_to(layer)

    layer.add_to(map_obj)
    
    # Calculate bucket counts
    bucket_counts = {}
    for i in range(len(bucket_labels)):
        count = np.sum(bucket_idxs == i)
        bucket_counts[i] = count
    
    return bucket_counts

def add_simple_points_layer(map_obj, geolocations: List[Tuple[float,float]], color="red", layer_name="Pickup Points"):
    layer = FeatureGroup(name=layer_name, show=True)
    for lat, lon in geolocations:
        folium.CircleMarker(
            location=(lat, lon),
            radius=4,
            color="black",
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=0.8
        ).add_to(layer)
    layer.add_to(map_obj)

# ----------------------------- Flexible Map Function (modular + fast) -----------------------------

def create_flexible_map(
    geolocations_df: Optional[pd.DataFrame] = None,
    metro_groups=None,
    zoom_start=12,
    heat_radius=15,
    heat_blur=20,
    heat_max_intensity=100,
    office_marker=None,
    hyd_files=None,
    map_type="heatmap",
    max_points_for_heatmap=800  # threshold: if many points, prefer heatmap
):
    """
    Build folium map with options. geolocations_df expected to have 'lat' and 'lon'.
    If office_marker is provided AND map_type == 'points', points will be colored by distance buckets.
    Returns tuple: (map_object, bucket_stats_dict or None)
    """
    bucket_stats = None
    
    # Determine start location
    if geolocations_df is not None and not geolocations_df.empty:
        start_location = (float(geolocations_df.iloc[0]["lat"]), float(geolocations_df.iloc[0]["lon"]))
    elif office_marker:
        start_location = (office_marker["lat"], office_marker["lon"])
    elif metro_groups:
        start_location = metro_groups[0]["line"][0]
    else:
        start_location = (0.0, 0.0)

    m = folium.Map(location=start_location, zoom_start=zoom_start, tiles="CartoDB positron", control_scale=True)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)

    # ------------- Geolocation visualization -------------
    if geolocations_df is not None and not geolocations_df.empty:
        n_points = len(geolocations_df)
        # Heatmap branch
        if map_type.lower() == "heatmap" or n_points > max_points_for_heatmap:
            layer = FeatureGroup(name="Pickup Heatmap", show=True)
            coords = geolocations_df[["lat", "lon"]].values.tolist()
            HeatMap(coords, radius=heat_radius, blur=heat_blur, max_intensity=heat_max_intensity).add_to(layer)
            layer.add_to(m)
            
            # Add heatmap legend
            heatmap_legend_html = build_heatmap_legend_html()
            m.get_root().html.add_child(folium.Element(heatmap_legend_html))
            
            # Add office marker and concentric circles if office is selected
            if office_marker:
                office_lat = office_marker["lat"]
                office_lon = office_marker["lon"]
                radii_m = office_marker.get("radii", [10000, 20000, 30000])
                add_concentric_circles(m, office_lat, office_lon, radii_meters=radii_m, 
                                     label=office_marker.get("label","Office"),
                                     layer_name=office_marker.get("layer_name", "Office Range"))
        else:
            # Points branch
            # If office provided, color points by distance buckets; otherwise simple points
            if office_marker:
                office_lat = office_marker["lat"]
                office_lon = office_marker["lon"]
                radii_m = office_marker.get("radii", [10000, 20000, 30000])
                # compute distances vectorized (in km)
                lat_arr = geolocations_df["lat"].to_numpy(dtype=float)
                lon_arr = geolocations_df["lon"].to_numpy(dtype=float)
                dist_km = haversine_vectorized(office_lat, office_lon, lat_arr, lon_arr)
                geolocations_df = geolocations_df.copy()
                geolocations_df["distance_km"] = dist_km

                # compute bins & bucketize
                bins = make_bins_from_radii(radii_m)
                bucket_idxs = bucketize_distances(dist_km, bins)  # numpy array of ints

                # make labels and colors
                bucket_labels = bucket_labels_from_bins(bins)
                colors = make_color_palette(len(bins))

                # add concentric circles around office
                add_concentric_circles(m, office_lat, office_lon, radii_meters=radii_m, label=office_marker.get("label","Office"))

                # add points colored by bucket
                bucket_counts = add_colored_points_layer(m, geolocations_df, "lat", "lon", colors, bucket_idxs, bucket_labels,
                                         layer_name="Pickup Points (by distance bucket)")
                
                # Store bucket statistics for return
                bucket_stats = {
                    "labels": bucket_labels,
                    "colors": colors,
                    "counts": bucket_counts
                }

                # also add a small legend (simple html)
                legend_html = build_legend_html(bucket_labels, colors, title="Distance buckets")
                m.get_root().html.add_child(folium.Element(legend_html))

            else:
                # no office: simple colored points (all same color)
                add_simple_points_layer(m, geolocations_df[["lat", "lon"]].values.tolist(), color="red", layer_name="Pickup Points")

    # --- Metro Layers ---
    if metro_groups:
        add_metro_layers(m, metro_groups)

    # --- Hyderabad Metro ---
    if hyd_files:
        lines_file, stations_file = hyd_files
        add_hyderabad_metro(m, lines_file, stations_file)

    # --- Office Marker (if not already added above) ---
    if office_marker and (geolocations_df is None or geolocations_df.empty):
        add_concentric_circles(
            m,
            office_marker["lat"],
            office_marker["lon"],
            label=office_marker.get("label", "Office"),
            radii_meters=office_marker.get("radii", [10000, 20000, 30000]),
            layer_name=office_marker.get("layer_name", "Office Range")
        )

    folium.LayerControl(collapsed=True).add_to(m)
    return m, bucket_stats

def build_legend_html(labels: List[str], colors: List[str], title="Legend"):
    """
    Build a small HTML legend. Limited styling but useful.
    """
    items = ""
    for lbl, col in zip(labels, colors):
        items += f"""
        <div style="display:flex; align-items:center; margin-bottom:4px;">
            <div style="width:18px;height:12px;background:{col};border:1px solid #000;margin-right:6px;"></div>
            <div style="font-size:12px;">{lbl}</div>
        </div>
        """
    html = f"""
    <div style="
        position: fixed;
        bottom: 50px;
        left: 10px;
        z-index: 9999;
        background:white;
        padding:8px 10px;
        border-radius:4px;
        box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
        font-family: Arial, sans-serif;
    ">
        <strong style="display:block; margin-bottom:6px;">{title}</strong>
        {items}
    </div>
    """
    return html

def build_heatmap_legend_html(title="Heatmap Intensity"):
    """
    Build a gradient legend for heatmap showing intensity scale.
    """
    html = f"""
    <div style="
        position: fixed;
        bottom: 50px;
        left: 10px;
        z-index: 9999;
        background:white;
        padding:10px 12px;
        border-radius:4px;
        box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
        font-family: Arial, sans-serif;
    ">
        <strong style="display:block; margin-bottom:8px; font-size:13px;">{title}</strong>
        <div style="display:flex; align-items:center; margin-bottom:4px;">
            <div style="font-size:11px; width:40px;">Low</div>
            <div style="width:100px; height:15px; background: linear-gradient(to right, 
                rgba(0,0,255,0.8), rgba(0,255,255,0.8), rgba(0,255,0,0.8), 
                rgba(255,255,0,0.8), rgba(255,0,0,0.8)); 
                border:1px solid #000;"></div>
            <div style="font-size:11px; width:40px; text-align:right;">High</div>
        </div>
        <div style="font-size:10px; color:#666; margin-top:6px;">
            Darker/Redder = More points
        </div>
    </div>
    """
    return html

# ----------------------------- Streamlit UI (uses modular functions above) -----------------------------

def main():
    st.set_page_config(page_title="Metro Heatmap Viewer", layout="wide")
    st.title("📍 Metro Station & Pickup Visualizer")

    # -- File upload --
    uploaded_file = st.file_uploader(
        "📄 Upload File (CSV or Excel with latitude & longitude columns)", 
        type=["csv", "xlsx", "xls"],
        help="Supports CSV, Excel (.xlsx, .xls) with columns like: Latitude/Lat, Longitude/Lon/Long"
    )

    map_type = st.radio("Select Map Type", ["Heatmap", "Points"], horizontal=True)

    # Only show heatmap configuration when heatmap is selected
    if map_type == "Heatmap":
        col1, col2, col3 = st.columns(3)
        with col1:
            heat_radius = st.slider("Heatmap Radius", 1, 50, 20)
        with col2:
            heat_blur = st.slider("Heatmap Blur", 1, 50, 17)
        with col3:
            heat_max_intensity = st.slider("Max Heat Intensity", 10, 500, 100)
    else:
        # Default values when not in heatmap mode
        heat_radius = 20
        heat_blur = 17
        heat_max_intensity = 100
    
    # Default zoom level
    zoom = 12

    # Metro options
    st.markdown("### 🚇 Optional: Add Metro Lines")
    with st.expander("Add Metro Markers"):
        show_Bangalore_metro = st.checkbox("Show Bangalore Metro Lines", value=False)
        show_Hyderbad_metro = st.checkbox("Show Hyderabad Metro", value=False)

    # Office Marker
    st.markdown("### 🏢 Optional: Add Office Marker with Distance Rings")
    with st.expander("Add Office Marker"):
        coords = st.text_input("Latitude, Longitude", value="0.0, 0.0", help="Enter as: lat, lon")
        office_lat, office_lon = parse_coords_input(coords)
        if office_lat is None:
            st.error("Please enter coordinates in the format: latitude, longitude")

        ring_input = st.text_input("Enter radii in meters (comma-separated)", value="10000,20000,30000",
                                   help="Example: 10000,20000,30000")
        user_radii = parse_radii_input(ring_input)

    show_office = st.checkbox("Show Office Marker & Distance Rings", value=False)

    # Data loading
    geolocations_df = None
    if uploaded_file:
        try:
            df_read = read_geolocations_from_file(uploaded_file)
            geolocations_df = df_read
            st.success(f"✅ Loaded {len(geolocations_df)} records from {uploaded_file.name}")
            
            # Show a preview of detected columns
            with st.expander("📋 Preview Data"):
                st.write(f"**Detected Columns:** Latitude & Longitude")
                st.dataframe(geolocations_df.head(10), use_container_width=True)
                
        except ValueError as e:
            st.error(f"❌ {str(e)}")
            geolocations_df = None
        except Exception as e:
            st.error(f"❌ Unexpected error: {str(e)}")
            geolocations_df = None

    # Metro groups
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
    if show_office and office_lat is not None and office_lon is not None and not (office_lat == 0.0 and office_lon == 0.0):
        office_marker = {
            "lat": float(office_lat),
            "lon": float(office_lon),
            "label": "Office",
            "radii": user_radii,
            "layer_name": "Office Range"
        }
        st.write(f"Using radii (meters): {user_radii}")

    # Render map
    if (geolocations_df is not None and not geolocations_df.empty) or metro_groups or office_marker or hyd_files:
        result_map, bucket_stats = create_flexible_map(
            geolocations_df=geolocations_df,
            metro_groups=metro_groups,
            zoom_start=zoom,
            heat_radius=heat_radius,
            heat_blur=heat_blur,
            heat_max_intensity=heat_max_intensity,
            office_marker=office_marker,
            hyd_files=hyd_files,
            map_type=map_type.lower()
        )
        
        # Display statistics table if we have bucket data
        if bucket_stats is not None:
            st.markdown("### 📊 Distance Distribution Summary")
            
            # Create dataframe for display
            stats_data = []
            total_points = 0
            for i, label in enumerate(bucket_stats["labels"]):
                count = bucket_stats["counts"].get(i, 0)
                total_points += count
                stats_data.append({
                    "Distance Range": label,
                    "Color": bucket_stats["colors"][i],
                    "Count": count
                })
            
            stats_df = pd.DataFrame(stats_data)
            
            # Add percentage column
            if total_points > 0:
                stats_df["Percentage"] = (stats_df["Count"] / total_points * 100).round(2).astype(str) + "%"
            else:
                stats_df["Percentage"] = "0.00%"
            
            # Display with color indicators
            st.dataframe(
                stats_df.style.apply(
                    lambda row: [f'background-color: {row["Color"]}; color: white' if idx == 1 else '' 
                                for idx in range(len(row))], 
                    axis=1
                ),
                use_container_width=True,
                hide_index=True
            )
            
            st.metric("Total Points", total_points)
        
        if result_map:
            st_folium(result_map, width=1200, height=900)
    else:
        st.info("📂 Please upload data or enable metro/office markers to view the map.")

if __name__ == "__main__":
    main()



