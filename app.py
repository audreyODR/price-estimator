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
    return pd.read_csv(url)

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

# --- 3. PDF PARSER ---
def extract_roofr_data(uploaded_file):
    data = {"sqft": 0.0, "ridges": 0.0, "pitch": 0.0}
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                area_match = re.search(r"Total roof area:\s*([\d,]+)", text)
                if area_match:
                    data["sqft"] = float(area_match.group(1).replace(',', ''))
                
                ridge_match = re.search(r"ridges[^\d]*(\d+)", text.lower())
                if ridge_match:
                    data["ridges"] = float(ridge_match.group(1))
                    
                pitch_match = re.search(r"pitch\s*[:]?\s*(\d+)/12", text.lower())
                if pitch_match:
                    data["pitch"] = float(pitch_match.group(1))
    return data

# --- 4. SIDEBAR & BASE MEASUREMENTS ---
with st.sidebar:
    st.header("📂 Roofr Integration")
    uploaded_pdf = st.file_uploader("Upload Roofr PDF", type="pdf")
    
    parsed_data = {"sqft": 0.0, "ridges": 0.0, "pitch": 0.0}
    if uploaded_pdf:
        parsed_data = extract_roofr_data(uploaded_pdf)
        st.success("Measurements & Pitch extracted!")
    
    st.divider()
    st.subheader("📏 Base Measurements")
    base_sqft = st.number_input("Total Sq Ft", value=parsed_data["sqft"], step=10.0)
    base_ridges = st.number_input("Total Ridges (ft)", value=parsed_data["ridges"], step=1.0)
    base_pitch = st.number_input("Predominant Pitch (X/12)", value=parsed_data["pitch"], step=1.0)
    
    base_squares = base_sqft / 100

# --- 5. THE SERVICE TABS ---
st.title("🚀 Smart Roofing Quoter Pro")

tab_roof, tab_side, tab_gut, tab_win, tab_ins, tab_srv = st.tabs([
    "Roofing", "Siding", "Gutters", "Windows/Doors", "Insulation", "Service"
])

# --- ROOFING BUILDER ---
with tab_roof:
    st.header("Build Roofing Quote")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Step 1: Pick Category
        categories = df['Category'].unique()
        selected_category = st.selectbox("1. Select Category", categories)
        
        # Step 2: Pick Option 1
        filtered_df = df[df['Category'] == selected_category]
        opt1_choices = [x for x in filtered_df['Option 1'].unique() if str(x).strip().upper() != 'N/A' and str(x).strip() != '']
        selected_opt1 = st.selectbox("2. Option 1", opt1_choices) if opt1_choices else "N/A"
        
        if selected_opt1 != "N/A":
            final_df = filtered_df[filtered_df['Option 1'] == selected_opt1]
        else:
            final_df = filtered_df[filtered_df['Option 1'] == 'N/A']
            
        # Step 3: Pick Option 2
        opt2_choices = [x for x in final_df['Option 2'].unique() if str(x).strip().upper() != 'N/A' and str(x).strip() != '']
        selected_opt2 = st.selectbox("3. Option 2", opt2_choices) if opt2_choices else "N/A"
        
        if selected_opt2 != "N/A":
            final_df = final_df[final_df['Option 2'] == selected_opt2]

        # Step 4: Pick Option 3
        if 'Option 3' in final_df.columns:
            opt3_choices = [x for x in final_df['Option 3'].unique() if str(x).strip().upper() != 'N/A' and str(x).strip() != '']
            selected_opt3 = st.selectbox("4. Option 3", opt3_choices) if opt3_choices else "N/A"
            
            if selected_opt3 != "N/A":
                final_df = final_df[final_df['Option 3'] == selected_opt3]
        else:
            selected_opt3 = "N/A"

    with col2:
        st.subheader("Calculation Details")
        
        if not final_df.empty:
            # 1. Identify the calculation type FIRST
            calc_unit = str(final_df['Measurement'].values[0]).strip() if 'Measurement' in final_df.columns else "Flat Fee"
            tier_target = str(final_df['Tier_Target'].values[0]).strip() if 'Tier_Target' in final_df.columns else "N/A"
            
            # 2. ASK FOR THE QUANTITY FIRST so it can drive the math
            if calc_unit == "Per Square":
                qty = st.number_input("Squares (Auto-filled but editable)", value=float(base_squares))
            elif calc_unit == "Per LF":
                qty = st.number_input("Linear Feet (Auto-filled but editable)", value=float(base_ridges))
            elif calc_unit == "Flat Fee":
                qty = 1
                st.info("Flat fee item. No measurements needed.")
            else: 
                qty = st.number_input("Quantity", min_value=1.0, value=1.0, step=1.0)
                
            # 3. SET THE TARGET FOR THE INVISIBLE TIER ENGINE
            if tier_target == "Squares":
                lookup_val = qty
            elif tier_target == "Pitch":
                lookup_val = base_pitch
            else:
                lookup_val = None 
                
            # 4. RUN THE INVISIBLE ENGINE
            if lookup_val is not None and 'Min_Qty' in final_df.columns and 'Max_Qty' in final_df.columns:
                valid_tier = final_df[(final_df['Min_Qty'] <= lookup_val) & (final_df['Max_Qty'] >= lookup_val)]
                if not valid_tier.empty:
                    final_df = valid_tier
        
            # 5. NOW GRAB THE CORRECT PRICE & DISPLAY IT
            if not final_df.empty:
                unit_price = final_df['Price'].values[0]
                
                st.write(f"**Unit Price:** ${unit_price:,.2f} ({calc_unit})")
                
                line_total = unit_price * qty
                st.metric("Line Item Total", f"${line_total:,.2f}")
                
                if st.button("➕ Add to Master Quote", use_container_width=True):
                    desc_parts = [str(selected_opt1)]
                    if selected_opt2 != "N/A": desc_parts.append(str(selected_opt2))
                    if selected_opt3 != "N/A": desc_parts.append(str(selected_opt3))
                    item_desc = " - ".join(desc_parts)
                    
                    if item_desc == "N/A" or item_desc == "":
                        item_desc = selected_category
                    
                    st.session_state.quote_items.append({
                        "Service": "Roofing",
                        "Item": item_desc,
                        "Qty": qty,
                        "Unit Price": f"${unit_price:,.2f}",
                        "Total": line_total
                    })
                    st.success(f"Added {item_desc} to quote!")
            else:
                st.warning("Pricing details not found for this measurement tier. Check Min/Max settings.")
        else:
            st.warning("Pricing details not found for this combination.")

# --- OTHER TABS ---
with tab_side: st.info("Siding module coming soon...")
with tab_gut: st.info("Gutters module coming soon...")
with tab_win: st.info("Windows module coming soon...")
with tab_ins: st.info("Insulation module coming soon...")
with tab_srv: st.info("Service module coming soon...")

# --- 6. THE MASTER QUOTE ---
st.divider()
st.header("🛒 Current Master Quote")

if len(st.session_state.quote_items) > 0:
    cart_df = pd.DataFrame(st.session_state.quote_items)
    st.dataframe(cart_df, hide_index=True, use_container_width=True)
    
    grand_total = cart_df['Total'].sum()
    st.subheader(f"Grand Total: ${grand_total:,.2f}")
    
    if st.button("🗑️ Clear Quote"):
        st.session_state.quote_items = []
        st.rerun()
else:
    st.caption("Your quote is currently empty. Add items from the tabs above.")