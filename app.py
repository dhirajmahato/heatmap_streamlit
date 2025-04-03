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

        # Sidebar controls for interactivity
        st.sidebar.header("🔧 Heatmap Settings")

        show_heatmap = st.sidebar.checkbox("Show Heatmap", value=True)
        radius = st.sidebar.slider("Heatmap Radius", min_value=5, max_value=50, value=20)
        opacity = st.sidebar.slider("Heatmap Opacity", min_value=0.1, max_value=1.0, value=0.6, step=0.1)
        blur = st.sidebar.slider("Heatmap Blur", min_value=1, max_value=30, value=15)

        # Optional: Select intensity column if available
        intensity_column = None
        if "intensity" in df.columns:
            intensity_column = "intensity"
        else:
            st.warning("⚠️ No intensity column found! Using uniform intensity for all points.")
            df["intensity"] = 1  # Assign default intensity

        # Choose a base map layer
        basemap = st.sidebar.selectbox(
            "Choose a Base Map",
            ["OpenStreetMap", "Satellite", "Terrain", "Dark Mode"],
        )

        # Initialize the map centered at the mean of uploaded coordinates
        m = leafmap
