import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium

st.set_page_config(layout="wide")
st.title("📍 Multiple Draggable Markers Map")

# Upload Excel file
uploaded_file = st.file_uploader("Upload an Excel file", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)

    if "latitude" in df.columns and "longitude" in df.columns:
        df = df.dropna(subset=["latitude", "longitude"])
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
        df = df.dropna(subset=["latitude", "longitude"])

        st.success("✅ File uploaded successfully!")
        st.write("📄 **Data Preview:**", df.head())

        # Set map center
        map_center = [df["latitude"].mean(), df["longitude"].mean()]
        fmap = folium.Map(location=map_center, zoom_start=12)

        # Optional: Column for marker label
        label_column = "marker_label" if "marker_label" in df.columns else None

        # Add draggable markers
        for _, row in df.iterrows():
            label = str(row[label_column]) if label_column else "Drag me!"
            folium.Marker(
                location=[row["latitude"], row["longitude"]],
                popup=label,
                draggable=True,
                icon=folium.Icon(color="red", icon="info-sign")
            ).add_to(fmap)

        # Show map and interactions
        map_data = st_folium(fmap, height=600, width=1000)

        # Optional debug
        st.write("🧭 Map Interaction Output:", map_data)

    else:
        st.error("❌ Excel must contain 'latitude' and 'longitude' columns.")
else:
    st.info("📤 Please upload an Excel file with coordinates.")
