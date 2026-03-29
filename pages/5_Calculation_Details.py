"""
Page 5 — Calculation Details
Shows all formulas and logic used throughout the app, with live worked examples.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import database as db
from utils.calculations import calc_daily_demand, calc_target_stock, calc_production_needed

st.title("Calculation Details")
st.caption("Everything the app computes, step by step. No black box.")

params  = db.get_params()
states  = db.get_states()
models  = db.get_models()
colors  = db.get_colors()
msp     = db.get_model_state_params()
inv     = db.get_inventory()
demand  = db.get_demand_settings()

dpw    = int(params.get("working_days_per_week", 5))
s_cons = float(params.get("safety_conservative", 1.5))
s_std  = float(params.get("safety_standard", 1.0))
s_lean = float(params.get("safety_lean", 0.6))
cap    = float(params.get("total_storage_m3", 500))

tabs = st.tabs([
    "Demand & Target Stock",
    "Production Needed",
    "Stock Health",
    "Storage",
    "Order Feasibility",
    "LP Optimization",
    "Storage Forecast",
])


# ══════════════════════════════════════════════════════════════════
# TAB 1 — Demand & Target Stock
# ══════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Demand & Target Stock")

    st.markdown("#### Formulas")
    st.markdown("""
**Daily demand** (converts weekly demand to per-day):

```
daily_demand = weekly_demand / working_days_per_week
```

**Target stock** (how many units should be in stock at a given production state):

```
target_stock = daily_demand × leadtime_days × safety_multiplier
```

- `leadtime_days` is the cumulative time remaining to delivery from that state
- `safety_multiplier` depends on the chosen scenario
""")

    col1, col2, col3 = st.columns(3)
    col1.metric("Conservative multiplier", f"{s_cons}×")
    col2.metric("Standard multiplier",     f"{s_std}×")
    col3.metric("Lean multiplier",         f"{s_lean}×")

    st.markdown("---")
    st.markdown("#### Worked example")

    if not models or not states or not demand:
        st.info("Configure models, states and demand settings to see a live example.")
    else:
        col_m, col_s, col_sc = st.columns(3)
        sel_model = col_m.selectbox("Model", [m["name"] for m in models], key="ts_model")
        sel_state = col_s.selectbox("State", [s["name"] for s in states], key="ts_state")
        sel_scen  = col_sc.selectbox("Scenario", ["Conservative", "Standard", "Lean"], index=1, key="ts_scen")

        model = next(m for m in models if m["name"] == sel_model)
        state = next(s for s in states if s["name"] == sel_state)
        safety = {"Conservative": s_cons, "Standard": s_std, "Lean": s_lean}[sel_scen]

        weekly = sum(d["weekly_demand"] for d in demand if d["model_id"] == model["id"])
        daily  = calc_daily_demand(weekly, dpw)
        lt     = state["leadtime_days"]
        target = calc_target_stock(daily, lt, safety)

        st.markdown(f"""
| Step | Formula | Value |
|------|---------|-------|
| Weekly demand (all colors) | sum of demand settings | **{weekly:.1f} units/week** |
| Working days per week | parameter | **{dpw} days** |
| Daily demand | {weekly:.1f} / {dpw} | **{daily:.2f} units/day** |
| Lead time at "{sel_state}" | parameter | **{lt:.1f} days** |
| Safety multiplier ({sel_scen}) | parameter | **{safety}×** |
| **Target stock** | {daily:.2f} × {lt:.1f} × {safety} | **{target:.1f} units** |
""")


# ══════════════════════════════════════════════════════════════════
# TAB 2 — Production Needed
# ══════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Production Needed")

    st.markdown("#### Formula")
    st.markdown("""
```
raw_needed     = max(0, target_stock − current_stock)
production_needed = ceil(raw_needed / MOQ) × MOQ   (if MOQ is defined)
```

