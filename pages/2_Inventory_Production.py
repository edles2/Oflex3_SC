"""
Page 2 — Inventory & Production Model
Real-time snapshot, scenario planning and storage optimization.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import database as db
from utils.calculations import (
    build_scenario, calc_storage_forecast, calc_daily_demand, today_str
)
from utils.optimization import optimize_storage_allocation, tradeoff_curve, build_launch_plan

st.title("Inventory & Production Model")

# ── Load data ─────────────────────────────────────────────────────────────────
params     = db.get_params()
states     = db.get_states()
models     = db.get_models()
colors     = db.get_colors()
msp        = db.get_model_state_params()
inventory  = db.get_inventory()
demand_raw = db.get_demand_settings()
orders_raw = db.get_orders()
order_lines= db.get_order_lines()

total_storage = float(params.get("total_storage_m3", 500))
dpw           = int(params.get("working_days_per_week", 5))
s_cons        = float(params.get("safety_conservative", 1.5))
s_std         = float(params.get("safety_standard", 1.0))
s_lean        = float(params.get("safety_lean", 0.6))

if not models:
    st.info("No chair models configured yet. Go to **Parameters** to add models.")
    st.stop()

tabs = st.tabs(["Real-Time Snapshot", "Scenario Planning", "Optimization Engine"])


# ══════════════════════════════════════════════════════════════════
# TAB A — Real-Time Snapshot
# ══════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Real-Time Inventory Snapshot")
    st.caption("Enter current stock quantities. Color is required for states Painted and beyond.")

    state_map = {s["id"]: s for s in states}
    model_map = {m["id"]: m["name"] for m in models}
    color_map = {c["id"]: c["name"] for c in colors}

    # Build editable inventory table
    # Pre-color states (order_index <= 3): no color
    # Post-painting states (order_index >= 4): requires color
    inv_map = {}
    for item in inventory:
        key = (item["model_id"], item["state_id"], item.get("color_id"))
        inv_map[key] = item["quantity"]

    rows = []
    for m in models:
        for s in states:
            if not s.get("can_hold_stock", 1):
                continue
            if s["order_index"] < 4:
                # no color
                qty = inv_map.get((m["id"], s["id"], None), 0)
                rows.append({
                    "model_id":  m["id"], "state_id": s["id"], "color_id": None,
                    "Model":     m["name"], "State": s["name"], "Color": "—",
                    "Quantity":  qty,
                })
            else:
                for c in colors:
                    qty = inv_map.get((m["id"], s["id"], c["id"]), 0)
                    rows.append({
                        "model_id":  m["id"], "state_id": s["id"], "color_id": c["id"],
                        "Model":     m["name"], "State": s["name"], "Color": c["name"],
                        "Quantity":  qty,
                    })

    df_inv = pd.DataFrame(rows)
    vol_map = {(p["model_id"], p["state_id"]): p["volume_coeff"] for p in msp}
    df_inv["Vol. Coeff"] = df_inv.apply(lambda r: vol_map.get((r["model_id"], r["state_id"]), 0.0), axis=1)
    df_inv["Storage (m³)"] = (df_inv["Quantity"] * df_inv["Vol. Coeff"]).round(3)

    # Alerts before editor
    total_used = df_inv["Storage (m³)"].sum()
    col_a, col_b = st.columns(2)
    col_a.metric("Storage Used", f"{total_used:.1f} m³", delta=f"{total_used - total_storage:.1f} m³ vs capacity")
    col_b.metric("Storage Capacity", f"{total_storage:.0f} m³")
    if total_used > total_storage:
        st.error(f"Storage over capacity by {total_used - total_storage:.1f} m³!")

    # KANBAN alerts
    kb_map = {(p["model_id"], p["state_id"]): p["kanban_threshold"] for p in msp}
    for _, row in df_inv.iterrows():
        kb = kb_map.get((row["model_id"], row["state_id"]))
        if kb and row["Quantity"] < kb:
            st.warning(f"KANBAN alert: **{row['Model']}** at **{row['State']}** — qty {int(row['Quantity'])} below threshold {kb}")

    display_cols = ["Model","State","Color","Quantity","Storage (m³)"]
    edited_inv = st.data_editor(
        df_inv[display_cols + ["model_id","state_id","color_id"]],
        column_config={
            "Model":       st.column_config.TextColumn(disabled=True),
            "State":       st.column_config.TextColumn(disabled=True),
            "Color":       st.column_config.TextColumn(disabled=True),
            "Quantity":    st.column_config.NumberColumn("Quantity", min_value=0, step=1),
            "Storage (m³)":st.column_config.NumberColumn(disabled=True, format="%.3f"),
            "model_id":    None, "state_id": None, "color_id": None,
        },
        use_container_width=True,
        key="inv_editor",
    )

    if st.button("Save Inventory Snapshot", type="primary"):
        db.clear_inventory()
        for _, row in edited_inv.iterrows():
            db.upsert_inventory(
                int(row["model_id"]), int(row["state_id"]),
                int(row["color_id"]) if row["color_id"] and not pd.isna(row["color_id"]) else None,
                int(row["Quantity"]),
            )
        st.success("Inventory snapshot saved.")
        st.rerun()

    st.divider()
    st.markdown("**Demand Settings (weekly units per model × color)**")
    demand_rows = []
    for m in models:
        for c in colors:
            d = next((x for x in demand_raw if x["model_id"] == m["id"] and x["color_id"] == c["id"]), None)
            demand_rows.append({
                "model_id": m["id"], "color_id": c["id"],
                "Model": m["name"], "Color": c["name"],
                "Weekly Demand": d["weekly_demand"] if d else 0.0,
            })
    dem_df = pd.DataFrame(demand_rows)
    edited_dem = st.data_editor(
        dem_df[["Model","Color","Weekly Demand","model_id","color_id"]],
        column_config={
            "Model": st.column_config.TextColumn(disabled=True),
            "Color": st.column_config.TextColumn(disabled=True),
            "Weekly Demand": st.column_config.NumberColumn("Weekly Demand (units/week)", min_value=0.0, format="%.1f"),
            "model_id": None, "color_id": None,
        },
        use_container_width=True,
        key="dem_editor",
    )
    if st.button("Save Demand Settings", type="primary"):
        for _, row in edited_dem.iterrows():
            db.upsert_demand(int(row["model_id"]), int(row["color_id"]), float(row["Weekly Demand"]))
        st.success("Demand settings saved.")
        st.rerun()


# ══════════════════════════════════════════════════════════════════
# TAB B — Scenario Planning
# ══════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Scenario Planning")

    scenario_cfg = {
        "Conservative": s_cons,
        "Standard":     s_std,
        "Lean":         s_lean,
    }

    sel_scenario = st.radio("Scenario", list(scenario_cfg.keys()), horizontal=True, index=1)
    safety = scenario_cfg[sel_scenario]
    st.caption(f"**{sel_scenario}** — safety multiplier: **{safety}×**")

    # Re-load demand (might have changed)
    demand_raw = db.get_demand_settings()
    inventory  = db.get_inventory()

    scenario = build_scenario(
        models, states, msp, inventory, demand_raw,
        safety_mult=safety, days_per_week=dpw, total_storage_m3=total_storage,
    )


    # Storage summary
    col1, col2, col3 = st.columns(3)
    col1.metric("Target Storage",   f"{scenario['total_storage_needed_m3']:.1f} m³")
    col2.metric("Current Storage",  f"{scenario['total_storage_used_m3']:.1f} m³")
    col3.metric("Capacity",         f"{total_storage:.0f} m³",
                delta=f"{scenario['total_storage_needed_m3'] - total_storage:.1f} m³" if scenario["over_capacity"] else "OK")
    if scenario["over_capacity"]:
        st.warning("Target stock exceeds storage capacity. Consider the Optimization Engine tab.")

    # Scenario table
    s_df = pd.DataFrame(scenario["rows"])
    if not s_df.empty:
        s_df_display = s_df[[
            "model_name","state_name","leadtime_days","weekly_demand",
            "target_stock","current_stock","production_needed","health",
            "storage_target_m3","storage_current_m3"
        ]].rename(columns={
            "model_name":       "Model",
            "state_name":       "State",
            "leadtime_days":    "Lead Time (days)",
            "weekly_demand":    "Weekly Demand",
            "target_stock":     "Target Stock",
            "current_stock":    "Current Stock",
            "production_needed":"To Launch",
            "health":           "Health",
            "storage_target_m3":"Target Storage (m³)",
            "storage_current_m3":"Current Storage (m³)",
        })
        health_colors = {"ok":"OK","low":"Low","critical":"Critical","excess":"Excess"}
        s_df_display["Health"] = s_df_display["Health"].map(lambda x: health_colors.get(x, x))
        st.dataframe(s_df_display, use_container_width=True, hide_index=True)

    # Storage forecast chart
    st.markdown("**12-Week Storage Forecast**")
    forecast = calc_storage_forecast(scenario["rows"], weeks=12, days_per_week=dpw)
    f_df = pd.DataFrame(forecast)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=f_df["week"], y=f_df["storage_m3"],
                             mode="lines+markers", name="Projected Storage",
                             line=dict(color="#1f77b4", width=2)))
    fig.add_hline(y=total_storage, line_dash="dash", line_color="red",
                  annotation_text=f"Capacity ({total_storage} m³)")
    fig.update_layout(title="Storage Utilization Forecast",
                      xaxis_title="Week", yaxis_title="Storage (m³)",
                      height=350, margin=dict(t=40))
    st.plotly_chart(fig, use_container_width=True)

    # Production actions needed
    actions = [r for r in scenario["rows"] if r["production_needed"] > 0]
    if actions:
        st.markdown("**Recommended Production Launches**")
        act_df = pd.DataFrame(actions)[["model_name","state_name","current_stock","target_stock","production_needed","moq"]].rename(columns={
            "model_name":"Model","state_name":"State","current_stock":"Current","target_stock":"Target","production_needed":"To Launch","moq":"MOQ"
        })
        st.dataframe(act_df, use_container_width=True, hide_index=True)

    # Delivery capacity per model per color
    st.markdown("**Estimated Weekly Delivery Capacity (units/week)**")
    cap_rows = []
    for m in models:
        for c in colors:
            weekly = next((d["weekly_demand"] for d in demand_raw
                           if d["model_id"]==m["id"] and d["color_id"]==c["id"]), 0)
            cap_rows.append({"Model": m["name"], "Color": c["name"], "Capacity (units/week)": weekly})
    st.dataframe(pd.DataFrame(cap_rows), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════
# TAB C — Optimization Engine
# ══════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Storage Allocation Optimization Engine")
    st.caption(
        "LP-based allocation that maximises stock held close to delivery, "
        "subject to total storage capacity constraint."
    )

    sel_opt_scenario = st.radio("Base scenario for optimization",
                                list(scenario_cfg.keys()), horizontal=True,
                                index=1, key="opt_scenario")
    opt_safety = scenario_cfg[sel_opt_scenario]

    demand_raw = db.get_demand_settings()
    inventory  = db.get_inventory()

    opt_scenario = build_scenario(
        models, states, msp, inventory, demand_raw,
        safety_mult=opt_safety, days_per_week=dpw, total_storage_m3=total_storage,
    )
    orders_pending = [o for o in orders_raw if o["status"] == "pending"]

    if not opt_scenario["rows"]:
        st.info("Configure models, states and demand first.")
    else:
        with st.spinner("Running LP optimization…"):
            opt_result = optimize_storage_allocation(
                opt_scenario["rows"], total_storage, orders_pending, order_lines
            )

        if opt_result["status"] == "ok":
            col1, col2, col3 = st.columns(3)
            col1.metric("Optimized Storage Used", f"{opt_result['storage_used']:.1f} m³")
            col2.metric("Capacity",               f"{total_storage:.0f} m³")
            col3.metric("Utilization",            f"{opt_result['storage_used']/total_storage*100:.1f}%")

            # Results table
            res_rows = [{
                "Model":         r["model_name"],
                "State":         r["state_name"],
                "Lead Time (days)": r["leadtime_days"],
                "Target Stock":  r["target_stock"],
                "Recommended":   r["recommended_stock"],
                "Scale Factor":  f"{r['scale_factor']:.0%}",
                "Storage (m³)":  r["storage_m3"],
            } for r in opt_result["rows"]]
            st.dataframe(pd.DataFrame(res_rows), use_container_width=True, hide_index=True)

            # Launch plan
            launch = build_launch_plan(opt_result["rows"], inventory, msp)
            if launch:
                st.markdown("**Recommended Production Launch Plan**")
                lp_df = pd.DataFrame(launch).rename(columns={
                    "model_name":"Model","state_name":"State",
                    "current":"Current Stock","recommended":"Recommended",
                    "to_launch":"To Launch","moq":"MOQ","leadtime_days":"Lead Time (days)"
                })
                st.dataframe(lp_df, use_container_width=True, hide_index=True)

        # Tradeoff curve
        st.markdown("**Storage vs. Delivery Time Tradeoff**")
        with st.spinner("Computing tradeoff curve…"):
            curve = tradeoff_curve(opt_scenario["rows"], total_storage, n_points=15)

        if curve:
            c_df = pd.DataFrame(curve)
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=c_df["storage_m3"], y=c_df["avg_delivery_days"],
                mode="lines+markers", name="Avg Delivery Time",
                line=dict(color="#e74c3c", width=2),
            ))
            fig2.add_vline(x=total_storage, line_dash="dash", line_color="green",
                           annotation_text=f"Current capacity ({total_storage} m³)")
            fig2.update_layout(
                title="Storage Budget vs. Achievable Delivery Time",
                xaxis_title="Storage Budget (m³)",
                yaxis_title="Weighted Avg. Delivery Time (days)",
                height=350, margin=dict(t=40),
            )
            st.plotly_chart(fig2, use_container_width=True)
