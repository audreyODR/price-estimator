import streamlit as st
import pandas as pd

st.set_page_config(page_title="Roofing Estimator", layout="wide")

SHEET_URL = st.secrets["gsheets"]["url"]

@st.cache_data
def load_data(url):
    # We skip the first 17 rows to get to the 'LINE ITEM' header on Row 18
    df = pd.read_csv(url, skiprows=17)
    return df

df_raw = load_data(SHEET_URL)

st.title("🏠 Roofing Price Estimator")

# --- CLEANING ---
# Remove rows that are just headers like "ASPHALT SHINGLES" or "PATRIOT"
# and keep only rows that have a price.
df = df_raw.dropna(subset=['SELL PRICE'])

# Clean up the price column (remove $ and commas) so we can do math
df['SELL PRICE'] = df['SELL PRICE'].replace('[\$,]', '', regex=True).astype(float)

# --- THE INTERFACE ---
st.subheader("Estimate Calculator")

col1, col2 = st.columns(2)

with col1:
    item = st.selectbox("Select Line Item", options=df['LINE ITEM'].unique())
    quantity = st.number_input("Quantity (Squares/Units)", min_value=1, value=1)

# Pull data for selected item
selected_row = df[df['LINE ITEM'] == item].iloc[0]
unit_price = selected_row['SELL PRICE']
metric = selected_row['ITEM METRIC']

with col2:
    st.metric("Unit Price", f"${unit_price:,.2f}")
    total = unit_price * quantity
    st.header(f"Total: ${total:,.2f}")
    st.caption(f"Pricing based on {metric}")

st.divider()
st.dataframe(df[['LINE ITEM', 'SELL PRICE', 'ITEM METRIC']])
