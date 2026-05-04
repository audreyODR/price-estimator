import streamlit as st
import pandas as pd
import pdfplumber
import re

st.set_page_config(page_title="Smart Roofing Quoter Pro", layout="wide")

# --- 1. INITIALIZE THE GLOBAL QUOTE CART ---
if "quote_items" not in st.session_state:
    st.session_state.quote_items = []

# --- 2. GOOGLE SHEETS CONNECTION ---
SHEET_URL = st.secrets["gsheets"]["url"]

@st.cache_data(ttl=60)
def load_data(url):
    df_temp = pd.read_csv(url)
    df_temp.columns = df_temp.columns.str.strip()
    return df_temp

df_raw = load_data(SHEET_URL)

# Data Cleaning
df = df_raw.dropna(subset=['Category']) 
df['Price'] = pd.to_numeric(df['Price'].astype(str).replace('[\$,]', '', regex=True), errors='coerce')

if 'Min_Qty' in df.columns:
    df['Min_Qty'] = pd.to_numeric(df['Min_Qty'], errors='coerce')
if 'Max_Qty' in df.columns:
    df['Max_Qty'] = pd.to_numeric(df['Max_Qty'], errors='coerce')

df['Option 1'] = df['Option 1'].fillna('N/A')
df['Option 2'] = df['Option 2'].fillna('N/A')
if 'Option 3' in df.columns:
    df['Option 3'] = df['Option 3'].fillna('N/A')
if 'Tier_Target' in df.columns:
    df['Tier_Target'] = df['Tier_Target'].fillna('N/A')

df = df.dropna(subset=['Price']) 

# --- 3. THE "SUPER" PDF PARSER ---
def extract_roofr_data(uploaded_file):
    data = {
        "sqft": 0.0, "flat": 0.0, "pitch": 0.0,
        "ridges": 0.0, "hips": 0.0, "valleys": 0.0,
        "eaves": 0.0, "rakes": 0.0, "wall_flash": 0.0, "step_flash": 0.0
    }
    
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text().lower()
            if text:
                def get_val(pattern):
                    match = re.search(pattern, text)
                    if match:
                        val_str = match.group(1).replace(',', '').replace('o', '0')
                        try: return float(val_str)
                        except: return 0.0
                    return None

                v = get_val(r"total roof area.*?(?:\"|:)\s*([\d,o]+)")
                if v is not None: data["sqft"] = v
                
                v = get_val(r"flat (?:roof )?area.*?(?:\"|:)\s*([\d,o]+)")
                if v is not None: data["flat"] = v
                
                v = get_val(r"pitch\s*[:]?\s*(\d+)/12")
                if v is not None: data["pitch"] = v
                    
                v = get_val(r"ridges[^\d,o]*([\d,o]+)")
                if v is not None: data["ridges"] = v
                    
                v = get_val(r"hips[^\d,o]*([\d,o]+)")
                if v is not None: data["hips"] = v
                    
                v = get_val(r"valleys[^\d,o]*([\d,o]+)")
                if v is not None: data["valleys"] = v
                    
                v = get_val(r"eaves[^\d,o]*([\d,o]+)")
                if v is not None: data["eaves"] = v
                    
                v = get_val(r"rakes[^\d,o]*([\d,o]+)")
                if v is not None: data["rakes"] = v
                    
                v = get_val(r"wall flashing[^\d,o]*([\d,o]+)")
                if v is not None: data["wall_flash"] = v
                    
                v = get_val(r"step flashing[^\d,o]*([\d,o]+)")
                if v is not None: data["step_flash"] = v
                
    return data

