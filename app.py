import streamlit as st
import pandas as pd
import pdfplumber
import re

# --- PDF PARSING FUNCTION ---
def extract_roofr_data(uploaded_file):
    data = {"sqft": 0.0, "ridges": 0.0}
    with pdfplumber.open(uploaded_file) as pdf:
        # Roofr reports usually have the summary table on page 4 or 6
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                # Look for Total Roof Area (e.g., 3531 sqft)
                area_match = re.search(r"Total roof area:\s*([\d,]+)", text)
                if area_match:
                    data["sqft"] = float(area_match.group(1).replace(',', ''))
                
                # Look for Total Ridges (e.g., 129ft 5in)
                ridge_match = re.search(r"Total ridges\s*,\s*\"?(\d+)ft", text)
                if ridge_match:
                    data["ridges"] = float(ridge_match.group(1))
    return data

# --- UI SETUP ---
st.title("🚀 Smart Roofing Quoter")

with st.sidebar:
    st.header("📂 Roofr Integration")
    uploaded_pdf = st.file_uploader("Upload Roofr PDF", type="pdf")
    
    # Auto-parse if file is uploaded
    parsed_data = {"sqft": 0.0, "ridges": 0.0}
    if uploaded_pdf:
        parsed_data = extract_roofr_data(uploaded_pdf)
        st.success("Data extracted!")

# --- EDITABLE MEASUREMENTS ---
st.subheader("📏 Project Measurements")
col1, col2 = st.columns(2)

with col1:
    # The 'value' is set to the parsed data, but the user can overwrite it
    sqft = st.number_input("Total Sq Ft", value=parsed_data["sqft"], step=10.0)

with col2:
    ridges = st.number_input("Total Ridges (ft)", value=parsed_data["ridges"], step=1.0)

# --- PRICING LOGIC ---
st.divider()
st.header("2. Add Line Items")
# Your existing pricing spreadsheet logic goes here, using 'sqft' for calculations!

st.set_page_config(page_title="Roofing Quoter Pro", layout="wide")

SHEET_URL = st.secrets["gsheets"]["url"]

@st.cache_data
def load_data(url):
    return pd.read_csv(url, skiprows=17)

df_raw = load_data(SHEET_URL)

# --- CLEANING ---
df = df_raw.dropna(subset=['LINE ITEM'])
df['SELL PRICE'] = pd.to_numeric(df['SELL PRICE'].replace('[\$,]', '', regex=True), errors='coerce')
df = df.dropna(subset=['SELL PRICE'])

st.title("🚀 Smart Roofing Quoter")

# --- SESSION STATE (The "Shopping Cart") ---
# This tells the app to remember items even when the page updates
if 'quote_items' not in st.session_state:
    st.session_state.quote_items = []

st.divider()

# --- BUILDER INTERFACE ---
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Add Line Items")
    
    # Selection
    item = st.selectbox("Select Material / Service / Add-on", options=df['LINE ITEM'].unique())
    quantity = st.number_input("Quantity", min_value=0.1, value=1.0, step=0.1)
    
    # Lookup price
    selected_row = df[df['LINE ITEM'] == item].iloc[0]
    unit_price = selected_row['SELL PRICE']
    
    st.info(f"**Unit Price:** ${unit_price:,.2f}")
    
    # The Action Button
    if st.button("➕ Add to Quote", use_container_width=True):
        st.session_state.quote_items.append({
            "Item": item,
            "Quantity": quantity,
            "Unit Price": unit_price,
            "Total": quantity * unit_price
        })
        st.success(f"Added {item} to quote!")

with col2:
    st.subheader("2. Current Quote")
    
    if len(st.session_state.quote_items) > 0:
        # Convert our "cart" into a nice table
        quote_df = pd.DataFrame(st.session_state.quote_items)
        st.dataframe(quote_df, hide_index=True, use_container_width=True)
        
        # Calculate Grand Total
        grand_total = quote_df['Total'].sum()
        st.metric("Grand Total", f"${grand_total:,.2f}")
        
        # Clear button
        if st.button("🗑️ Clear Quote"):
            st.session_state.quote_items = []
            st.rerun()
    else:
        st.caption("Quote is currently empty. Add items from the left.")
