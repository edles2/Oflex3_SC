"""
Business logic calculations for Oflex3 Supply Chain app.
"""
from datetime import datetime, timedelta
from typing import Optional


DATE_FMT = "%d/%m/%Y"


def parse_date(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s, DATE_FMT)
    except Exception:
        return None


def fmt_date(dt: datetime) -> str:
    return dt.strftime(DATE_FMT)


def today_str() -> str:
    return fmt_date(datetime.now())


def add_working_days(start: datetime, days: float, days_per_week: int = 5) -> datetime:
    """Add working days to a date (approximate: converts to calendar days)."""
    calendar_days = int(days * 7 / days_per_week)
    return start + timedelta(days=calendar_days)


# ─── Storage calculations ──────────────────────────────────────────────────────

def calc_storage_used(inventory: list, model_state_params: list) -> float:
    """
    inventory: list of dicts with model_id, state_id, quantity
    model_state_params: list of dicts with model_id, state_id, volume_coeff
    Returns total m³ used.
    """
    vol_map = {(p["model_id"], p["state_id"]): p["volume_coeff"] for p in model_state_params}
    total = 0.0
    for item in inventory:
        key = (item["model_id"], item["state_id"])
        vol = vol_map.get(key, 0.0)
        total += vol * item["quantity"]
    return round(total, 3)


def calc_storage_breakdown(inventory: list, model_state_params: list) -> dict:
    """Returns {(model_id, state_id): m³ used}"""
    vol_map = {(p["model_id"], p["state_id"]): p["volume_coeff"] for p in model_state_params}
    breakdown = {}
    for item in inventory:
        key = (item["model_id"], item["state_id"])
        vol = vol_map.get(key, 0.0) * item["quantity"]
        breakdown[key] = breakdown.get(key, 0.0) + vol
    return breakdown


# ─── Target stock & production planning ───────────────────────────────────────

def calc_target_stock(daily_demand: float, leadtime_days: float, safety_mult: float) -> float:
    """Standard formula: target = daily_demand × leadtime_days × safety_multiplier."""
    return daily_demand * leadtime_days * safety_mult


def calc_daily_demand(weekly_demand: float, days_per_week: int = 5) -> float:
    return weekly_demand / days_per_week if days_per_week > 0 else 0.0


def calc_production_needed(target: float, current: float, moq) -> float:
    """
    How many units to launch to reach target from current stock.
    Rounds up to MOQ if applicable.
    """
    needed = max(0.0, target - current)
    if needed > 0 and moq and moq > 0:
        # Round up to nearest MOQ
        import math
        needed = math.ceil(needed / moq) * moq
    return needed


def build_scenario(
    models: list,
    states: list,
    model_state_params: list,
    inventory: list,
    demand_settings: list,
    safety_mult: float,
    days_per_week: int,
    total_storage_m3: float,
) -> dict:
    """
    Returns a scenario dict with target stocks, production needed, storage,
    and stock health per (model_id, state_id).
    """
    # Build lookup maps
    vol_map = {(p["model_id"], p["state_id"]): p["volume_coeff"] for p in model_state_params}
    moq_map = {(p["model_id"], p["state_id"]): p["moq"] for p in model_state_params}
    kb_map  = {(p["model_id"], p["state_id"]): p["kanban_threshold"] for p in model_state_params}
    state_map = {s["id"]: s for s in states}

    inv_map: dict = {}
    for item in inventory:
        key = (item["model_id"], item["state_id"])
        inv_map[key] = inv_map.get(key, 0) + item["quantity"]

    # Aggregate weekly demand per model (sum over colors)
    weekly_demand_by_model: dict = {}
    for d in demand_settings:
        mid = d["model_id"]
        weekly_demand_by_model[mid] = weekly_demand_by_model.get(mid, 0.0) + d["weekly_demand"]

    results = []
    total_storage_needed = 0.0
    total_storage_used   = 0.0

    for model in models:
        mid = model["id"]
        weekly = weekly_demand_by_model.get(mid, 0.0)
        daily  = calc_daily_demand(weekly, days_per_week)

        for state in states:
            if not state.get("can_hold_stock", 1):
                continue
            sid  = state["id"]
            lt   = state["leadtime_days"]
            vol  = vol_map.get((mid, sid), 0.0)
            moq  = moq_map.get((mid, sid))
            kb   = kb_map.get((mid, sid))
            current = inv_map.get((mid, sid), 0)

            target   = calc_target_stock(daily, lt, safety_mult)
            needed   = calc_production_needed(target, current, moq)
            stor_tgt = target * vol
            stor_cur = current * vol

            total_storage_needed += stor_tgt
            total_storage_used   += stor_cur

            # Health status
            if kb and current < kb:
                health = "critical"
            elif target > 0 and current < target * 0.5:
                health = "low"
            elif target > 0 and current > target * 1.3:
                health = "excess"
            else:
                health = "ok"

            results.append({
                "model_id":        mid,
                "model_name":      model["name"],
                "state_id":        sid,
                "state_name":      state["name"],
                "leadtime_days":   lt,
                "daily_demand":    round(daily, 2),
                "weekly_demand":   round(weekly, 2),
                "target_stock":    round(target, 1),
                "current_stock":   current,
                "production_needed": round(needed, 0),
                "moq":             moq,
                "kanban_threshold": kb,
                "vol_coeff":       vol,
                "storage_target_m3":  round(stor_tgt, 2),
                "storage_current_m3": round(stor_cur, 2),
                "health":          health,
            })

    return {
        "rows":                   results,
        "total_storage_needed_m3": round(total_storage_needed, 2),
        "total_storage_used_m3":   round(total_storage_used, 2),
        "storage_capacity_m3":     total_storage_m3,
        "over_capacity":           total_storage_needed > total_storage_m3,
    }


