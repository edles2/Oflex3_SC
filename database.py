"""
database.py — All SQLite operations for Oflex3 Supply Chain app.
"""
import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oflex3.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS global_params (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS production_states (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT    NOT NULL,
            order_index     INTEGER NOT NULL,
            leadtime_weeks  REAL    NOT NULL DEFAULT 0,
            leadtime_days   REAL    NOT NULL DEFAULT 0,
            can_hold_stock  INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS chair_models (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS model_state_params (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id          INTEGER NOT NULL,
            state_id          INTEGER NOT NULL,
            volume_coeff      REAL    NOT NULL DEFAULT 0.0,
            moq               INTEGER DEFAULT NULL,
            kanban_threshold  INTEGER DEFAULT NULL,
            cycle_time_days   REAL    DEFAULT NULL,
            UNIQUE(model_id, state_id),
            FOREIGN KEY (model_id) REFERENCES chair_models(id) ON DELETE CASCADE,
            FOREIGN KEY (state_id) REFERENCES production_states(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS raw_materials (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id       INTEGER NOT NULL,
            name           TEXT    NOT NULL,
            supplier       TEXT    DEFAULT '',
            moq            INTEGER DEFAULT NULL,
            unit_volume    REAL    DEFAULT 0.0,
            leadtime_weeks REAL    DEFAULT 0.0,
            FOREIGN KEY (model_id) REFERENCES chair_models(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS colors (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL UNIQUE,
            painting_moq INTEGER DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS inventory (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id   INTEGER NOT NULL,
            state_id   INTEGER NOT NULL,
            color_id   INTEGER DEFAULT NULL,
            quantity   INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (model_id) REFERENCES chair_models(id)  ON DELETE CASCADE,
            FOREIGN KEY (state_id) REFERENCES production_states(id) ON DELETE CASCADE,
            FOREIGN KEY (color_id) REFERENCES colors(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS demand_settings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id     INTEGER NOT NULL,
            color_id     INTEGER NOT NULL,
            weekly_demand REAL   NOT NULL DEFAULT 0,
            UNIQUE(model_id, color_id),
            FOREIGN KEY (model_id) REFERENCES chair_models(id)  ON DELETE CASCADE,
            FOREIGN KEY (color_id) REFERENCES colors(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS orders (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            order_ref     TEXT NOT NULL UNIQUE,
            customer_name TEXT NOT NULL,
            order_date    TEXT NOT NULL,
            deadline      TEXT NOT NULL,
            priority      INTEGER NOT NULL DEFAULT 3,
            status        TEXT NOT NULL DEFAULT 'pending',
            destination   TEXT DEFAULT '',
            notes         TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS order_lines (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            model_id INTEGER NOT NULL,
            color_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
            FOREIGN KEY (model_id) REFERENCES chair_models(id),
            FOREIGN KEY (color_id) REFERENCES colors(id)
        );

        CREATE TABLE IF NOT EXISTS logistics_centers (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT NOT NULL UNIQUE,
            country        TEXT DEFAULT '',
            city           TEXT DEFAULT '',
            capacity_m3    REAL DEFAULT 0,
            fixed_cost_eur REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS transport_routes (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            center_id               INTEGER NOT NULL,
            destination             TEXT    NOT NULL,
            transport_time_days     INTEGER DEFAULT 0,
            shared_truck            INTEGER DEFAULT 0,
            truck_capacity_m3       REAL    DEFAULT 0,
            cost_per_m3             REAL    DEFAULT 0,
            departure_frequency_days INTEGER DEFAULT 1,
            transport_mode          TEXT    DEFAULT 'truck',
            FOREIGN KEY (center_id) REFERENCES logistics_centers(id) ON DELETE CASCADE
        );
    """)

    c.execute("SELECT value FROM global_params WHERE key='data_initialized'")
    if not c.fetchone():
        _load_sample_data(conn)

    conn.commit()
    conn.close()


def _load_sample_data(conn):
    c = conn.cursor()
    today_dt = datetime.now()

    # Global params
    params = [
        ("total_storage_m3",     "500"),
        ("safety_conservative",  "1.5"),
        ("safety_standard",      "1.0"),
        ("safety_lean",          "0.6"),
        ("working_days_per_week","5"),
        ("working_weeks_per_year","52"),
        ("data_initialized",     "true"),
    ]
    c.executemany("INSERT OR IGNORE INTO global_params VALUES (?,?)", params)

    # Production states
    states = [
        (1, "Raw material",           1, 8.0, 40.0,  1),
        (2, "Prepared parts (kit)",   2, 6.0, 30.0,  1),
        (3, "Assembled raw chairs",   3, 2.5, 12.5,  1),
        (4, "Painted chairs",         4, 1.0,  5.0,  1),
        (5, "Individually packaged",  5, 0.5,  2.5,  1),
        (6, "Ready for delivery",     6, 0.2,  1.0,  1),
    ]
    c.executemany(
        "INSERT OR IGNORE INTO production_states (id,name,order_index,leadtime_weeks,leadtime_days,can_hold_stock) VALUES (?,?,?,?,?,?)",
        states,
    )

    # Chair models
    c.execute("INSERT OR IGNORE INTO chair_models (id,name,description) VALUES (1,'Model A','Standard chair')")
    c.execute("INSERT OR IGNORE INTO chair_models (id,name,description) VALUES (2,'Model B','Premium chair')")

    # Model state params
    a = [
        (1,1,0.05,None,None,5.0),
        (1,2,0.08,100,50,3.0),
        (1,3,0.15,40,None,2.0),
        (1,4,0.15,20,None,1.0),
        (1,5,0.18,None,None,0.5),
        (1,6,0.18,None,None,0.0),
    ]
    b = [
        (2,1,0.06,None,None,5.0),
        (2,2,0.10,80,40,3.0),
        (2,3,0.20,40,None,2.0),
        (2,4,0.20,20,None,1.0),
        (2,5,0.22,None,None,0.5),
        (2,6,0.22,None,None,0.0),
    ]
    c.executemany(
        "INSERT OR IGNORE INTO model_state_params (model_id,state_id,volume_coeff,moq,kanban_threshold,cycle_time_days) VALUES (?,?,?,?,?,?)",
        a + b,
    )

    # Raw materials
    c.execute("INSERT OR IGNORE INTO raw_materials (model_id,name,supplier,moq,unit_volume,leadtime_weeks) VALUES (1,'Steel tubes','SupplierX',200,0.01,8)")
    c.execute("INSERT OR IGNORE INTO raw_materials (model_id,name,supplier,moq,unit_volume,leadtime_weeks) VALUES (2,'Reinforced steel','SupplierY',150,0.012,10)")

    # Colors
    c.execute("INSERT OR IGNORE INTO colors (id,name,painting_moq) VALUES (1,'Black',20)")
    c.execute("INSERT OR IGNORE INTO colors (id,name,painting_moq) VALUES (2,'White',20)")
    c.execute("INSERT OR IGNORE INTO colors (id,name,painting_moq) VALUES (3,'Grey',30)")

    # Orders
    dl1 = (today_dt + timedelta(weeks=3)).strftime("%d/%m/%Y")
    dl2 = (today_dt + timedelta(weeks=6)).strftime("%d/%m/%Y")
    od  = today_dt.strftime("%d/%m/%Y")
    c.execute("INSERT OR IGNORE INTO orders (id,order_ref,customer_name,order_date,deadline,priority,status,destination,notes) VALUES (1,'ORD-001','ClientFR',?,?,1,'pending','France','')", (od, dl1))
    c.execute("INSERT OR IGNORE INTO orders (id,order_ref,customer_name,order_date,deadline,priority,status,destination,notes) VALUES (2,'ORD-002','ClientDE',?,?,2,'pending','Germany','')", (od, dl2))

    # Order lines
    c.executemany("INSERT OR IGNORE INTO order_lines (order_id,model_id,color_id,quantity) VALUES (?,?,?,?)", [
        (1, 1, 1, 50),
        (2, 2, 2, 30),
        (2, 1, 3, 20),
    ])

    # Logistics center + transport route
    c.execute("INSERT OR IGNORE INTO logistics_centers (id,name,country,city,capacity_m3,fixed_cost_eur) VALUES (1,'Paris Hub','France','Paris',200,5000)")
    c.execute("INSERT OR IGNORE INTO transport_routes (center_id,destination,transport_time_days,shared_truck,truck_capacity_m3,cost_per_m3,departure_frequency_days,transport_mode) VALUES (1,'Germany',3,1,30,15.0,5,'truck')")

    # Default demand
    demand = [(1,1,10.0),(1,2,8.0),(1,3,5.0),(2,1,6.0),(2,2,5.0),(2,3,3.0)]
    c.executemany("INSERT OR IGNORE INTO demand_settings (model_id,color_id,weekly_demand) VALUES (?,?,?)", demand)


# ─── Global params ─────────────────────────────────────────────────────────────
def get_params() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM global_params").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def set_param(key: str, value):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO global_params (key,value) VALUES (?,?)", (key, str(value)))
    conn.commit()
    conn.close()


# ─── Production states ─────────────────────────────────────────────────────────
def get_states() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM production_states ORDER BY order_index").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_states(states: list):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM production_states")
    for i, s in enumerate(states):
        c.execute(
            "INSERT INTO production_states (id,name,order_index,leadtime_weeks,leadtime_days,can_hold_stock) VALUES (?,?,?,?,?,?)",
            (s.get("id") or None, s["name"], i + 1, s["leadtime_weeks"], s["leadtime_days"], int(s.get("can_hold_stock", 1))),
        )
    conn.commit()
    conn.close()


# ─── Chair models ──────────────────────────────────────────────────────────────
def get_models() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM chair_models ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_model(name: str, description: str, model_id: int = None) -> int:
    conn = get_conn()
    c = conn.cursor()
    if model_id:
        c.execute("UPDATE chair_models SET name=?, description=? WHERE id=?", (name, description, model_id))
        conn.commit()
        conn.close()
        return model_id
    else:
        c.execute("INSERT INTO chair_models (name,description) VALUES (?,?)", (name, description))
        mid = c.lastrowid
        conn.commit()
        conn.close()
        return mid


def delete_model(model_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM chair_models WHERE id=?", (model_id,))
    conn.commit()
    conn.close()


# ─── Model–state params ────────────────────────────────────────────────────────
def get_model_state_params(model_id: int = None) -> list:
    conn = get_conn()
    if model_id:
        rows = conn.execute("SELECT * FROM model_state_params WHERE model_id=?", (model_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM model_state_params").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_model_state_params(model_id: int, state_id: int, volume_coeff: float,
                               moq, kanban_threshold, cycle_time_days):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM model_state_params WHERE model_id=? AND state_id=?", (model_id, state_id))
    row = c.fetchone()
    if row:
        c.execute(
            "UPDATE model_state_params SET volume_coeff=?,moq=?,kanban_threshold=?,cycle_time_days=? WHERE id=?",
            (volume_coeff, moq, kanban_threshold, cycle_time_days, row["id"]),
        )
    else:
        c.execute(
            "INSERT INTO model_state_params (model_id,state_id,volume_coeff,moq,kanban_threshold,cycle_time_days) VALUES (?,?,?,?,?,?)",
            (model_id, state_id, volume_coeff, moq, kanban_threshold, cycle_time_days),
        )
    conn.commit()
    conn.close()


# ─── Raw materials ─────────────────────────────────────────────────────────────
def get_raw_materials(model_id: int = None) -> list:
    conn = get_conn()
    if model_id:
        rows = conn.execute("SELECT * FROM raw_materials WHERE model_id=?", (model_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM raw_materials").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_raw_material(model_id, name, supplier, moq, unit_volume, leadtime_weeks, mat_id=None):
    conn = get_conn()
    c = conn.cursor()
    if mat_id:
        c.execute(
            "UPDATE raw_materials SET name=?,supplier=?,moq=?,unit_volume=?,leadtime_weeks=? WHERE id=?",
            (name, supplier, moq, unit_volume, leadtime_weeks, mat_id),
        )
    else:
        c.execute(
            "INSERT INTO raw_materials (model_id,name,supplier,moq,unit_volume,leadtime_weeks) VALUES (?,?,?,?,?,?)",
            (model_id, name, supplier, moq, unit_volume, leadtime_weeks),
        )
    conn.commit()
    conn.close()


def delete_raw_material(mat_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM raw_materials WHERE id=?", (mat_id,))
    conn.commit()
    conn.close()


# ─── Colors ────────────────────────────────────────────────────────────────────
def get_colors() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM colors ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_color(name: str, painting_moq, color_id: int = None):
    conn = get_conn()
    c = conn.cursor()
    if color_id:
        c.execute("UPDATE colors SET name=?, painting_moq=? WHERE id=?", (name, painting_moq, color_id))
    else:
        c.execute("INSERT INTO colors (name,painting_moq) VALUES (?,?)", (name, painting_moq))
    conn.commit()
    conn.close()


def delete_color(color_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM colors WHERE id=?", (color_id,))
    conn.commit()
    conn.close()


# ─── Inventory ─────────────────────────────────────────────────────────────────
def get_inventory() -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT i.*, m.name AS model_name, s.name AS state_name, s.order_index,
               c.name AS color_name
        FROM inventory i
        JOIN chair_models m ON i.model_id = m.id
        JOIN production_states s ON i.state_id = s.id
        LEFT JOIN colors c ON i.color_id = c.id
        ORDER BY m.name, s.order_index, c.name
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_inventory(model_id: int, state_id: int, color_id, quantity: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id FROM inventory WHERE model_id=? AND state_id=? AND color_id IS ?",
        (model_id, state_id, color_id),
    )
    row = c.fetchone()
    if row:
        c.execute("UPDATE inventory SET quantity=?, updated_at=datetime('now') WHERE id=?", (quantity, row["id"]))
    else:
        c.execute("INSERT INTO inventory (model_id,state_id,color_id,quantity) VALUES (?,?,?,?)", (model_id, state_id, color_id, quantity))
    conn.commit()
    conn.close()


def clear_inventory():
    conn = get_conn()
    conn.execute("DELETE FROM inventory")
    conn.commit()
    conn.close()


# ─── Demand settings ───────────────────────────────────────────────────────────
def get_demand_settings() -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT d.*, m.name AS model_name, c.name AS color_name
        FROM demand_settings d
        JOIN chair_models m ON d.model_id = m.id
        JOIN colors c ON d.color_id = c.id
        ORDER BY m.name, c.name
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_demand(model_id: int, color_id: int, weekly_demand: float):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM demand_settings WHERE model_id=? AND color_id=?", (model_id, color_id))
    row = c.fetchone()
    if row:
        c.execute("UPDATE demand_settings SET weekly_demand=? WHERE id=?", (weekly_demand, row["id"]))
    else:
        c.execute("INSERT INTO demand_settings (model_id,color_id,weekly_demand) VALUES (?,?,?)", (model_id, color_id, weekly_demand))
    conn.commit()
    conn.close()


# ─── Orders ────────────────────────────────────────────────────────────────────
def get_orders() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM orders ORDER BY priority, deadline").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_order_lines(order_id: int = None) -> list:
    conn = get_conn()
    if order_id:
        rows = conn.execute("""
            SELECT ol.*, m.name AS model_name, c.name AS color_name
            FROM order_lines ol
            JOIN chair_models m ON ol.model_id = m.id
            JOIN colors c ON ol.color_id = c.id
            WHERE ol.order_id=?
        """, (order_id,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT ol.*, m.name AS model_name, c.name AS color_name
            FROM order_lines ol
            JOIN chair_models m ON ol.model_id = m.id
            JOIN colors c ON ol.color_id = c.id
        """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_order(order_ref, customer_name, order_date, deadline, priority, status, destination, notes, order_id=None) -> int:
    conn = get_conn()
    c = conn.cursor()
    if order_id:
        c.execute(
            "UPDATE orders SET order_ref=?,customer_name=?,order_date=?,deadline=?,priority=?,status=?,destination=?,notes=? WHERE id=?",
            (order_ref, customer_name, order_date, deadline, priority, status, destination, notes, order_id),
        )
        conn.commit()
        conn.close()
        return order_id
    else:
        c.execute(
            "INSERT INTO orders (order_ref,customer_name,order_date,deadline,priority,status,destination,notes) VALUES (?,?,?,?,?,?,?,?)",
            (order_ref, customer_name, order_date, deadline, priority, status, destination, notes),
        )
        oid = c.lastrowid
        conn.commit()
        conn.close()
        return oid


def delete_order(order_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM orders WHERE id=?", (order_id,))
    conn.commit()
    conn.close()


def save_order_lines(order_id: int, lines: list):
    """lines = [{'model_id':..,'color_id':..,'quantity':..}]"""
    conn = get_conn()
    conn.execute("DELETE FROM order_lines WHERE order_id=?", (order_id,))
    conn.executemany(
        "INSERT INTO order_lines (order_id,model_id,color_id,quantity) VALUES (?,?,?,?)",
        [(order_id, l["model_id"], l["color_id"], l["quantity"]) for l in lines],
    )
    conn.commit()
    conn.close()


# ─── Logistics ─────────────────────────────────────────────────────────────────
def get_logistics_centers() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM logistics_centers ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_logistics_center(name, country, city, capacity_m3, fixed_cost_eur, center_id=None) -> int:
    conn = get_conn()
    c = conn.cursor()
    if center_id:
        c.execute("UPDATE logistics_centers SET name=?,country=?,city=?,capacity_m3=?,fixed_cost_eur=? WHERE id=?",
                  (name, country, city, capacity_m3, fixed_cost_eur, center_id))
        conn.commit(); conn.close()
        return center_id
    c.execute("INSERT INTO logistics_centers (name,country,city,capacity_m3,fixed_cost_eur) VALUES (?,?,?,?,?)",
              (name, country, city, capacity_m3, fixed_cost_eur))
    cid = c.lastrowid
    conn.commit(); conn.close()
    return cid


def delete_logistics_center(center_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM logistics_centers WHERE id=?", (center_id,))
    conn.commit(); conn.close()


def get_transport_routes(center_id: int = None) -> list:
    conn = get_conn()
    if center_id:
        rows = conn.execute("""
            SELECT tr.*, lc.name AS center_name
            FROM transport_routes tr JOIN logistics_centers lc ON tr.center_id=lc.id
            WHERE tr.center_id=?
        """, (center_id,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT tr.*, lc.name AS center_name
            FROM transport_routes tr JOIN logistics_centers lc ON tr.center_id=lc.id
        """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_transport_route(center_id, destination, transport_time_days, shared_truck,
                          truck_capacity_m3, cost_per_m3, departure_frequency_days,
                          transport_mode, route_id=None) -> int:
    conn = get_conn()
    c = conn.cursor()
    if route_id:
        c.execute("""UPDATE transport_routes SET center_id=?,destination=?,transport_time_days=?,
            shared_truck=?,truck_capacity_m3=?,cost_per_m3=?,departure_frequency_days=?,transport_mode=?
            WHERE id=?""",
            (center_id, destination, transport_time_days, shared_truck,
             truck_capacity_m3, cost_per_m3, departure_frequency_days, transport_mode, route_id))
        conn.commit(); conn.close()
        return route_id
    c.execute("""INSERT INTO transport_routes
        (center_id,destination,transport_time_days,shared_truck,truck_capacity_m3,cost_per_m3,departure_frequency_days,transport_mode)
        VALUES (?,?,?,?,?,?,?,?)""",
        (center_id, destination, transport_time_days, shared_truck,
         truck_capacity_m3, cost_per_m3, departure_frequency_days, transport_mode))
    rid = c.lastrowid
    conn.commit(); conn.close()
    return rid


def delete_transport_route(route_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM transport_routes WHERE id=?", (route_id,))
    conn.commit(); conn.close()
