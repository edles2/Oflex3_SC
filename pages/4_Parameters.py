"""
Page 1 — Parameters
Manage global settings, production states, chair models and colors.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import database as db

st.title("Parameters")
tabs = st.tabs(["Global Settings", "Production States", "Chair Models", "Colors"])


# ══════════════════════════════════════════════════════════════════
# TAB A — Global Settings
# ══════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Global Settings")
    params = db.get_params()

    col1, col2 = st.columns(2)
    with col1:
        storage = st.number_input("Total storage capacity (m³)", min_value=0.0,
                                   value=float(params.get("total_storage_m3", 500)), step=10.0)
        wpw = st.number_input("Working days per week", min_value=1, max_value=7,
                               value=int(params.get("working_days_per_week", 5)))
        wpy = st.number_input("Working weeks per year", min_value=1, max_value=52,
                               value=int(params.get("working_weeks_per_year", 52)))
    with col2:
        st.markdown("**Safety stock multipliers**")
        s_cons = st.number_input("Conservative multiplier", min_value=0.1, max_value=5.0,
                                  value=float(params.get("safety_conservative", 1.5)), step=0.1)
        s_std  = st.number_input("Standard multiplier",     min_value=0.1, max_value=5.0,
                                  value=float(params.get("safety_standard",  1.0)), step=0.1)
        s_lean = st.number_input("Lean multiplier",         min_value=0.1, max_value=5.0,
                                  value=float(params.get("safety_lean",  0.6)), step=0.1)

    if st.button("Save Global Settings", type="primary"):
        db.set_param("total_storage_m3",      storage)
        db.set_param("working_days_per_week",  wpw)
        db.set_param("working_weeks_per_year", wpy)
        db.set_param("safety_conservative",    s_cons)
        db.set_param("safety_standard",        s_std)
        db.set_param("safety_lean",            s_lean)
        st.success("Global settings saved.")
        st.rerun()


# ══════════════════════════════════════════════════════════════════
# TAB B — Production States
# ══════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Production States")
    st.caption("Define the sequential production states. Working days are auto-calculated from weeks × days/week but can be overridden.")

    params = db.get_params()
    dpw = int(params.get("working_days_per_week", 5))

    states = db.get_states()
    df = pd.DataFrame(states, columns=["id","name","order_index","leadtime_weeks","leadtime_days","can_hold_stock"])
    df = df[["id","name","leadtime_weeks","leadtime_days","can_hold_stock"]]
    df.rename(columns={
        "name":           "State Name",
        "leadtime_weeks": "Lead Time (weeks)",
        "leadtime_days":  "Lead Time (days)",
        "can_hold_stock": "Can Hold Stock",
    }, inplace=True)
    df["Can Hold Stock"] = df["Can Hold Stock"].astype(bool)

    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "id":               st.column_config.NumberColumn("ID", disabled=True),
            "State Name":       st.column_config.TextColumn("State Name"),
            "Lead Time (weeks)":st.column_config.NumberColumn("Lead Time (weeks)", min_value=0.0, format="%.1f"),
            "Lead Time (days)": st.column_config.NumberColumn("Lead Time (days)",  min_value=0.0, format="%.1f"),
            "Can Hold Stock":   st.column_config.CheckboxColumn("Can Hold Stock"),
        },
        key="states_editor",
    )

    col_a, col_b = st.columns([1,4])
    with col_a:
        if st.button("Recalculate Days from Weeks"):
            edited["Lead Time (days)"] = edited["Lead Time (weeks)"] * dpw

    with col_b:
        if st.button("Save Production States", type="primary"):
            records = []
            for _, row in edited.iterrows():
                records.append({
                    "id":              row.get("id"),
                    "name":            row["State Name"],
                    "leadtime_weeks":  row["Lead Time (weeks)"],
                    "leadtime_days":   row["Lead Time (days)"],
                    "can_hold_stock":  int(bool(row["Can Hold Stock"])),
                })
            db.save_states(records)
            st.success("Production states saved.")
            st.rerun()


# ══════════════════════════════════════════════════════════════════
# TAB C — Chair Models
# ══════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Chair Models")
    models = db.get_models()
    states = db.get_states()

    # Model list
    st.markdown("**Model List**")
    model_df = pd.DataFrame(models) if models else pd.DataFrame(columns=["id","name","description"])
    edited_models = st.data_editor(
        model_df[["id","name","description"]].rename(columns={"name":"Model Name","description":"Description"}),
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "id":          st.column_config.NumberColumn("ID", disabled=True),
            "Model Name":  st.column_config.TextColumn("Model Name"),
            "Description": st.column_config.TextColumn("Description"),
        },
        key="model_list_editor",
    )

    col_save, col_del = st.columns([1,3])
    with col_save:
        if st.button("Save Model List", type="primary"):
            for _, row in edited_models.iterrows():
                mid = row.get("id")
                if pd.isna(row["Model Name"]) or row["Model Name"] == "":
                    continue
                db.save_model(row["Model Name"], row.get("Description",""), int(mid) if mid and not pd.isna(mid) else None)
            # Delete models not in edited list
            edited_ids = set(int(r["id"]) for _, r in edited_models.iterrows() if r.get("id") and not pd.isna(r["id"]))
            for m in models:
                if m["id"] not in edited_ids:
                    db.delete_model(m["id"])
            st.success("Model list saved.")
            st.rerun()

    st.divider()

    # Per-model detail editor
    models = db.get_models()
    if not models:
        st.info("Add at least one model above to configure details.")
    else:
        selected_name = st.selectbox("Select model to configure", [m["name"] for m in models])
        model = next(m for m in models if m["name"] == selected_name)
        mid   = model["id"]

        # State params table
        st.markdown(f"**Production State Parameters — {selected_name}**")
        msp = {p["state_id"]: p for p in db.get_model_state_params(mid)}
        rows = []
        for s in states:
            p = msp.get(s["id"], {})
            rows.append({
                "state_id":        s["id"],
                "State":           s["name"],
                "Vol. Coeff (m³/unit)": p.get("volume_coeff", 0.0),
                "MOQ":             p.get("moq"),
                "KANBAN Threshold":p.get("kanban_threshold"),
                "Cycle Time (days)":p.get("cycle_time_days"),
            })
        sp_df = pd.DataFrame(rows)

        edited_sp = st.data_editor(
            sp_df,
            use_container_width=True,
            column_config={
                "state_id":           st.column_config.NumberColumn("State ID", disabled=True),
                "State":              st.column_config.TextColumn("State", disabled=True),
                "Vol. Coeff (m³/unit)": st.column_config.NumberColumn("Vol. Coeff (m³/unit)", min_value=0.0, format="%.4f"),
                "MOQ":                st.column_config.NumberColumn("MOQ"),
                "KANBAN Threshold":   st.column_config.NumberColumn("KANBAN Threshold"),
                "Cycle Time (days)":  st.column_config.NumberColumn("Cycle Time (days)", format="%.1f"),
            },
            key=f"sp_editor_{mid}",
        )

        if st.button(f"Save State Params for {selected_name}", type="primary"):
            for _, row in edited_sp.iterrows():
                db.upsert_model_state_params(
                    model_id=mid,
                    state_id=int(row["state_id"]),
                    volume_coeff=float(row["Vol. Coeff (m³/unit)"] or 0),
                    moq=int(row["MOQ"]) if row["MOQ"] and not pd.isna(row["MOQ"]) else None,
                    kanban_threshold=int(row["KANBAN Threshold"]) if row["KANBAN Threshold"] and not pd.isna(row["KANBAN Threshold"]) else None,
                    cycle_time_days=float(row["Cycle Time (days)"]) if row["Cycle Time (days)"] and not pd.isna(row["Cycle Time (days)"]) else None,
                )
            st.success(f"State params for {selected_name} saved.")

        st.divider()

        # Raw materials
        st.markdown(f"**Raw Materials — {selected_name}**")
        mats = db.get_raw_materials(mid)
        mats_df = pd.DataFrame(mats) if mats else pd.DataFrame(
            columns=["id","model_id","name","supplier","moq","unit_volume","leadtime_weeks"]
        )
        display_cols = ["id","name","supplier","moq","unit_volume","leadtime_weeks"]
        mats_df = mats_df.reindex(columns=display_cols)
        mats_df.rename(columns={
            "name":"Material Name","supplier":"Supplier","moq":"MOQ",
            "unit_volume":"Unit Volume (m³)","leadtime_weeks":"Lead Time (weeks)"
        }, inplace=True)

        edited_mats = st.data_editor(
            mats_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "id":              st.column_config.NumberColumn("ID", disabled=True),
                "Material Name":   st.column_config.TextColumn("Material Name"),
                "Supplier":        st.column_config.TextColumn("Supplier"),
                "MOQ":             st.column_config.NumberColumn("MOQ"),
                "Unit Volume (m³)":st.column_config.NumberColumn("Unit Volume (m³)", format="%.4f"),
                "Lead Time (weeks)":st.column_config.NumberColumn("Lead Time (weeks)", format="%.1f"),
            },
            key=f"mats_editor_{mid}",
        )

        if st.button(f"Save Raw Materials for {selected_name}", type="primary"):
            # Delete and re-insert
            for m in mats:
                db.delete_raw_material(m["id"])
            for _, row in edited_mats.iterrows():
                if pd.isna(row.get("Material Name")) or row.get("Material Name","") == "":
                    continue
                db.save_raw_material(
                    model_id=mid,
                    name=row["Material Name"],
                    supplier=row.get("Supplier",""),
                    moq=int(row["MOQ"]) if row.get("MOQ") and not pd.isna(row.get("MOQ")) else None,
                    unit_volume=float(row.get("Unit Volume (m³)",0) or 0),
                    leadtime_weeks=float(row.get("Lead Time (weeks)",0) or 0),
                )
            st.success(f"Raw materials for {selected_name} saved.")
            st.rerun()


# ══════════════════════════════════════════════════════════════════
# TAB D — Colors
# ══════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Colors & Painting MOQ")
    st.caption("MOQ applies per color batch at the painting stage (not per model).")

    colors = db.get_colors()
    c_df = pd.DataFrame(colors) if colors else pd.DataFrame(columns=["id","name","painting_moq"])
    c_df.rename(columns={"name":"Color Name","painting_moq":"Painting MOQ"}, inplace=True)

    edited_colors = st.data_editor(
        c_df[["id","Color Name","Painting MOQ"]],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "id":          st.column_config.NumberColumn("ID", disabled=True),
            "Color Name":  st.column_config.TextColumn("Color Name"),
            "Painting MOQ":st.column_config.NumberColumn("Painting MOQ", min_value=0),
        },
        key="color_editor",
    )

    if st.button("Save Colors", type="primary"):
        edited_ids = set()
        for _, row in edited_colors.iterrows():
            if pd.isna(row.get("Color Name")) or row.get("Color Name","") == "":
                continue
            cid = int(row["id"]) if row.get("id") and not pd.isna(row.get("id")) else None
            moq = int(row["Painting MOQ"]) if row.get("Painting MOQ") and not pd.isna(row.get("Painting MOQ")) else None
            db.save_color(row["Color Name"], moq, cid)
            if cid:
                edited_ids.add(cid)
        for c in colors:
            if c["id"] not in edited_ids:
                db.delete_color(c["id"])
        st.success("Colors saved.")
        st.rerun()
