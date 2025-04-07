import streamlit as st
import leafmap.foliumap as leafmap
import pandas as pd
from streamlit_folium import st_folium

st.set_page_config(layout="wide")
st.title("📍 Interactive Heatmap with Clickable Markers")

# Upload an Excel file
uploaded_file = st.file_uploader("Upload an Excel file", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)

    if "latitude" in df.columns and "longitude" in df.columns:
        st.success("✅ File uploaded successfully!")

        df = df.dropna(subset=["latitude", "longitude"])
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
        df = df.dropna(subset=["latitude", "longitude"])

        st.sidebar.header("🔧 Heatmap Settings")
        show_heatmap = st.sidebar.checkbox("Show Heatmap", value=True)
        radius = st.sidebar.slider("Heatmap Radius", 5, 50, 20)
        opacity = st.sidebar.slider("Heatmap Opacity", 0.1, 1.0, 0.6, step=0.1)
        blur = st.sidebar.slider("Heatmap Blur", 1, 30, 15)

        if "intensity" in df.columns:
            df["intensity"] = pd.to_numeric(df["intensity"], errors="coerce").fillna(1)
            intensity_column = "intensity"
        else:
            st.warning("⚠️ No intensity column found! Using default intensity.")
            df["intensity"] = 1
            intensity_column = "intensity"

        basemap = st.sidebar.selectbox("Choose a Base Map", ["OpenStreetMap", "Satellite", "Terrain", "Dark Mode"])

        # Create folium map instead of leafmap.Map for full control
        import folium
        m = folium.Map(
            location=[df["latitude"].mean(), df["longitude"].mean()],
            zoom_start=10,
            control_scale=True,
            zoom_control=True,
        )

        # Add heatmap
        if show_heatmap:
            from folium.plugins import HeatMap
            heat_data = [[row["latitude"], row["longitude"], row[intensity_column]] for idx, row in df.iterrows()]
            HeatMap(heat_data, radius=radius, blur=blur, opacity=opacity).add_to(m)

        # Show base map layer (optional customization)
        if basemap == "Satellite":
            folium.TileLayer("Esri.WorldImagery").add_to(m)
        elif basemap == "Terrain":
            folium.TileLayer("Stamen Terrain").add_to(m)
        elif basemap == "Dark Mode":
            folium.TileLayer("CartoDB dark_matter").add_to(m)
        else:
            folium.TileLayer("OpenStreetMap").add_to(m)

        # Render map and capture clicks
        st.subheader("🖱️ Click on map to drop a marker")
        map_data = st_folium(m, height=600, returned_objects=["last_clicked"])

        if map_data and map_data["last_clicked"]:
            clicked = map_data["last_clicked"]
            st.success(f"📌 Marker dropped at: **({clicked['lat']:.5f}, {clicked['lng']:.5f})**")

    else:
        st.error("⚠️ Excel must contain 'latitude' and 'longitude' columns.")

else:
    st.info("📤 Please upload an Excel file with 'latitude' and 'longitude' columns.")
