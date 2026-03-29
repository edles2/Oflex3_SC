"""
Oflex3 Supply Chain — entry point.
Run with: streamlit run app.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import database as db

st.set_page_config(page_title="Oflex3 Supply Chain", layout="wide")

if "db_ready" not in st.session_state:
    db.init_db()
    st.session_state.db_ready = True

pages = [
    st.Page("pages/dashboard.py",              title="Dashboard",              default=True),
    st.Page("pages/1_Orders.py",               title="Orders"),
    st.Page("pages/2_Inventory_Production.py", title="Inventory & Production"),
    st.Page("pages/3_Transport_Logistics.py",  title="Transport & Logistics"),
    st.Page("pages/4_Parameters.py",           title="Parameters"),
    st.Page("pages/5_Calculation_Details.py",  title="Calculation Details"),
]

pg = st.navigation(pages)
pg.run()