- If `raw_needed` is 0, no launch is required.
- MOQ (Minimum Order Quantity) forces rounding up to the next batch size.
- If no MOQ is set for that model × state, `production_needed = raw_needed`.
""")

    st.markdown("---")
    st.markdown("#### Worked example")

    if not models or not states or not demand:
        st.info("Configure models, states and demand settings to see a live example.")
    else:
        col_m2, col_s2, col_sc2 = st.columns(3)
        sel_model2 = col_m2.selectbox("Model", [m["name"] for m in models], key="pn_model")
        sel_state2 = col_s2.selectbox("State", [s["name"] for s in states], key="pn_state")
        sel_scen2  = col_sc2.selectbox("Scenario", ["Conservative", "Standard", "Lean"], index=1, key="pn_scen")

        model2  = next(m for m in models if m["name"] == sel_model2)
        state2  = next(s for s in states if s["name"] == sel_state2)
        safety2 = {"Conservative": s_cons, "Standard": s_std, "Lean": s_lean}[sel_scen2]

        weekly2  = sum(d["weekly_demand"] for d in demand if d["model_id"] == model2["id"])
        daily2   = calc_daily_demand(weekly2, dpw)
        lt2      = state2["leadtime_days"]
        target2  = calc_target_stock(daily2, lt2, safety2)

        sp2 = next((p for p in msp if p["model_id"] == model2["id"] and p["state_id"] == state2["id"]), {})
        moq2 = sp2.get("moq")

        inv_map = {}
        for item in inv:
            k = (item["model_id"], item["state_id"])
            inv_map[k] = inv_map.get(k, 0) + item["quantity"]
        current2 = inv_map.get((model2["id"], state2["id"]), 0)

        raw_needed = max(0, target2 - current2)
        needed = calc_production_needed(target2, current2, moq2)

        moq_note = f"ceil({raw_needed:.1f} / {moq2}) × {moq2} = **{needed:.0f}**" if moq2 and raw_needed > 0 else f"no MOQ → **{raw_needed:.1f}**"

        st.markdown(f"""
| Step | Formula | Value |
|------|---------|-------|
| Target stock | (from previous tab) | **{target2:.1f} units** |
| Current stock | from inventory snapshot | **{current2} units** |
| Raw needed | max(0, {target2:.1f} − {current2}) | **{raw_needed:.1f} units** |
| MOQ for this model × state | parameter | **{moq2 if moq2 else "not set"}** |
| **Production needed** | {moq_note} | **{needed:.0f} units** |
""")


# ══════════════════════════════════════════════════════════════════
# TAB 3 — Stock Health
# ══════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Stock Health Status")

    st.markdown("#### Rules (evaluated in this order)")
    st.markdown("""
| Status | Condition | Color |
|--------|-----------|-------|
| **Critical** | `current_stock < KANBAN threshold` | Red |
| **Low** | `current_stock < target_stock × 0.5` | Yellow |
| **Excess** | `current_stock > target_stock × 1.3` | Orange |
| **OK** | none of the above | Green |

KANBAN threshold is set per model × state in Parameters. It is a hard reorder trigger —
when stock falls below it, the status is Critical regardless of the target.
""")

    st.markdown("---")
    st.markdown("#### Worked example")

    if not models or not states or not demand:
        st.info("Configure models, states and demand settings to see a live example.")
    else:
        col_m3, col_s3, col_sc3 = st.columns(3)
        sel_model3 = col_m3.selectbox("Model", [m["name"] for m in models], key="sh_model")
        sel_state3 = col_s3.selectbox("State", [s["name"] for s in states], key="sh_state")
        sel_scen3  = col_sc3.selectbox("Scenario", ["Conservative", "Standard", "Lean"], index=1, key="sh_scen")

        model3  = next(m for m in models if m["name"] == sel_model3)
        state3  = next(s for s in states if s["name"] == sel_state3)
        safety3 = {"Conservative": s_cons, "Standard": s_std, "Lean": s_lean}[sel_scen3]

        weekly3  = sum(d["weekly_demand"] for d in demand if d["model_id"] == model3["id"])
        daily3   = calc_daily_demand(weekly3, dpw)
        target3  = calc_target_stock(daily3, state3["leadtime_days"], safety3)

        sp3 = next((p for p in msp if p["model_id"] == model3["id"] and p["state_id"] == state3["id"]), {})
        kb3 = sp3.get("kanban_threshold")

        inv_map3 = {}
        for item in inv:
            k = (item["model_id"], item["state_id"])
            inv_map3[k] = inv_map3.get(k, 0) + item["quantity"]
        current3 = inv_map3.get((model3["id"], state3["id"]), 0)

        if kb3 and current3 < kb3:
            health3 = "Critical"
            reason3 = f"current {current3} < KANBAN {kb3}"
        elif target3 > 0 and current3 < target3 * 0.5:
            health3 = "Low"
            reason3 = f"current {current3} < target × 0.5 ({target3 * 0.5:.1f})"
        elif target3 > 0 and current3 > target3 * 1.3:
            health3 = "Excess"
            reason3 = f"current {current3} > target × 1.3 ({target3 * 1.3:.1f})"
        else:
            health3 = "OK"
            reason3 = f"current {current3} is within normal range"

        color_map = {"Critical": "#e74c3c", "Low": "#f39c12", "Excess": "#e67e22", "OK": "#2ecc71"}
        st.markdown(f"""
