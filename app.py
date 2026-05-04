import streamlit as st
import pandas as pd
import pdfplumber
import re
import streamlit.components.v1 as components

# This MUST be the first Streamlit command!
st.set_page_config(page_title="Smart Roofing Quoter Pro", layout="wide")

# --- 1. INITIALIZE THE GLOBAL QUOTE CART ---
if "quote_items" not in st.session_state:
    st.session_state.quote_items = []

# --- 2. GOOGLE SHEETS CONNECTION (MULTI-TAB EXCEL) ---
SHEET_URL = st.secrets["gsheets"]["url"]

@st.cache_data(ttl=60)
def load_all_sheets(url):
    # Convert standard sharing URL into an Excel export URL to grab ALL tabs
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
    if match:
        sheet_id = match.group(1)
        export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    else:
        export_url = url
    
    xls = pd.read_excel(export_url, sheet_name=None, engine='openpyxl')
    cleaned_sheets = {}
    
    for sheet_name, df_raw in xls.items():
        df_raw.columns = df_raw.columns.str.strip()
        if 'Category' not in df_raw.columns: continue
            
        df = df_raw.dropna(subset=['Category']) 
        df['Price'] = pd.to_numeric(df['Price'].astype(str).replace('[\$,]', '', regex=True), errors='coerce')
        df = df.dropna(subset=['Price']) 
        
        # Clean Tier Columns
        for col in ['Min_Qty', 'Max_Qty']:
            if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')

        # Standardize Strings
        for col in ['Option 1', 'Option 2', 'Option 3', 'Tier_Target', 'Measurement']:
            if col in df.columns: df[col] = df[col].fillna('N/A').astype(str).str.strip()
            
        cleaned_sheets[sheet_name.strip()] = df
    return cleaned_sheets

all_sheets = load_all_sheets(SHEET_URL)

# --- 3. PDF PARSER ---
def extract_roofr_data(uploaded_file):
    data = {
        "sqft": 0.0, "flat": 0.0, "pitch": 0.0, "ridges": 0.0, "hips": 0.0, 
        "valleys": 0.0, "eaves": 0.0, "rakes": 0.0, "wall_flash": 0.0, "step_flash": 0.0
    }
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text().lower()
            if text:
                def get_val(pattern):
                    match = re.search(pattern, text)
                    if match:
                        v = match.group(1).replace(',', '').replace('o', '0')
                        try: return float(v)
                        except: return 0.0
                    return None

                if (v := get_val(r"total roof area.*?(?:\"|:)\s*([\d,o]+)")) is not None: data["sqft"] = v
                if (v := get_val(r"total flat.*?(?:\"|:)\s*([\d,o]+)")) is not None: data["flat"] = v
                if (v := get_val(r"pitch\s*[:]?\s*(\d+)/12")) is not None: data["pitch"] = v
                if (v := get_val(r"total ridges\s*.*?([\d,o]+)")) is not None: data["ridges"] = v
                if (v := get_val(r"total hips\s*.*?([\d,o]+)")) is not None: data["hips"] = v
                if (v := get_val(r"total valleys\s*.*?([\d,o]+)")) is not None: data["valleys"] = v
                if (v := get_val(r"total eaves\s*.*?([\d,o]+)")) is not None: data["eaves"] = v
                if (v := get_val(r"total rakes\s*.*?([\d,o]+)")) is not None: data["rakes"] = v
                if (v := get_val(r"total wall flashing\s*.*?([\d,o]+)")) is not None: data["wall_flash"] = v
                if (v := get_val(r"total step flashing\s*.*?([\d,o]+)")) is not None: data["step_flash"] = v
    return data

# --- 4. SIDEBAR & BASE MEASUREMENTS ---
with st.sidebar:
    st.header("📂 Roofr Integration")
    uploaded_pdf = st.file_uploader("Upload Roofr PDF", type="pdf")
    
    p = {"sqft": 0.0, "flat": 0.0, "pitch": 0.0, "ridges": 0.0, "hips": 0.0, "valleys": 0.0, "eaves": 0.0, "rakes": 0.0, "wall_flash": 0.0, "step_flash": 0.0}
    if uploaded_pdf:
        p = extract_roofr_data(uploaded_pdf)
        st.success("Measurements extracted!")
    
    st.divider()
    st.subheader("📏 Base Measurements")
    b_sqft = st.number_input("Total Sq Ft", value=p["sqft"])
    b_flat = st.number_input("Flat Roof Sq Ft", value=p["flat"])
    b_pitch = st.number_input("Pitch (X/12)", value=p["pitch"])
    
    colA, colB = st.columns(2)
    with colA:
        b_ridges = st.number_input("Ridges", value=p["ridges"])
        b_valleys = st.number_input("Valleys", value=p["valleys"])
    with colB:
        b_eaves = st.number_input("Eaves", value=p["eaves"])
        b_rakes = st.number_input("Rakes", value=p["rakes"])
    
    b_hips = st.number_input("Hips", value=p["hips"])
    b_wall = st.number_input("Wall Flash", value=p["wall_flash"])
    b_step = st.number_input("Step Flash", value=p["step_flash"])

    # CALCULATIONS
    b_sqs = b_sqft / 100
    f_sqs = b_flat / 100
    t_flash = b_wall + b_step
    # YOUR FORMULA: (SqFt + Hips + Ridges + Valleys + ((Eaves+Rakes)/100)) / 100
    complex_sqs = (b_sqft + b_hips + b_ridges + b_valleys + ((b_eaves + b_rakes)/100)) / 100

    st.divider()
    st.subheader("📐 Calculated Squares")
    st.info(f"**Base Roof:** {b_sqs:,.2f} SQ\n\n**Complex (w/ Starter):** {complex_sqs:,.2f} SQ")

meas = {
    "base_squares": b_sqs, "flat_squares": f_sqs, "complex_squares": complex_sqs,
    "base_valleys": b_valleys, "base_eaves": b_eaves, "total_flashing": t_flash,
    "base_ridges": b_ridges, "base_pitch": b_pitch
}

# --- 5. THE PRESENTATION HELPER ---
def get_tier_price(df, item_name, lookup_val, tier_target_type):
    # Filters the sheet for the specific shingle name and checks the tier math
    f = df[df['Option 1'].str.contains(item_name, case=False, na=False)]
    if f.empty: return 0.0
    
    # Run the invisible tier engine
    f_tier = f[(f['Min_Qty'] <= lookup_val) & (f['Max_Qty'] >= lookup_val)]
    if not f_tier.empty:
        return f_tier['Price'].values[0]
    return f['Price'].values[0] # Fallback to first row if tier not found

# --- 6. THE QUOTING ENGINE ---
def render_interface(service, df, meas_dict, key):
    if df.empty:
        st.error(f"⚠️ Tab '{service}' not found."); return
    
    st.header(f"Build {service} Quote")
    c1, c2 = st.columns(2)
    with c1:
        cat = st.selectbox("1. Category", df['Category'].unique(), key=f"{key}_cat")
        f = df[df['Category'] == cat]
        
        opt1 = st.selectbox("2. Option 1", f['Option 1'].unique(), key=f"{key}_o1")
        f = f[f['Option 1'] == opt1]
        
        o