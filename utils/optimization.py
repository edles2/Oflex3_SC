"""
Optimization engine for Oflex3 Supply Chain app.
Uses scipy.optimize.linprog to allocate storage capacity across models/states.
"""
import numpy as np
from scipy.optimize import linprog


def optimize_storage_allocation(
    scenario_rows: list,
    total_storage_m3: float,
    orders: list,
    order_lines: list,
) -> dict:
    """
    LP: Allocate storage capacity to minimise delivery-time-weighted stock shortfall.

    Formulation
    -----------
    Variables  x[i]  = scaling factor for target stock at row i  (0 ≤ x[i] ≤ 1)

    Minimise   Σ_i  leadtime[i] × (1 - x[i]) × target[i]
             (penalises reductions at high-priority, short-leadtime positions)

    Subject to Σ_i  vol[i] × x[i] × target[i]  ≤  total_storage
               0 ≤ x[i] ≤ 1

    Returns recommended scaled targets + remaining storage.
    """
    rows = [r for r in scenario_rows if r["target_stock"] > 0]
    if not rows:
        return {"status": "no_data", "rows": [], "storage_used": 0.0}

    n = len(rows)
    # Coefficients for objective  (minimise weighted shortfall)
    # We minimise -x[i] weighted by (1/leadtime × target × vol)
    # so that units near delivery are filled first.
    lt_arr     = np.array([max(r["leadtime_days"], 0.1) for r in rows])
    target_arr = np.array([r["target_stock"] for r in rows])
    vol_arr    = np.array([r["vol_coeff"] for r in rows])

    # Objective: minimise Σ (lt[i] / max_lt) × (1 - x[i])  → maximise coverage at short-lt
    max_lt   = max(lt_arr)
    c_obj    = (lt_arr / max_lt) * (-1.0)   # negate because linprog minimises

    # Inequality: Σ vol[i] × target[i] × x[i] ≤ total_storage
    A_ub = [(vol_arr * target_arr).tolist()]
    b_ub = [total_storage_m3]

    bounds = [(0.0, 1.0)] * n

    result = linprog(c_obj, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")

    if result.status not in (0, 1):
        # Fall back: proportional scaling
        total_needed = sum(r["target_stock"] * r["vol_coeff"] for r in rows)
        scale = min(1.0, total_storage_m3 / total_needed) if total_needed > 0 else 1.0
        x = np.full(n, scale)
    else:
        x = result.x

    output_rows = []
    storage_used = 0.0
    for i, r in enumerate(rows):
        rec = round(r["target_stock"] * x[i], 1)
        s_used = rec * r["vol_coeff"]
        storage_used += s_used
        output_rows.append({
            **r,
            "recommended_stock": rec,
            "scale_factor":      round(float(x[i]), 3),
            "storage_m3":        round(s_used, 2),
        })

    return {
        "status":       "ok",
        "rows":         output_rows,
        "storage_used": round(storage_used, 2),
        "solver_msg":   getattr(result, "message", ""),
    }


def tradeoff_curve(
    scenario_rows: list,
    max_storage: float,
    n_points: int = 12,
) -> list:
    """
    Compute tradeoff: for each storage budget S, what is the achievable
    weighted-average delivery time?

    Returns list of {'storage_m3': float, 'avg_delivery_days': float}
    """
    rows = [r for r in scenario_rows if r["target_stock"] > 0 and r["vol_coeff"] > 0]
    if not rows:
        return []

    lt_arr     = np.array([max(r["leadtime_days"], 0.1) for r in rows])
    target_arr = np.array([r["target_stock"] for r in rows])
    vol_arr    = np.array([r["vol_coeff"] for r in rows])

    total_unconstrained = float(np.dot(vol_arr, target_arr))
    s_min = total_unconstrained * 0.1
    s_max = max_storage

    budgets = np.linspace(s_min, s_max, n_points)
    curve   = []

    for budget in budgets:
        # Solve LP
        c_obj  = (lt_arr / lt_arr.max()) * (-1.0)
        A_ub   = [(vol_arr * target_arr).tolist()]
        b_ub   = [float(budget)]
        bounds = [(0.0, 1.0)] * len(rows)
        res    = linprog(c_obj, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")

        if res.status == 0:
            x = res.x
        else:
            scale = min(1.0, budget / total_unconstrained) if total_unconstrained > 0 else 1.0
            x = np.full(len(rows), scale)

        # Weighted average delivery time (weighted by demand × stock coverage)
        coverage     = x * target_arr
        total_demand = coverage.sum()
        if total_demand > 0:
            avg_lt = float(np.dot(lt_arr, coverage) / total_demand)
        else:
            avg_lt = float(lt_arr.max())

        curve.append({
            "storage_m3":        round(float(budget), 1),
            "avg_delivery_days": round(avg_lt, 1),
        })

    return curve


def build_launch_plan(
    optimized_rows: list,
    inventory: list,
    model_state_params: list,
) -> list:
    """
    From optimized recommended stocks, compute what to launch at each state.
    """
    inv_map = {}
    for item in inventory:
        key = (item["model_id"], item["state_id"])
        inv_map[key] = inv_map.get(key, 0) + item["quantity"]

    moq_map = {(p["model_id"], p["state_id"]): p.get("moq") for p in model_state_params}

    import math
    plan = []
    for r in optimized_rows:
        key     = (r["model_id"], r["state_id"])
        current = inv_map.get(key, 0)
        rec     = r.get("recommended_stock", r["target_stock"])
        needed  = max(0, rec - current)
        moq     = moq_map.get(key)
        if needed > 0 and moq and moq > 0:
            needed = math.ceil(needed / moq) * moq
        if needed > 0:
            plan.append({
                "model_name":  r["model_name"],
                "state_name":  r["state_name"],
                "current":     current,
                "recommended": rec,
                "to_launch":   round(needed, 0),
                "moq":         moq,
                "leadtime_days": r["leadtime_days"],
            })
    return sorted(plan, key=lambda x: x["leadtime_days"])