| Parameter | Value |
|-----------|-------|
| Current stock | **{current3} units** |
| Target stock ({sel_scen3}) | **{target3:.1f} units** |
| KANBAN threshold | **{kb3 if kb3 else "not set"}** |
| Low threshold (target × 0.5) | **{target3 * 0.5:.1f}** |
| Excess threshold (target × 1.3) | **{target3 * 1.3:.1f}** |
""")
        st.markdown(f"**Result:** :{color_map[health3].replace('#','')}[{health3}] — {reason3}")
        st.info(f"Status: **{health3}** — {reason3}")


# ══════════════════════════════════════════════════════════════════
# TAB 4 — Storage
# ══════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Storage Calculations")

    st.markdown("#### Formulas")
    st.markdown("""
**Storage used by a stock position:**
```
storage_m3 = quantity × volume_coefficient
```

**Total storage used** (sum across all models × states × colors):
```
total_storage_m3 = Σ (quantity[i] × vol_coeff[i])
```

**Target storage** (how much space the target stock would need):
```
target_storage_m3 = target_stock × vol_coeff
```

Volume coefficients (m³/unit) are set per model × state in Parameters.
They represent how much space one unit occupies at that stage of production
(e.g. assembled chairs take more space than raw tubes).
""")

    st.markdown("---")
    st.markdown("#### Current storage breakdown")

    if not msp or not inv:
        st.info("No inventory data yet.")
    else:
        vol_map4 = {(p["model_id"], p["state_id"]): p["volume_coeff"] for p in msp}
        model_map4 = {m["id"]: m["name"] for m in models}
        state_map4 = {s["id"]: s["name"] for s in states}

        rows4 = []
        for item in inv:
            if item["quantity"] == 0:
                continue
            vol = vol_map4.get((item["model_id"], item["state_id"]), 0.0)
            rows4.append({
                "Model":         model_map4.get(item["model_id"], ""),
                "State":         state_map4.get(item["state_id"], ""),
                "Quantity":      item["quantity"],
                "Vol. coeff (m³/unit)": vol,
                "Storage (m³)":  round(item["quantity"] * vol, 3),
                "Calculation":   f"{item['quantity']} × {vol} = {item['quantity'] * vol:.3f}",
            })

        if rows4:
            df4 = pd.DataFrame(rows4)
            st.dataframe(df4, use_container_width=True, hide_index=True)
            total4 = df4["Storage (m³)"].sum()
            st.markdown(f"**Total: {total4:.2f} m³ used out of {cap:.0f} m³ capacity ({total4/cap*100:.1f}%)**")
        else:
            st.info("All inventory quantities are zero.")


# ══════════════════════════════════════════════════════════════════
# TAB 5 — Order Feasibility
# ══════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("Order Feasibility Logic")

    st.markdown("#### How it works")
    st.markdown("""
For each line item in an order (model × color × quantity):

**Step 1 — Find the best available stock position.**

States are checked from closest-to-delivery down to raw material:
```
for state in [Ready for delivery → Packaged → Painted → Assembled → Kit → Raw]:
    if stock[model, color, state] >= qty_needed:
        use this state's leadtime_days as the delivery estimate
        break
```
Color is only matched for states at "Painted" or later (order_index ≥ 4).
For earlier states, stock is color-agnostic.

**Step 2 — If nothing in stock**, fall back to the raw material leadtime (full production cycle).

**Step 3 — Order lead time** = max lead time across all line items.

**Step 4 — Estimated delivery date:**
```
est_delivery = today + leadtime_days × (7 / working_days_per_week)
```
(converts working days to calendar days, approximate)

**Step 5 — At risk** if `est_delivery > deadline`.
""")

    st.markdown("---")
    st.markdown("#### Working days → calendar days conversion")
    st.markdown(f"""
With **{dpw} working days/week**:
```
calendar_days = working_days × (7 / {dpw}) = working_days × {7/dpw:.2f}
```

| Working days | Calendar days (approx.) |
|---|---|
| 1 | {1 * 7 / dpw:.1f} |
| 5 | {5 * 7 / dpw:.1f} |
| 10 | {10 * 7 / dpw:.1f} |
| 20 | {20 * 7 / dpw:.1f} |
| 40 | {40 * 7 / dpw:.1f} |
""")


# ══════════════════════════════════════════════════════════════════
# TAB 6 — LP Optimization
# ══════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("LP Storage Allocation Optimization")

    st.markdown("#### Problem statement")
    st.markdown("""
Given a storage capacity constraint, how should stock be allocated across
all model × state positions to minimise delivery time?

The app uses a **linear program** (via `scipy.optimize.linprog`, HiGHS solver).
""")

    st.markdown("#### Decision variables")
    st.markdown("""
For each position `i` (model × state with a non-zero target stock):

