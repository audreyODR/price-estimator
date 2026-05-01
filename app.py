import streamlit as st
import pandas as pd

# Pull the URL from Streamlit's secure secrets
SHEET_URL = st.secrets["gsheets"]["url"]

@st.cache_data
def load_data(url):
    return pd.read_csv(url)

df = load_data(SHEET_URL)
st.write("Data loaded successfully!", df.head())