# ─── Delivery time estimation ──────────────────────────────────────────────────

def estimate_delivery_days(
    model_id: int,
    color_id: int,
    qty_needed: int,
    inventory: list,
    states: list,
    days_per_week: int = 5,
) -> tuple:
    """
    Estimate earliest delivery time (in working days) for qty_needed units.
    Returns (leadtime_days, state_name, available_qty) for the best available state.
    Falls back to raw material leadtime if nothing in stock.
    """
    # Aggregate inventory per state (model+color aware: color states 4+ need color match)
    state_stock: dict = {}
    for item in inventory:
        if item["model_id"] != model_id:
            continue
        sid = item["state_id"]
        # Color only matters for painted+ states (order_index >= 4)
        state = next((s for s in states if s["id"] == sid), None)
        if state and state["order_index"] >= 4:
            if item.get("color_id") != color_id:
                continue
        state_stock[sid] = state_stock.get(sid, 0) + item["quantity"]

    # Try from closest-to-delivery state first
    for state in sorted(states, key=lambda s: s["order_index"], reverse=True):
        sid = state["id"]
        avail = state_stock.get(sid, 0)
        if avail >= qty_needed:
            return state["leadtime_days"], state["name"], avail

    # Nothing in stock — use raw material leadtime
    raw_state = next((s for s in states if s["order_index"] == 1), None)
    lt = raw_state["leadtime_days"] if raw_state else 40
    return lt, "Raw material (to produce)", 0


def calc_order_feasibility(
    orders: list,
    order_lines: list,
    inventory: list,
    states: list,
    days_per_week: int = 5,
) -> list:
    """
    For each order, compute feasibility status and estimated delivery date.
    Returns list of enriched order dicts.
    """
    today = datetime.now()
    results = []

    for order in orders:
        oid = order["id"]
        lines = [l for l in order_lines if l["order_id"] == oid]
        deadline = parse_date(order["deadline"])

        max_lt   = 0
        feasible = True
        details  = []

        for line in lines:
            lt_days, state_name, avail = estimate_delivery_days(
                line["model_id"], line["color_id"], line["quantity"],
                inventory, states, days_per_week,
            )
            max_lt = max(max_lt, lt_days)
            enough = avail >= line["quantity"]
            if not enough:
                feasible = False
            details.append({
                "model_name": line.get("model_name", ""),
                "color_name": line.get("color_name", ""),
                "qty":        line["quantity"],
                "avail":      avail,
                "lt_days":    lt_days,
                "state_name": state_name,
                "from_stock": enough,
            })

        est_delivery = add_working_days(today, max_lt, days_per_week)
        at_risk = deadline and est_delivery > deadline

        results.append({
            **order,
            "lines":          lines,
            "line_details":   details,
            "max_lt_days":    max_lt,
            "est_delivery":   fmt_date(est_delivery),
            "from_stock":     feasible,
            "at_risk":        at_risk,
        })

    return results


# ─── Storage forecast ─────────────────────────────────────────────────────────

def calc_storage_forecast(
    scenario_rows: list,
    weeks: int = 12,
    days_per_week: int = 5,
) -> list:
    """
    Rolling weekly storage forecast.
    Assumption: stock depletes at daily_demand rate each week (simplified).
    Returns list of {'week': int, 'storage_m3': float}
    """
    current_stock = {(r["model_id"], r["state_id"]): r["current_stock"] for r in scenario_rows}
    vol_map       = {(r["model_id"], r["state_id"]): r["vol_coeff"]     for r in scenario_rows}
    demand_map    = {(r["model_id"], r["state_id"]): r["daily_demand"]  for r in scenario_rows}

    forecast = []
    for w in range(weeks + 1):
        total = 0.0
        for key in current_stock:
            stock = max(0, current_stock[key] - demand_map.get(key, 0) * days_per_week * w)
            total += stock * vol_map.get(key, 0.0)
        forecast.append({"week": w, "storage_m3": round(total, 2)})
    return forecast
