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
        
        for col in ['Min_Qty', 'Max_Qty']:
            if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')

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
    f = df[df['Option 1'].str.contains(item_name, case=False, na=False)]
    if f.empty: return 0.0
    
    if 'Min_Qty' in f.columns and 'Max_Qty' in f.columns:
        f_tier = f[(f['Min_Qty'] <= lookup_val) & (f['Max_Qty'] >= lookup_val)]
        if not f_tier.empty:
            return f_tier['Price'].values[0]
    return f['Price'].values[0]

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
        
        if 'Option 2' in f.columns:
            o2_list = [x for x in f['Option 2'].unique() if x != 'N/A']
            opt2 = st.selectbox("3. Option 2", o2_list, key=f"{key}_o2") if o2_list else "N/A"
            if opt2 != "N/A": f = f[f['Option 2'] == opt2]
        else:
            opt2 = "N/A"
            
        if 'Option 3' in f.columns:
            o3_list = [x for x in f['Option 3'].unique() if x != 'N/A']
            opt3 = st.selectbox("4. Option 3", o3_list, key=f"{key}_o3") if o3_list else "N/A"
            if opt3 != "N/A": f = f[f['Option 3'] == opt3]
        else:
            opt3 = "N/A"
        
    with c2:
        if not f.empty:
            m_type = str(f['Measurement'].values[0]).lower() if 'Measurement' in f.columns else "flat fee"
            t_target = str(f['Tier_Target'].values[0]).lower() if 'Tier_Target' in f.columns else "n/a"
            cat_lower = str(cat).lower()
            
            # THE FIX: Dynamic keys attached to the math force the box to reset when data changes!
            if "sq" in m_type or "square" in m_type:
                if any(x in cat_lower for x in ["shingle", "removal", "plywood"]):
                    qty = st.number_input("Squares (Complex Buffer)", value=float(meas_dict["complex_squares"]), key=f"{key}_csq_{meas_dict['complex_squares']}")
                elif "low slope" in cat_lower or "flat" in cat_lower:
                    qty = st.number_input("Squares (Flat Area)", value=float(meas_dict["flat_squares"]), key=f"{key}_fsq_{meas_dict['flat_squares']}")
                else: 
                    qty = st.number_input("Squares (Base Roof)", value=float(meas_dict["base_squares"]), key=f"{key}_bsq_{meas_dict['base_squares']}")
            
            elif "lf" in m_type or "linear" in m_type:
                if service == "Gutters": 
                    qty = st.number_input("Linear Feet (Eaves)", value=float(meas_dict["base_eaves"]), key=f"{key}_geav_{meas_dict['base_eaves']}")
                elif "valley" in cat_lower: 
                    qty = st.number_input("Linear Feet (Valleys)", value=float(meas_dict["base_valleys"]), key=f"{key}_val_{meas_dict['base_valleys']}")
                elif any(x in cat_lower for x in ["smartvent", "smart vent", "edge"]): 
                    qty = st.number_input("Linear Feet (Eaves)", value=float(meas_dict["base_eaves"]), key=f"{key}_eav_{meas_dict['base_eaves']}")
                elif any(x in cat_lower for x in ["flashing", "wall", "step", "counter"]): 
                    qty = st.number_input("Linear Feet (Wall + Step)", value=float(meas_dict["total_flashing"]), key=f"{key}_fla_{meas_dict['total_flashing']}")
                else: 
                    qty = st.number_input("Linear Feet (Ridges)", value=float(meas_dict["base_ridges"]), key=f"{key}_rid_{meas_dict['base_ridges']}")
            
            elif "flat" in m_type:
                qty = 1
                st.info("Flat fee item. No measurements needed.")
            
            else: 
                qty = st.number_input("Quantity", min_value=1.0, value=1.0, key=f"{key}_std_{meas_dict['base_squares']}")
            
            # Tier Logic
            lookup = qty if "sq" in t_target else meas_dict["base_pitch"] if "pitch" in t_target else None
            if lookup is not None and 'Min_Qty' in f.columns and 'Max_Qty' in f.columns:
                t_row = f[(f['Min_Qty'] <= lookup) & (f['Max_Qty'] >= lookup)]
                if not t_row.empty: f = t_row
            
            price = f['Price'].values[0]
            display_unit = str(f['Measurement'].values[0]).strip() if 'Measurement' in f.columns else "Flat Fee"
            st.write(f"**Unit Price:** ${price:,.2f} ({display_unit})")
            
            total = price * qty
            st.metric("Line Total", f"${total:,.2f}")
            
            if st.button("➕ Add to Quote", key=f"{key}_btn"):
                desc_parts = [str(opt1)]
                if opt2 != "N/A": desc_parts.append(str(opt2))
                if opt3 != "N/A": desc_parts.append(str(opt3))
                desc = " - ".join(desc_parts) if desc_parts != ["N/A"] else cat
                
                st.session_state.quote_items.append({"Service": service, "Item": desc, "Qty": qty, "Unit Price": f"${price:,.2f}", "Total": total})
                st.success("Added!")

# --- 7. UI TABS ---
st.title("🚀 Smart Quoter Pro")
t_pres, t_roof, t_gut, t_side, t_win = st.tabs(["Presentation", "Roofing", "Gutters", "Siding", "Windows"])

