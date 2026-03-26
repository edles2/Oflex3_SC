"""
Page 5 — Dashboard
KPIs, stock health heatmap, upcoming actions and order deadlines.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import database as db
from utils.calculations import (
    build_scenario, calc_storage_used, calc_order_feasibility, parse_date
)
from datetime import datetime, timedelta

st.set_page_config(page_title="Dashboard — Oflex3", layout="wide", page_icon="📊")
if "db_ready" not in st.session_state:
    db.init_db()
    st.session_state.db_ready = True

st.title("📊 Dashboard — Overview")

# ── Load data ─────────────────────────────────────────────────────────────────
params      = db.get_params()
states      = db.get_states()
models      = db.get_models()
colors      = db.get_colors()
msp         = db.get_model_state_params()
inventory   = db.get_inventory()
demand_raw  = db.get_demand_settings()
orders      = db.get_orders()
all_lines   = db.get_order_lines()

total_storage = float(params.get("total_storage_m3", 500))
dpw           = int(params.get("working_days_per_week", 5))
s_cons        = float(params.get("safety_conservative", 1.5))
s_std         = float(params.get("safety_standard",  1.0))
s_lean        = float(params.get("safety_lean",  0.6))

if not models:
    st.info("👆 No data configured yet. Start with the **Parameters** page.")
    st.stop()

# ── Scenario toggle ───────────────────────────────────────────────────────────
scenario_cfg = {"Conservative": s_cons, "Standard": s_std, "Lean": s_lean}
sel = st.radio("Scenario", list(scenario_cfg.keys()), horizontal=True, index=1)
safety = scenario_cfg[sel]

scenario = build_scenario(
    models, states, msp, inventory, demand_raw,
    safety_mult=safety, days_per_week=dpw, total_storage_m3=total_storage,
)

pending_orders = [o for o in orders if o["status"] == "pending"]
feasibility    = calc_order_feasibility(pending_orders, all_lines, inventory, states, dpw) if pending_orders else []
at_risk        = [f for f in feasibility if f.get("at_risk")]

# ── KPI Row ───────────────────────────────────────────────────────────────────
st.subheader("Key Performance Indicators")
k1, k2, k3, k4, k5, k6 = st.columns(6)

storage_pct = scenario["total_storage_used_m3"] / total_storage * 100 if total_storage > 0 else 0
k1.metric("Storage Used",      f"{scenario['total_storage_used_m3']:.1f} m³",
           delta=f"{storage_pct:.0f}%")
k2.metric("Storage Capacity",  f"{total_storage:.0f} m³")
k3.metric("Pending Orders",    len(pending_orders))
k4.metric("Orders at Risk",    len(at_risk),
           delta=f"{len(at_risk)} need attention" if at_risk else "All on track",
           delta_color="inverse")
k5.metric("Total Models",      len(models))
k6.metric("Total Colors",      len(colors))

# Average delivery time by model
if feasibility:
    avg_lt = sum(f["max_lt_days"] for f in feasibility) / len(feasibility)
    st.caption(f"Average delivery lead time across pending orders: **{avg_lt:.0f} days**")

st.divider()

# ── Stock Health Heatmap ──────────────────────────────────────────────────────
st.subheader("Stock Health Heatmap (Model × State)")
st.caption("🟢 OK  🟡 Low  🔴 Critical (below KANBAN)  🟠 Excess")

health_score = {"ok": 2, "low": 1, "critical": 0, "excess": 3}
color_map_h  = {0: "#e74c3c", 1: "#f39c12", 2: "#2ecc71", 3: "#e67e22"}

heatmap_rows = scenario["rows"]
if heatmap_rows:
    df_h = pd.DataFrame(heatmap_rows)
    pivot = df_h.pivot_table(
        index="model_name", columns="state_name",
        values="health", aggfunc="first"
    )
    # Order columns by state order
    state_order = {s["name"]: s["order_index"] for s in states}
    pivot = pivot.reindex(columns=sorted(pivot.columns, key=lambda x: state_order.get(x, 99)))

    # Build numeric heatmap
    numeric_pivot = pivot.applymap(lambda x: health_score.get(x, -1) if pd.notna(x) else -1)
    z_text = pivot.applymap(lambda x: {"ok":"OK","low":"Low","critical":"Critical","excess":"Excess"}.get(x,"—") if pd.notna(x) else "—")

    fig_heat = go.Figure(go.Heatmap(
        z=numeric_pivot.values,
        x=list(numeric_pivot.columns),
        y=list(numeric_pivot.index),
        text=z_text.values,
        texttemplate="%{text}",
        colorscale=[[0,"#e74c3c"],[0.33,"#f39c12"],[0.66,"#2ecc71"],[1.0,"#e67e22"]],
        zmin=0, zmax=3,
        showscale=False,
        hovertemplate="Model: %{y}<br>State: %{x}<br>Health: %{text}<extra></extra>",
    ))
    fig_heat.update_layout(
        title=f"Stock Health — {sel} Scenario",
        height=max(200, len(models) * 60 + 80),
        margin=dict(t=50, l=100),
        xaxis=dict(side="bottom"),
    )
    st.plotly_chart(fig_heat, use_container_width=True)

st.divider()

# ── Two-column layout: Actions + Deadlines ────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("⚡ Upcoming Production Actions")
    st.caption("Sorted by urgency (shortest leadtime first)")
    actions = sorted(
        [r for r in scenario["rows"] if r["production_needed"] > 0],
        key=lambda r: r["leadtime_days"],
    )
    if not actions:
        st.success("✅ No immediate production launches required.")
    else:
        for a in actions[:10]:
            urgency = "🔴" if a["health"] == "critical" else "🟡"
            with st.container():
                st.markdown(
                    f"{urgency} **{a['model_name']}** @ {a['state_name']}  \n"
                    f"Launch **{int(a['production_needed'])} units** "
                    f"(current: {a['current_stock']}, target: {a['target_stock']:.0f})"
                )
        if len(actions) > 10:
            st.caption(f"… and {len(actions) - 10} more. See Inventory & Production page.")

with col_right:
    st.subheader("📅 Upcoming Order Deadlines (next 4 weeks)")
    today = datetime.now()
    horizon = today + timedelta(weeks=4)

    upcoming = []
    for order in orders:
        dl = parse_date(order["deadline"])
        if dl and dl <= horizon:
            feas = next((f for f in feasibility if f["id"] == order["id"]), None)
            upcoming.append({
                "Ref":       order["order_ref"],
                "Customer":  order["customer_name"],
                "Deadline":  order["deadline"],
                "Priority":  order["priority"],
                "Status":    order["status"],
                "At Risk":   feas.get("at_risk", False) if feas else False,
            })

    upcoming.sort(key=lambda x: (parse_date(x["Deadline"]) or datetime.max, x["Priority"]))

    if not upcoming:
        st.info("No order deadlines in the next 4 weeks.")
    else:
        for u in upcoming:
            badge = "🔴" if u["At Risk"] else "🟢"
            st.markdown(f"{badge} **{u['Ref']}** — {u['Customer']}  \nDeadline: **{u['Deadline']}** | Priority: {u['Priority']} | Status: {u['Status']}")

st.divider()

# ── Storage utilization bar ───────────────────────────────────────────────────
st.subheader("Storage Utilization by Model & State")
if heatmap_rows:
    df_stor = pd.DataFrame(heatmap_rows)
    df_stor = df_stor[df_stor["storage_current_m3"] > 0]
    if not df_stor.empty:
        fig_stor = px.bar(
            df_stor,
            x="state_name",
            y="storage_current_m3",
            color="model_name",
            barmode="stack",
            labels={"state_name":"State","storage_current_m3":"Storage (m³)","model_name":"Model"},
            title="Current Storage Distribution",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig_stor.add_hline(
            y=total_storage,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Capacity ({total_storage} m³)",
        )
        fig_stor.update_layout(height=350, margin=dict(t=50))
        st.plotly_chart(fig_stor, use_container_width=True)
    else:
        st.info("No inventory data. Enter current stock on the Inventory & Production page.")

# ── Order status pie ──────────────────────────────────────────────────────────
if orders:
    st.subheader("Order Status Breakdown")
    status_counts = pd.Series([o["status"] for o in orders]).value_counts().reset_index()
    status_counts.columns = ["Status","Count"]
    fig_pie = px.pie(status_counts, values="Count", names="Status",
                     color_discrete_sequence=px.colors.qualitative.Pastel,
                     title="Orders by Status")
    fig_pie.update_layout(height=300, margin=dict(t=50))
    st.plotly_chart(fig_pie, use_container_width=True)
