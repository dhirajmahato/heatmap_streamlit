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

        # Initialize the map centered at the mean of uploaded coordinates
        m = leafmap.Map(center=[df["latitude"].mean(), df["longitude"].mean()], zoom=10)

        # Add Heatmap layer
        m.add_heatmap(
            data=df,
            latitude="latitude",
            longitude="longitude",
            name="Heat Map",
            radius=20,
        )

        # Display the map in Streamlit
        m.to_streamlit(height=600)
    
    else:
        st.error("⚠️ Error: The Excel file must contain 'latitude' and 'longitude' columns.")

else:
    st.info("📤 Please upload an Excel file with 'latitude' and 'longitude' columns.")
