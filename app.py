"""
Oflex3 Supply Chain — Main entry point.
Run with:  streamlit run app.py
"""
import streamlit as st
import database as db

st.set_page_config(
    page_title="Oflex3 Supply Chain",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Initialize DB once per session ────────────────────────────────────────────
if "db_ready" not in st.session_state:
    db.init_db()
    st.session_state.db_ready = True

# ── Home page ─────────────────────────────────────────────────────────────────
st.title("🏭 Oflex3 — Supply Chain Planning")
st.markdown("**Production planning & inventory optimization for metal chair manufacturing.**")
st.divider()

col1, col2, col3 = st.columns(3)
with col1:
    st.info("**⚙️ Parameters**\nManage production states, chair models, colors and global settings.")
with col2:
    st.info("**📦 Inventory & Production**\nReal-time snapshot, scenario planning and storage optimization.")
with col3:
    st.info("**🚛 Transport & Logistics**\nLogistics network, transport routes and delivery planning.")

col4, col5 = st.columns(2)
with col4:
    st.info("**📋 Orders**\nManage customer orders, check feasibility and see impact on production.")
with col5:
    st.info("**📊 Dashboard**\nKPIs overview, stock health heatmap and upcoming deadlines.")

st.divider()
st.caption("Use the sidebar to navigate between pages. All data is persisted locally in `oflex3.db`.")

# Quick health check
try:
    params = db.get_params()
    models = db.get_models()
    orders = db.get_orders()
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Storage capacity", f"{params.get('total_storage_m3','—')} m³")
    col_b.metric("Chair models",     len(models))
    col_c.metric("Pending orders",   sum(1 for o in orders if o["status"] == "pending"))
    col_d.metric("Total orders",     len(orders))
except Exception as e:
    st.warning(f"Could not load summary: {e}")