```
x[i]  ∈ [0, 1]   — scaling factor applied to the target stock
```

`x[i] = 1` means the full target stock is held. `x[i] = 0.5` means half the target.
""")

    st.markdown("#### Objective")
    st.markdown("""
**Minimise weighted shortfall**, prioritising positions close to delivery:

```
minimise  Σ_i  (leadtime[i] / max_leadtime) × (−x[i])
```

Positions with **short leadtime** (near delivery) get a larger negative weight,
so the solver fills them first. A unit at "Ready for delivery" (leadtime ≈ 1 day)
is far more valuable to hold than a unit at "Raw material" (leadtime = 40 days).
""")

    st.markdown("#### Constraint")
    st.markdown("""
**Total storage must not exceed capacity:**

```
Σ_i  vol_coeff[i] × target_stock[i] × x[i]  ≤  total_storage_m3
```
""")

    st.markdown("#### Output")
    st.markdown("""
- `recommended_stock[i] = target_stock[i] × x[i]`
- `scale_factor[i] = x[i]`  (shown as % in the results table)
- If the LP is infeasible, falls back to proportional scaling:
  `x[i] = min(1, total_storage / total_needed)` for all `i`.
""")

    st.markdown("#### Tradeoff curve")
    st.markdown("""
The storage vs. delivery time tradeoff chart solves the same LP repeatedly
across a range of storage budgets from 10% of unconstrained need up to the
current capacity. Each point shows the **demand-weighted average delivery time**
achievable at that storage level:

```
avg_delivery = Σ_i (leadtime[i] × coverage[i]) / Σ_i coverage[i]
where coverage[i] = x[i] × target_stock[i]
```
""")


# ══════════════════════════════════════════════════════════════════
# TAB 7 — Storage Forecast
# ══════════════════════════════════════════════════════════════════
with tabs[6]:
    st.subheader("12-Week Storage Forecast")

    st.markdown("#### Model")
    st.markdown("""
The forecast is a **simple stock depletion model** — it does not account for
production replenishments, only consumption:

```
stock[i, week] = max(0, current_stock[i] − daily_demand[i] × days_per_week × week)
storage[week]  = Σ_i  stock[i, week] × vol_coeff[i]
```

This answers: *"If we don't launch any production, how fast does storage free up?"*

It is a conservative lower-bound estimate — actual storage will be higher
once production replenishments are triggered.
""")

    st.markdown("---")
    st.markdown("#### Live forecast table")

    if not models or not states or not demand:
        st.info("Configure models, states and demand to see the forecast.")
    else:
        vol_map7  = {(p["model_id"], p["state_id"]): p["volume_coeff"] for p in msp}
        inv_map7  = {}
        for item in inv:
            k = (item["model_id"], item["state_id"])
            inv_map7[k] = inv_map7.get(k, 0) + item["quantity"]

        weekly_by_model = {}
        for d in demand:
            mid = d["model_id"]
            weekly_by_model[mid] = weekly_by_model.get(mid, 0.0) + d["weekly_demand"]

        # Build per-position data
        positions = []
        for m in models:
            for s in states:
                if not s.get("can_hold_stock", 1):
                    continue
                k = (m["id"], s["id"])
                positions.append({
                    "key":          k,
                    "current":      inv_map7.get(k, 0),
                    "daily_demand": weekly_by_model.get(m["id"], 0) / dpw if dpw > 0 else 0,
                    "vol":          vol_map7.get(k, 0.0),
                })

        weeks = list(range(13))
        rows7 = []
        for w in weeks:
            total = 0.0
            for p in positions:
                remaining = max(0, p["current"] - p["daily_demand"] * dpw * w)
                total += remaining * p["vol"]
            rows7.append({"Week": w, "Projected storage (m³)": round(total, 2),
                          "Formula": f"stock depleted by {w} weeks of demand"})

        df7 = pd.DataFrame(rows7)
        st.dataframe(df7[["Week","Projected storage (m³)","Formula"]], use_container_width=True, hide_index=True)

        fig7 = go.Figure()
        fig7.add_trace(go.Scatter(
            x=df7["Week"], y=df7["Projected storage (m³)"],
            mode="lines+markers", name="Projected storage",
            line=dict(color="#1f77b4", width=2),
        ))
        fig7.add_hline(y=cap, line_dash="dash", line_color="red",
                       annotation_text=f"Capacity ({cap:.0f} m³)")
        fig7.update_layout(
            title="Storage Depletion Forecast (no replenishment assumed)",
            xaxis_title="Week", yaxis_title="Storage (m³)",
            height=350, margin=dict(t=50),
        )
        st.plotly_chart(fig7, use_container_width=True)
