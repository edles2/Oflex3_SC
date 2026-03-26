"""
Page 3 — Transport & Logistics
Logistics network, transport parameters and delivery planning.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import database as db
from utils.calculations import estimate_delivery_days, parse_date, fmt_date
from datetime import datetime, timedelta

st.set_page_config(page_title="Transport & Logistics — Oflex3", layout="wide", page_icon="🚛")
if "db_ready" not in st.session_state:
    db.init_db()
    st.session_state.db_ready = True

st.title("🚛 Transport & Logistics")

# ── Load data ─────────────────────────────────────────────────────────────────
params    = db.get_params()
states    = db.get_states()
models    = db.get_models()
colors    = db.get_colors()
msp       = db.get_model_state_params()
inventory = db.get_inventory()
dpw       = int(params.get("working_days_per_week", 5))

tabs = st.tabs(["🏭 Logistics Network", "🗺️ Transport Parameters", "📦 Delivery Planning"])


# ══════════════════════════════════════════════════════════════════
# TAB A — Logistics Network
# ══════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Logistics Centers")

    centers = db.get_logistics_centers()
    c_df = pd.DataFrame(centers) if centers else pd.DataFrame(
        columns=["id","name","country","city","capacity_m3","fixed_cost_eur"]
    )
    c_df.rename(columns={
        "name":"Center Name","country":"Country","city":"City",
        "capacity_m3":"Capacity (m³)","fixed_cost_eur":"Fixed Cost (€/month)"
    }, inplace=True)

    edited_c = st.data_editor(
        c_df[["id","Center Name","Country","City","Capacity (m³)","Fixed Cost (€/month)"]],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "id":                   st.column_config.NumberColumn("ID", disabled=True),
            "Center Name":          st.column_config.TextColumn("Center Name"),
            "Country":              st.column_config.TextColumn("Country"),
            "City":                 st.column_config.TextColumn("City"),
            "Capacity (m³)":        st.column_config.NumberColumn("Capacity (m³)", min_value=0.0, format="%.0f"),
            "Fixed Cost (€/month)": st.column_config.NumberColumn("Fixed Cost (€/month)", format="%.2f"),
        },
        key="lc_editor",
    )

    if st.button("💾 Save Logistics Centers", type="primary"):
        edited_ids = set()
        for _, row in edited_c.iterrows():
            if pd.isna(row.get("Center Name")) or row.get("Center Name","") == "":
                continue
            cid = int(row["id"]) if row.get("id") and not pd.isna(row.get("id")) else None
            rid = db.save_logistics_center(
                row["Center Name"], row.get("Country",""), row.get("City",""),
                float(row.get("Capacity (m³)",0) or 0),
                float(row.get("Fixed Cost (€/month)",0) or 0),
                cid,
            )
            if cid:
                edited_ids.add(cid)
        for c in centers:
            if c["id"] not in edited_ids:
                db.delete_logistics_center(c["id"])
        st.success("Logistics centers saved.")
        st.rerun()

    # Capacity visualization
    centers = db.get_logistics_centers()
    if centers:
        st.divider()
        st.markdown("**Center Capacity Overview**")
        fig = go.Figure(go.Bar(
            x=[c["name"] for c in centers],
            y=[c["capacity_m3"] for c in centers],
            marker_color="#3498db",
            text=[f"{c['capacity_m3']:.0f} m³" for c in centers],
            textposition="auto",
        ))
        fig.update_layout(title="Logistics Center Capacities", yaxis_title="m³", height=300, margin=dict(t=40))
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════
# TAB B — Transport Parameters
# ══════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Transport Routes")

    centers = db.get_logistics_centers()
    if not centers:
        st.info("Add at least one logistics center first.")
    else:
        routes = db.get_transport_routes()
        center_options = {c["id"]: c["name"] for c in centers}

        r_df = pd.DataFrame(routes) if routes else pd.DataFrame(columns=[
            "id","center_id","destination","transport_time_days","shared_truck",
            "truck_capacity_m3","cost_per_m3","departure_frequency_days","transport_mode"
        ])
        r_df.rename(columns={
            "center_id":               "Center",
            "destination":             "Destination",
            "transport_time_days":     "Transit (days)",
            "shared_truck":            "Shared Truck",
            "truck_capacity_m3":       "Truck Capacity (m³)",
            "cost_per_m3":             "Cost (€/m³)",
            "departure_frequency_days":"Frequency (days)",
            "transport_mode":          "Mode",
        }, inplace=True)
        if "Center" in r_df.columns and not r_df.empty:
            r_df["Center"] = r_df["Center"].map(center_options)

        edited_r = st.data_editor(
            r_df[["id","Center","Destination","Transit (days)","Shared Truck",
                  "Truck Capacity (m³)","Cost (€/m³)","Frequency (days)","Mode"]],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "id":                 st.column_config.NumberColumn("ID", disabled=True),
                "Center":             st.column_config.SelectboxColumn("Center", options=list(center_options.values())),
                "Destination":        st.column_config.TextColumn("Destination"),
                "Transit (days)":     st.column_config.NumberColumn("Transit (days)", min_value=0),
                "Shared Truck":       st.column_config.CheckboxColumn("Shared Truck"),
                "Truck Capacity (m³)":st.column_config.NumberColumn("Truck Capacity (m³)", format="%.0f"),
                "Cost (€/m³)":        st.column_config.NumberColumn("Cost (€/m³)", format="%.2f"),
                "Frequency (days)":   st.column_config.NumberColumn("Frequency (days)", min_value=1),
                "Mode":               st.column_config.SelectboxColumn("Mode", options=["truck","rail","sea","air","courier"]),
            },
            key="routes_editor",
        )

        if st.button("💾 Save Transport Routes", type="primary"):
            name_to_id = {v: k for k, v in center_options.items()}
            edited_ids = set()
            for _, row in edited_r.iterrows():
                if pd.isna(row.get("Destination")) or row.get("Destination","") == "":
                    continue
                rid_existing = int(row["id"]) if row.get("id") and not pd.isna(row.get("id")) else None
                cid = name_to_id.get(row.get("Center",""))
                if not cid:
                    continue
                rid = db.save_transport_route(
                    center_id=cid,
                    destination=row["Destination"],
                    transport_time_days=int(row.get("Transit (days)",0) or 0),
                    shared_truck=int(bool(row.get("Shared Truck"))),
                    truck_capacity_m3=float(row.get("Truck Capacity (m³)",0) or 0),
                    cost_per_m3=float(row.get("Cost (€/m³)",0) or 0),
                    departure_frequency_days=int(row.get("Frequency (days)",1) or 1),
                    transport_mode=row.get("Mode","truck"),
                    route_id=rid_existing,
                )
                if rid_existing:
                    edited_ids.add(rid_existing)
            for r in routes:
                if r["id"] not in edited_ids:
                    db.delete_transport_route(r["id"])
            st.success("Transport routes saved.")
            st.rerun()


# ══════════════════════════════════════════════════════════════════
# TAB C — Delivery Planning
# ══════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Delivery Planning")
    st.caption("Estimate total delivery time for a customer order: production leadtime + transport.")

    centers = db.get_logistics_centers()
    routes  = db.get_transport_routes()

    if not models or not colors:
        st.info("Configure models and colors first.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            sel_model  = st.selectbox("Chair Model", [m["name"] for m in models])
            sel_color  = st.selectbox("Color",       [c["name"] for c in colors])
            qty        = st.number_input("Quantity", min_value=1, value=50, step=1)
        with col2:
            dest       = st.text_input("Destination", placeholder="e.g. Germany")
            req_date   = st.date_input("Required delivery date")

        if st.button("🔍 Estimate Delivery", type="primary"):
            model  = next((m for m in models if m["name"] == sel_model), None)
            color  = next((c for c in colors if c["name"] == sel_color), None)

            if not model or not color:
                st.error("Invalid model or color selection.")
            else:
                # Production leadtime
                lt_days, state_name, avail = estimate_delivery_days(
                    model["id"], color["id"], qty, inventory, states, dpw
                )

                # Find matching transport route
                matching_routes = [r for r in routes
                                   if r["destination"].lower() == dest.lower()] if dest else []

                st.markdown("---")
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Production Leadtime", f"{lt_days:.0f} days",
                              help=f"From state: {state_name}")
                col_a.caption(f"Source: {state_name} | Available: {avail} units")

                if matching_routes:
                    best_route = min(matching_routes, key=lambda r: r["transport_time_days"])
                    total_days = lt_days + best_route["transport_time_days"]
                    est_delivery = datetime.now() + timedelta(days=int(total_days * 7 / dpw))

                    col_b.metric("Transport Time", f"{best_route['transport_time_days']} days",
                                  help=f"Via {best_route.get('center_name','')}")
                    col_c.metric("Total Delivery", f"{total_days:.0f} days",
                                  help=fmt_date(est_delivery))
                    col_c.caption(f"Est. delivery: **{fmt_date(est_delivery)}**")

                    # Partial load warning
                    vol_map = {(p["model_id"], p["state_id"]): p["volume_coeff"] for p in msp}
                    s_ready = next((s for s in states if s["order_index"] == 6), None)
                    if s_ready:
                        vol = vol_map.get((model["id"], s_ready["id"]), 0.15)
                        order_vol = qty * vol
                        truck_cap = best_route["truck_capacity_m3"]
                        if best_route["shared_truck"] and truck_cap > 0:
                            fill_pct = order_vol / truck_cap * 100
                            if fill_pct < 80:
                                st.warning(f"⚠️ Partial truck load: order fills {fill_pct:.0f}% of {truck_cap:.0f} m³ truck. "
                                           f"Consider consolidating with other orders.")
                            else:
                                st.success(f"✅ Good truck utilization: {fill_pct:.0f}% of {truck_cap:.0f} m³")

                    # Risk check
                    req_dt = datetime.combine(req_date, datetime.min.time())
                    if est_delivery > req_dt:
                        days_late = (est_delivery - req_dt).days
                        st.error(f"❌ Cannot meet deadline — estimated {days_late} days late.")
                    else:
                        st.success(f"✅ Can meet deadline with {(req_dt - est_delivery).days} days buffer.")

                    # Route summary table
                    st.markdown("**Available Routes**")
                    route_rows = []
                    for r in matching_routes:
                        route_rows.append({
                            "Center":           r.get("center_name",""),
                            "Transit (days)":   r["transport_time_days"],
                            "Mode":             r["transport_mode"],
                            "Truck Cap. (m³)":  r["truck_capacity_m3"],
                            "Cost (€/m³)":      r["cost_per_m3"],
                            "Frequency (days)": r["departure_frequency_days"],
                        })
                    st.dataframe(pd.DataFrame(route_rows), use_container_width=True, hide_index=True)

                else:
                    col_b.metric("Transport Time", "N/A", help="No route found")
                    col_c.metric("Total Delivery", f"≥{lt_days:.0f} days")
                    if dest:
                        st.warning(f"No transport route configured for destination: **{dest}**. "
                                   f"Add routes in the Transport Parameters tab.")
                    else:
                        st.info("Enter a destination to include transport time.")