# --- 4. SIDEBAR & BASE MEASUREMENTS ---
with st.sidebar:
    st.header("📂 Roofr Integration")
    uploaded_pdf = st.file_uploader("Upload Roofr PDF", type="pdf")
    
    parsed_data = {"sqft": 0.0, "flat": 0.0, "pitch": 0.0, "ridges": 0.0, "hips": 0.0, "valleys": 0.0, "eaves": 0.0, "rakes": 0.0, "wall_flash": 0.0, "step_flash": 0.0}
    if uploaded_pdf:
        parsed_data = extract_roofr_data(uploaded_pdf)
        st.success("All complex measurements extracted!")
    
    st.divider()
    st.subheader("📏 Base Measurements")
    
    base_sqft = st.number_input("Total Sq Ft", value=parsed_data["sqft"], step=10.0)
    base_flat = st.number_input("Flat Roof Sq Ft", value=parsed_data["flat"], step=10.0)
    base_pitch = st.number_input("Predominant Pitch (X/12)", value=parsed_data["pitch"], step=1.0)
    
    st.markdown("**Linear Measurements (ft)**")
    colA, colB = st.columns(2)
    with colA:
        base_ridges = st.number_input("Ridges", value=parsed_data["ridges"])
        base_hips = st.number_input("Hips", value=parsed_data["hips"])
        base_valleys = st.number_input("Valleys", value=parsed_data["valleys"])
    with colB:
        base_eaves = st.number_input("Eaves", value=parsed_data["eaves"])
        base_rakes = st.number_input("Rakes", value=parsed_data["rakes"])
        base_wall = st.number_input("Wall Flash", value=parsed_data["wall_flash"])
        base_step = st.number_input("Step Flash", value=parsed_data["step_flash"])
    
    # --- PROPRIETARY CALCULATIONS ---
    base_squares = base_sqft / 100
    flat_squares = base_flat / 100
    total_flashing = base_wall + base_step
    
    buffer_sqft = base_sqft + base_hips + base_ridges + base_valleys + ((base_eaves + base_rakes) / 100)
    complex_squares = buffer_sqft / 100

    st.divider()
    st.subheader("📐 Calculated Squares")
    st.info(f"**Base Roof:** {base_squares:,.2f} SQ\n\n**Complex (with buffer/starter):** {complex_squares:,.2f} SQ")

# Package measurements for the routing engine
meas = {
    "base_squares": base_squares, "flat_squares": flat_squares, "complex_squares": complex_squares,
    "base_valleys": base_valleys, "base_eaves": base_eaves, "total_flashing": total_flashing,
    "base_ridges": base_ridges, "base_pitch": base_pitch
}

