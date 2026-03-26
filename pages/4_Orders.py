"""
Page 4 — Orders
Manage customer orders, check feasibility and see production impact.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import database as db
from utils.calculations import (
    calc_order_feasibility, build_scenario, today_str, parse_date, fmt_date
)
from datetime import datetime, timedelta

st.set_page_config(page_title="Orders — Oflex3", layout="wide", page_icon="📋")
if "db_ready" not in st.session_state:
    db.init_db()
    st.session_state.db_ready = True

st.title("📋 Orders")

# ── Load data ─────────────────────────────────────────────────────────────────
params      = db.get_params()
states      = db.get_states()
models      = db.get_models()
colors      = db.get_colors()
msp         = db.get_model_state_params()
inventory   = db.get_inventory()
demand_raw  = db.get_demand_settings()
dpw         = int(params.get("working_days_per_week", 5))

model_map  = {m["id"]: m["name"] for m in models}
color_map  = {c["id"]: c["name"] for c in colors}
model_opts = {m["name"]: m["id"] for m in models}
color_opts = {c["name"]: c["id"] for c in colors}

tabs = st.tabs(["📋 Order List", "✅ Feasibility Check", "📈 Production Impact"])


# ══════════════════════════════════════════════════════════════════
# TAB A — Order List
# ══════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Customer Orders")
    orders = db.get_orders()

    # ── Add / Edit order form ─────────────────────────────────────
    with st.expander("➕ Add / Edit Order", expanded=not orders):
        edit_mode = st.radio("Action", ["New Order", "Edit Existing"], horizontal=True)
        editing_order = None

        if edit_mode == "Edit Existing" and orders:
            sel_ref = st.selectbox("Select order to edit", [o["order_ref"] for o in orders])
            editing_order = next((o for o in orders if o["order_ref"] == sel_ref), None)

        with st.form("order_form"):
            col1, col2 = st.columns(2)
            with col1:
                order_ref     = st.text_input("Order Reference",  value=editing_order["order_ref"] if editing_order else f"ORD-{len(orders)+1:03d}")
                customer_name = st.text_input("Customer Name",    value=editing_order["customer_name"] if editing_order else "")
                destination   = st.text_input("Destination",      value=editing_order["destination"] if editing_order else "")
                priority      = st.number_input("Priority (1=highest)", min_value=1, max_value=10,
                                                value=int(editing_order["priority"]) if editing_order else 3)
            with col2:
                try:
                    od_default = datetime.strptime(editing_order["order_date"], "%d/%m/%Y").date() if editing_order else datetime.now().date()
                except Exception:
                    od_default = datetime.now().date()
                try:
                    dl_default = datetime.strptime(editing_order["deadline"], "%d/%m/%Y").date() if editing_order else (datetime.now() + timedelta(weeks=4)).date()
                except Exception:
                    dl_default = (datetime.now() + timedelta(weeks=4)).date()

                order_date = st.date_input("Order Date",      value=od_default)
                deadline   = st.date_input("Deadline",        value=dl_default)
                status     = st.selectbox("Status", ["pending","in production","shipped","delivered"],
                                          index=["pending","in production","shipped","delivered"].index(
                                              editing_order["status"] if editing_order else "pending"))
                notes      = st.text_area("Notes", value=editing_order["notes"] if editing_order else "")

            st.markdown("**Line Items**")
            st.caption("Add order lines below:")

            existing_lines = db.get_order_lines(editing_order["id"]) if editing_order else []
            n_lines = st.number_input("Number of line items", min_value=1, max_value=10,
                                       value=max(1, len(existing_lines)))

            line_data = []
            for i in range(int(n_lines)):
                lc1, lc2, lc3 = st.columns(3)
                ex_line = existing_lines[i] if i < len(existing_lines) else None
                with lc1:
                    sel_m = st.selectbox(f"Model (line {i+1})", list(model_opts.keys()),
                                          index=list(model_opts.values()).index(ex_line["model_id"])
                                          if ex_line and ex_line["model_id"] in model_opts.values() else 0,
                                          key=f"lm_{i}")
                with lc2:
                    sel_c = st.selectbox(f"Color (line {i+1})", list(color_opts.keys()),
                                          index=list(color_opts.values()).index(ex_line["color_id"])
                                          if ex_line and ex_line["color_id"] in color_opts.values() else 0,
                                          key=f"lc_{i}")
                with lc3:
                    qty  = st.number_input(f"Qty (line {i+1})", min_value=1,
                                            value=int(ex_line["quantity"]) if ex_line else 10,
                                            key=f"lq_{i}")
                line_data.append({"model_id": model_opts[sel_m], "color_id": color_opts[sel_c], "quantity": qty})

            submitted = st.form_submit_button("💾 Save Order", type="primary")
            if submitted:
                if not models or not colors:
                    st.error("Configure models and colors in Parameters first.")
                else:
                    oid = db.save_order(
                        order_ref=order_ref,
                        customer_name=customer_name,
                        order_date=fmt_date(datetime.combine(order_date, datetime.min.time())),
                        deadline=fmt_date(datetime.combine(deadline, datetime.min.time())),
                        priority=priority,
                        status=status,
                        destination=destination,
                        notes=notes,
                        order_id=editing_order["id"] if editing_order else None,
                    )
                    db.save_order_lines(oid, line_data)
                    st.success(f"Order {order_ref} saved.")
                    st.rerun()

    st.divider()

    # ── Order table ───────────────────────────────────────────────
    orders = db.get_orders()
    if not orders:
        st.info("No orders yet. Use the form above to add your first order.")
    else:
        all_lines = db.get_order_lines()
        for order in orders:
            oid = order["id"]
            lines = [l for l in all_lines if l["order_id"] == oid]
            lines_str = "; ".join(f"{l['quantity']}× {l.get('model_name','')} {l.get('color_name','')}" for l in lines)
            order["Line Items"] = lines_str

        o_df = pd.DataFrame(orders)[[
            "order_ref","customer_name","order_date","deadline",
            "priority","status","destination","Line Items","notes"
        ]].rename(columns={
            "order_ref":     "Ref",
            "customer_name": "Customer",
            "order_date":    "Order Date",
            "deadline":      "Deadline",
            "priority":      "Priority",
            "status":        "Status",
            "destination":   "Destination",
            "notes":         "Notes",
        })
        st.dataframe(o_df, use_container_width=True, hide_index=True)

        # Delete
        st.markdown("**Delete an Order**")
        del_ref = st.selectbox("Select order to delete", ["—"] + [o["order_ref"] for o in orders])
        if del_ref != "—":
            if st.button(f"🗑️ Delete {del_ref}", type="secondary"):
                order_to_del = next((o for o in orders if o["order_ref"] == del_ref), None)
                if order_to_del:
                    db.delete_order(order_to_del["id"])
                    st.success(f"Order {del_ref} deleted.")
                    st.rerun()


# ══════════════════════════════════════════════════════════════════
# TAB B — Feasibility Check
# ══════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Order Feasibility Check")

    params    = db.get_params()
    s_cons    = float(params.get("safety_conservative", 1.5))
    s_std     = float(params.get("safety_standard", 1.0))
    s_lean    = float(params.get("safety_lean", 0.6))

    scenario_labels = {"Conservative": s_cons, "Standard": s_std, "Lean": s_lean}
    sel_scenario    = st.radio("Scenario", list(scenario_labels.keys()), horizontal=True, index=1)
    safety          = scenario_labels[sel_scenario]

    orders      = db.get_orders()
    all_lines   = db.get_order_lines()
    pending     = [o for o in orders if o["status"] == "pending"]

    if not pending:
        st.info("No pending orders.")
    else:
        feasibility = calc_order_feasibility(pending, all_lines, inventory, states, dpw)

        for f in sorted(feasibility, key=lambda x: x["priority"]):
            deadline = parse_date(f["deadline"])
            at_risk  = f.get("at_risk", False)
            from_stock = f.get("from_stock", False)

            badge = "🔴" if at_risk else ("🟢" if from_stock else "🟡")
            status_label = ("From stock" if from_stock else
                            f"Needs production (est. {f['max_lt_days']:.0f} days)")

            with st.container():
                st.markdown(f"### {badge} {f['order_ref']} — {f['customer_name']}")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Deadline",      f["deadline"])
                c2.metric("Est. Delivery", f["est_delivery"])
                c3.metric("Lead Time",     f"{f['max_lt_days']:.0f} days")
                c4.metric("Status",        status_label)

                if at_risk:
                    st.error(f"⚠️ At risk: estimated delivery {f['est_delivery']} is after deadline {f['deadline']}")

                detail_df = pd.DataFrame(f["line_details"])
                if not detail_df.empty:
                    detail_df.rename(columns={
                        "model_name":"Model","color_name":"Color","qty":"Ordered",
                        "avail":"Available","lt_days":"Lead Time (days)",
                        "state_name":"Best Available State","from_stock":"In Stock?"
                    }, inplace=True)
                    detail_df["In Stock?"] = detail_df["In Stock?"].map({True:"✅",False:"❌"})
                    st.dataframe(detail_df[["Model","Color","Ordered","Available","In Stock?",
                                            "Lead Time (days)","Best Available State"]],
                                 use_container_width=True, hide_index=True)
                st.divider()


# ══════════════════════════════════════════════════════════════════
# TAB C — Production Impact
# ══════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Order Impact on Production Plan")
    st.caption("How the order backlog modifies recommended production quantities.")

    params    = db.get_params()
    s_std     = float(params.get("safety_standard", 1.0))
    total_s   = float(params.get("total_storage_m3", 500))

    orders    = db.get_orders()
    all_lines = db.get_order_lines()
    pending   = [o for o in orders if o["status"] == "pending"]

    if not pending:
        st.info("No pending orders to impact.")
    else:
        # Standard scenario without orders
        base_scenario = build_scenario(
            models, states, msp, inventory, demand_raw,
            safety_mult=s_std, days_per_week=dpw, total_storage_m3=total_s,
        )

        # Compute order demand overlay
        order_demand: dict = {}  # (model_id, color_id) -> total qty
        for order in pending:
            lines = [l for l in all_lines if l["order_id"] == order["id"]]
            for l in lines:
                key = (l["model_id"], l["color_id"])
                order_demand[key] = order_demand.get(key, 0) + l["quantity"]

        st.markdown("**Pending Order Demand Summary**")
        od_rows = []
        for (mid, cid), qty in order_demand.items():
            od_rows.append({
                "Model":    model_map.get(mid,""),
                "Color":    color_map.get(cid,""),
                "Order Qty":qty,
            })
        if od_rows:
            st.dataframe(pd.DataFrame(od_rows), use_container_width=True, hide_index=True)

        # Production needed with orders included
        st.markdown("**Adjusted Production Plan (Standard Scenario + Orders)**")
        impact_rows = []
        inv_map = {}
        for item in inventory:
            key = (item["model_id"], item["state_id"])
            inv_map[key] = inv_map.get(key, 0) + item["quantity"]

        for row in base_scenario["rows"]:
            mid = row["model_id"]
            sid = row["state_id"]
            state = next((s for s in states if s["id"] == sid), {})

            # Only check finished states for order demand
            total_order_qty = 0
            if state.get("order_index", 0) >= 5:
                for (m2, c2), qty in order_demand.items():
                    if m2 == mid:
                        total_order_qty += qty

            adjusted_target = row["target_stock"] + total_order_qty
            adjusted_needed = max(0, adjusted_target - row["current_stock"])
            impact_rows.append({
                "Model":            row["model_name"],
                "State":            row["state_name"],
                "Base Target":      row["target_stock"],
                "Order Demand":     total_order_qty,
                "Adjusted Target":  round(adjusted_target, 1),
                "Current Stock":    row["current_stock"],
                "Adjusted Launch":  round(adjusted_needed, 1),
            })

        st.dataframe(pd.DataFrame(impact_rows), use_container_width=True, hide_index=True)

        # Conflict detection
        st.markdown("**Conflict Detection**")
        stock_map = {}
        for item in inventory:
            key = (item["model_id"], item.get("color_id"))
            stock_map[key] = stock_map.get(key, 0) + item["quantity"]

        conflicts = []
        for (mid, cid), total_qty in order_demand.items():
            avail = stock_map.get((mid, cid), 0)
            orders_for_this = [
                (o["order_ref"], l["quantity"])
                for o in pending
                for l in all_lines
                if l["order_id"] == o["id"] and l["model_id"] == mid and l["color_id"] == cid
            ]
            if total_qty > avail and len(orders_for_this) > 1:
                conflicts.append({
                    "Model":    model_map.get(mid,""),
                    "Color":    color_map.get(cid,""),
                    "Stock":    avail,
                    "Needed":   total_qty,
                    "Competing Orders": ", ".join(f"{ref}({qty})" for ref, qty in orders_for_this),
                })

        if conflicts:
            st.warning("⚠️ Stock conflicts detected between orders:")
            st.dataframe(pd.DataFrame(conflicts), use_container_width=True, hide_index=True)
            st.caption("Set order priorities to resolve conflicts — orders with lower priority number are fulfilled first.")
        else:
            st.success("✅ No stock conflicts detected between pending orders.")
