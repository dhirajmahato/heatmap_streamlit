import streamlit as st
import leafmap.foliumap as leafmap
import pandas as pd

st.set_page_config(layout="wide")
st.title("📍 Interactive Heatmap in Streamlit")

# Upload an Excel file
uploaded_file = st.file_uploader("Upload an Excel file", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)

    # Check if required columns exist
    if "latitude" in df.columns and "longitude" in df.columns:
        st.success("✅ File uploaded successfully!")

        # Clean coordinates
        df = df.dropna(subset=["latitude", "longitude"])
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
        df = df.dropna(subset=["latitude", "longitude"])

        # Sidebar controls
        st.sidebar.header("🔧 Heatmap Settings")
        show_heatmap = st.sidebar.checkbox("Show Heatmap", value=True)
        radius = st.sidebar.slider("Heatmap Radius", 5, 50, 20)
        opacity = st.sidebar.slider("Heatmap Opacity", 0.1, 1.0, 0.6, step=0.1)
        blur = st.sidebar.slider("Heatmap Blur", 1, 30, 15)

        # Handle intensity
        if "intensity" in df.columns:
            df["intensity"] = pd.to_numeric(df["intensity"], errors="coerce").fillna(1)
            intensity_column = "intensity"
        else:
            st.warning("⚠️ No intensity column found. Using default intensity.")
            df["intensity"] = 1
            intensity_column = "intensity"

        # Base map selection
        basemap = st.sidebar.selectbox("Choose a Base Map", ["OpenStreetMap", "Satellite", "Terrain", "Dark Mode"])

        # Initialize clean map (no draw/measure/fullscreen/etc.)
        m = leafmap.Map(
            center=[df["latitude"].mean(), df["longitude"].mean()],
            zoom=10,
            draw_control=False,
            measure_control=False,
            fullscreen_control=False,
            attribution_control=False,
            locate_control=False,
            layers_control=False,
        )

        # Set base map
        if basemap == "Satellite":
            m.add_basemap("SATELLITE")
        elif basemap == "Terrain":
            m.add_basemap("TERRAIN")
        elif basemap == "Dark Mode":
            m.add_basemap("CartoDB.DarkMatter")
        else:
            m.add_basemap("OpenStreetMap")

        # Preview data
        st.write("🔎 **Data Preview**:", df.head())

        # Add heatmap
        if show_heatmap:
            try:
                m.add_heatmap(
                    data=df,
                    latitude="latitude",
                    longitude="longitude",
                    value=intensity_column,
                    name="Heat Map",
                    radius=radius,
                    blur=blur,
                    opacity=opacity,
                )
            except Exception as e:
                st.error(f"🔥 Heatmap Error: {e}")

        # Render map
        m.to_streamlit(height=600)

    else:
        st.error("⚠️ The Excel file must contain 'latitude' and 'longitude' columns.")

else:
    st.info("📤 Please upload an Excel file with 'latitude' and 'longitude' columns.")
