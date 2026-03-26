# Oflex3 Supply Chain Planning

Production planning and inventory optimization tool for **Oflex3**, a metal chair manufacturing company.

## Features

- **Parameters** — Configure production states, chair models (with per-state volumetric coefficients, MOQs, KANBAN thresholds), colors, and global settings
- **Inventory & Production** — Real-time inventory snapshot, Conservative/Standard/Lean scenario planning, LP-based storage allocation optimizer
- **Transport & Logistics** — Logistics center management, transport route matrix, delivery time estimator
- **Orders** — Customer order management, feasibility checks, conflict detection, production impact analysis
- **Dashboard** — KPI overview, stock health heatmap, upcoming actions and deadlines

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the app

```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`. Sample data (2 chair models, 3 colors, 2 orders, 1 logistics center) is pre-loaded automatically on first launch.

## Data Persistence

All data is stored in a local SQLite database `oflex3.db` in the project directory. The file is created automatically on first run.

## Project Structure

```
Oflex3_SC/
├── app.py                          # Entry point + home page
├── database.py                     # All SQLite CRUD operations
├── requirements.txt
├── README.md
├── pages/
│   ├── 1_Parameters.py             # Global settings, states, models, colors
│   ├── 2_Inventory_Production.py   # Snapshot, scenario planning, optimization
│   ├── 3_Transport_Logistics.py    # Logistics network and delivery planning
│   ├── 4_Orders.py                 # Order management and feasibility
│   └── 5_Dashboard.py             # KPIs and overview
└── utils/
    ├── calculations.py             # Business logic (targets, forecasts, feasibility)
    └── optimization.py             # scipy LP solver for storage allocation
```

## Key Concepts

| Term | Meaning |
|------|---------|
| **MOQ** | Minimum Order Quantity — minimum batch size to launch |
| **KANBAN threshold** | Reorder trigger point — alert when stock falls below |
| **Safety multiplier** | Scale factor applied to target stock (Conservative: 1.5×, Standard: 1.0×, Lean: 0.6×) |
| **Volumetric coefficient** | m³ per unit at a given production state |
| **Cumulative lead time** | Days remaining until delivery from a given state |

## Dates

All dates are displayed in **DD/MM/YYYY** format.
