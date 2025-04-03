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

        # Convert to numeric and drop NaN rows
        df = df.dropna(subset=["latitude", "longitude"])
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
        df = df.dropna(subset=["latitude", "longitude"])  # Drop rows with NaNs

        # Sidebar controls for interactivity
        st.sidebar.header("🔧 Heatmap Settings")
        show_heatmap = st.sidebar.checkbox("Show Heatmap", value=True)
        radius = st.sidebar.slider("Heatmap Radius", 5, 50, 20)
        opacity = st.sidebar.slider("Heatmap Opacity", 0.1, 1.0, 0.6, step=0.1)
        blur = st.sidebar.slider("Heatmap Blur", 1, 30, 15)

        # Optional: Select intensity column if available
        if "intensity" in df.columns:
            intensity_column = "intensity"
            df["intensity"] = pd.to_numeric(df["intensity"], errors="coerce").fillna(1)
        else:
            st.warning("⚠️ No intensity column found! Using uniform intensity for all points.")
            df["intensity"] = 1  # Assign default intensity
            intensity_column = None  # Set to None to avoid passing a missing column

        # Choose a base map layer
        basemap = st.sidebar.selectbox("Choose a Base Map", ["OpenStreetMap", "Satellite", "Terrain", "Dark Mode"])

        # Initialize the map centered at the mean of uploaded coordinates
        m = leafmap.Map(center=[df["latitude"].mean(), df["longitude"].mean()], zoom=10)

        # Set base map
        if basemap == "Satellite":
            m.add_basemap("SATELLITE")
        elif basemap == "Terrain":
            m.add_basemap("TERRAIN")
        elif basemap == "Dark Mode":
            m.add_basemap("CartoDB.DarkMatter")
        else:
            m.add_basemap("OpenStreetMap")

        # Debugging: Print DataFrame Head
        st.write("🔎 **Data Preview**:", df.head())

        # Add Heatmap layer with error handling
        if show_heatmap:
            try:
                if intensity_column:  # If intensity exists
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
                else:  # If no intensity column, exclude it
                    m.add_heatmap(
                        data=df[["latitude", "longitude"]],
                        latitude="latitude",
                        longitude="longitude",
                        name="Heat Map",
                        radius=radius,
                        blur=blur,
                        opacity=opacity,
                    )
            except Exception as e:
                st.error(f"🔥 Heatmap Error: {e}")

        # Display the map in Streamlit
        m.to_streamlit(height=600)

    else:
        st.error("⚠️ Error: The Excel file must contain 'latitude' and 'longitude' columns.")

else:
    st.info("📤 Please upload an Excel file with 'latitude' and 'longitude' columns.")