# --- 5. THE REUSABLE FORM ENGINE ---
# This function lets us generate the quoting form on ANY tab perfectly!
def render_quoting_interface(service_name, df, meas_dict, key_prefix):
    st.header(f"Build {service_name} Quote")
    
    col1, col2 = st.columns(2)
    with col1:
        categories = df['Category'].unique()
        selected_category = st.selectbox("1. Select Category", categories, key=f"{key_prefix}_cat")
        
        filtered_df = df[df['Category'] == selected_category]
        opt1_choices = [x for x in filtered_df['Option 1'].unique() if str(x).strip().upper() != 'N/A' and str(x).strip() != '']
        selected_opt1 = st.selectbox("2. Option 1", opt1_choices, key=f"{key_prefix}_opt1") if opt1_choices else "N/A"
        
        final_df = filtered_df[filtered_df['Option 1'] == selected_opt1] if selected_opt1 != "N/A" else filtered_df[filtered_df['Option 1'] == 'N/A']
            
        opt2_choices = [x for x in final_df['Option 2'].unique() if str(x).strip().upper() != 'N/A' and str(x).strip() != '']
        selected_opt2 = st.selectbox("3. Option 2", opt2_choices, key=f"{key_prefix}_opt2") if opt2_choices else "N/A"
        if selected_opt2 != "N/A": final_df = final_df[final_df['Option 2'] == selected_opt2]

        if 'Option 3' in final_df.columns:
            opt3_choices = [x for x in final_df['Option 3'].unique() if str(x).strip().upper() != 'N/A' and str(x).strip() != '']
            selected_opt3 = st.selectbox("4. Option 3", opt3_choices, key=f"{key_prefix}_opt3") if opt3_choices else "N/A"
            if selected_opt3 != "N/A": final_df = final_df[final_df['Option 3'] == selected_opt3]
        else:
            selected_opt3 = "N/A"

    with col2:
        st.subheader("Calculation Details")
        
        if not final_df.empty:
            raw_calc_unit = str(final_df['Measurement'].values[0]).strip() if 'Measurement' in final_df.columns else "Flat Fee"
            calc_unit_lower = raw_calc_unit.lower()
            
            raw_tier_target = str(final_df['Tier_Target'].values[0]).strip() if 'Tier_Target' in final_df.columns else "N/A"
            tier_target_lower = raw_tier_target.lower()
            cat_lower = str(selected_category).lower()
            
            # --- SMART ROUTING LOGIC ---
            if "sq" in calc_unit_lower or "square" in calc_unit_lower:
                if "shingle" in cat_lower or "layer removal" in cat_lower or "plywood" in cat_lower:
                    qty = st.number_input("Squares (Complex Buffer Math)", value=float(meas_dict["complex_squares"]), key=f"{key_prefix}_qty_csq")
                elif "low slope" in cat_lower or "flat" in cat_lower:
                    qty = st.number_input("Squares (Flat Area)", value=float(meas_dict["flat_squares"]), key=f"{key_prefix}_qty_fsq")
                else:
                    qty = st.number_input("Squares (Base Roof Area)", value=float(meas_dict["base_squares"]), key=f"{key_prefix}_qty_bsq")
                    
            elif "lf" in calc_unit_lower or "linear" in calc_unit_lower:
                if "valley" in cat_lower:
                    qty = st.number_input("Linear Feet (Valleys)", value=float(meas_dict["base_valleys"]), key=f"{key_prefix}_qty_val")
                elif "smartvent" in cat_lower or "smart vent" in cat_lower:
                    qty = st.number_input("Linear Feet (Eaves)", value=float(meas_dict["base_eaves"]), key=f"{key_prefix}_qty_eav")
                elif "flashing" in cat_lower or "wall" in cat_lower or "step" in cat_lower:
                    qty = st.number_input("Linear Feet (Wall + Step)", value=float(meas_dict["total_flashing"]), key=f"{key_prefix}_qty_flash")
                else:
                    qty = st.number_input("Linear Feet (Ridges)", value=float(meas_dict["base_ridges"]), key=f"{key_prefix}_qty_ridge")
                    
            elif "flat" in calc_unit_lower:
                qty = 1
                st.info("Flat fee item. No measurements needed.")
            else: 
                qty = st.number_input("Quantity", min_value=1.0, value=1.0, step=1.0, key=f"{key_prefix}_qty_std")
                
            # INVISIBLE TIER ENGINE
            if "sq" in tier_target_lower:
                lookup_val = qty
            elif "pitch" in tier_target_lower:
                lookup_val = meas_dict["base_pitch"]
            else:
                lookup_val = None 
                
            if lookup_val is not None and 'Min_Qty' in final_df.columns and 'Max_Qty' in final_df.columns:
                valid_tier = final_df[(final_df['Min_Qty'] <= lookup_val) & (final_df['Max_Qty'] >= lookup_val)]
                if not valid_tier.empty: final_df = valid_tier
        
            # MATH & DISPLAY
            if not final_df.empty:
                unit_price = final_df['Price'].values[0]
                st.write(f"**Unit Price:** ${unit_price:,.2f} ({raw_calc_unit})")
                
                line_total = unit_price * qty
                st.metric("Line Item Total", f"${line_total:,.2f}")
                
                if st.button("➕ Add to Master Quote", use_container_width=True, key=f"{key_prefix}_add"):
                    desc_parts = [str(selected_opt1)]
                    if selected_opt2 != "N/A": desc_parts.append(str(selected_opt2))
                    if selected_opt3 != "N/A": desc_parts.append(str(selected_opt3))
                    item_desc = " - ".join(desc_parts)
                    if item_desc == "N/A" or item_desc == "": item_desc = selected_category
                    
                    st.session_state.quote_items.append({
                        "Service": service_name, "Item": item_desc, "Qty": qty, 
                        "Unit Price": f"${unit_price:,.2f}", "Total": line_total
                    })
                    st.success(f"Added {item_desc} to quote!")
            else:
                st.warning("Pricing details not found for this tier.")
        else:
            st.warning("Pricing details not found for this combination.")

# --- 6. THE SERVICE TABS ---
st.title("🚀 Smart Roofing Quoter Pro")

tab_roof, tab_side, tab_gut, tab_win, tab_ins, tab_srv = st.tabs([
    "Roofing", "Siding", "Gutters", "Windows/Doors", "Insulation", "Service"
])

# Deploy the Reusable Form Engine to the active tabs!
with tab_roof:
    render_quoting_interface("Roofing", df, meas, "roof")

with tab_gut:
    render_quoting_interface("Gutters", df, meas, "gut")

# Placeholders for future modules
with tab_side: st.info("Siding module coming soon...")
with tab_win: st.info("Windows module coming soon...")
with tab_ins: st.info("Insulation module coming soon...")
with tab_srv: st.info("Service module coming soon...")

# --- 7. THE MASTER QUOTE ---
st.divider()
st.header("🛒 Current Master Quote")

if len(st.session_state.quote_items) > 0:
    cart_df = pd.DataFrame(st.session_state.quote_items)
    
    # Format the Total column specifically as Currency
    st.dataframe(
        cart_df, 
        hide_index=True, 
        use_container_width=True,
        column_config={
            "Total": st.column_config.NumberColumn("Total", format="$%.2f")
        }
    )
    
    grand_total = cart_df['Total'].sum()
    st.subheader(f"Grand Total: ${grand_total:,.2f}")
    if st.button("🗑️ Clear Quote"):
        st.session_state.quote_items = []
        st.rerun()
else:
    st.caption("Your quote is currently empty.")