with t_pres:
    st.header("✨ Homeowner Presentation Mode")
    series = st.radio("Select Presentation Tier", ["Base Architectural Series", "Luxury Estate Series"], horizontal=True)
    
    df_r = all_sheets.get("Roofing", pd.DataFrame())
    
    if not df_r.empty:
        p_patriot = get_tier_price(df_r, "Patriot", meas["complex_squares"], "Squares") * meas["complex_squares"]
        p_landmark = get_tier_price(df_r, "Landmark Pro", meas["complex_squares"], "Squares") * meas["complex_squares"]
        p_northgate = get_tier_price(df_r, "Northgate", meas["complex_squares"], "Squares") * meas["complex_squares"]
        p_belmont = get_tier_price(df_r, "Belmont", meas["complex_squares"], "Squares") * meas["complex_squares"]
        p_grand = get_tier_price(df_r, "Grand Manor", meas["complex_squares"], "Squares") * meas["complex_squares"]

        if st.button("🖼️ Open Presentation Slides"):
            if series == "Base Architectural Series":
                html_code = f"""
                <div style="font-family: 'Merriweather', serif; padding: 40px; color: #1a365d;">
                    <h1 style="border-bottom: 2px solid #c29e61; padding-bottom: 15px;">Architectural Investment Tiers</h1>
                    <div style="display: flex; gap: 20px; margin-top: 40px;">
                        <div style="flex: 1; padding: 25px; background: #fdfbf7; border-top: 5px solid #1a365d; border-radius: 8px;">
                            <h3 style="color: #c29e61;">GOOD: Patriot</h3>
                            <h2 style="font-size: 32px;">${p_patriot:,.2f}</h2>
                            <p style="font-size: 14px;">Reliable entry-level architectural protection.</p>
                        </div>
                        <div style="flex: 1; padding: 25px; background: #fffcf5; border-top: 5px solid #c29e61; border-radius: 8px; box-shadow: 0 10px 20px rgba(0,0,0,0.1);">
                            <h3 style="color: #c29e61;">BETTER: Landmark Pro</h3>
                            <h2 style="font-size: 32px;">${p_landmark:,.2f}</h2>
                            <p style="font-size: 14px;"><b>Recommended:</b> Best balance of cost and performance.</p>
                        </div>
                        <div style="flex: 1; padding: 25px; background: #fdfbf7; border-top: 5px solid #1a365d; border-radius: 8px;">
                            <h3 style="color: #c29e61;">BEST: Northgate</h3>
                            <h2 style="font-size: 32px;">${p_northgate:,.2f}</h2>
                            <p style="font-size: 14px;">Maximum impact and storm resilience.</p>
                        </div>
                    </div>
                </div>
                """
            else:
                html_code = f"""
                <div style="font-family: 'Merriweather', serif; padding: 40px; color: #1a365d;">
                    <h1 style="border-bottom: 2px solid #c29e61; padding-bottom: 15px;">Luxury Estate Collection</h1>
                    <div style="display: flex; gap: 40px; margin-top: 40px;">
                        <div style="flex: 1; padding: 35px; background: #fdfbf7; border-top: 5px solid #1a365d; border-radius: 8px;">
                            <h3 style="color: #c29e61;">Luxury: Belmont</h3>
                            <h2 style="font-size: 40px;">${p_belmont:,.2f}</h2>
                            <p>Authentic slate replication without the stone weight.</p>
                        </div>
                        <div style="flex: 1; padding: 35px; background: #fffcf5; border-top: 5px solid #c29e61; border-radius: 8px; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
                            <h3 style="color: #c29e61;">Grand Luxury: Grand Manor</h3>
                            <h2 style="font-size: 40px;">${p_grand:,.2f}</h2>
                            <p>Flagship triple-layer construction for the ultimate estate.</p>
                        </div>
                    </div>
                </div>
                """
            components.html(html_code, height=500)

with t_roof: render_interface("Roofing", all_sheets.get("Roofing", pd.DataFrame()), meas, "r")
with t_gut: render_interface("Gutters", all_sheets.get("Gutters", pd.DataFrame()), meas, "g")

# --- 8. CART ---
st.divider()
st.header("🛒 Current Master Quote")

if len(st.session_state.quote_items) > 0:
    c_df = pd.DataFrame(st.session_state.quote_items)
    
    st.dataframe(
        c_df, 
        hide_index=True, 
        use_container_width=True,
        column_config={
            "Total": st.column_config.NumberColumn("Total", format="$%.2f")
        }
    )
    
    grand_total = c_df['Total'].sum()
    st.subheader(f"Grand Total: ${grand_total:,.2f}")
    
    # --- NEW: SIDE-BY-SIDE EXPORT & CLEAR BUTTONS ---
    colA, colB = st.columns(2)
    
    with colA:
        # Convert the dataframe to a downloadable CSV
        csv_data = c_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="💾 Download Quote for CRM (CSV)",
            data=csv_data,
            file_name="Master_Roofing_Quote.csv",
            mime="text/csv",
            use_container_width=True
        )
        
    with colB:
        if st.button("🗑️ Clear Quote", use_container_width=True):
            st.session_state.quote_items = []
            st.rerun()
else:
    st.caption("Your quote is currently empty.")