"""
Diagnostic helpers for EQE loading and parsing.
"""

import ipywidgets as widgets
from IPython.display import clear_output


def diagnose_eqe_loading(data_manager):
    """Print a detailed diagnostic report for EQE loading/parsing state."""
    print("=" * 70)
    print("EQE LOADING DIAGNOSTIC")
    print("=" * 70)

    diag = getattr(data_manager, "last_diagnostics", {}) or {}
    if not diag:
        print("No diagnostic snapshot available yet. Load a batch first.")
        return

    # --- Basic counts ---
    for key in ["batch_count", "api_source", "sample_ids_total", "sample_ids_unique"]:
        if key in diag:
            print(f"{key}: {diag[key]}")

    if diag.get("sample_ids_preview"):
        print("sample_ids_preview:")
        for sid in diag["sample_ids_preview"]:
            print(f"  - {sid}")

    # --- Strategy results ---
    print("\n--- API Search Strategies ---")
    print("Strategy 1 (entry_references):")
    print(f"  default EQE type : {diag.get('strategy1_default_samples', '?')} samples found")
    print(f"  GammaBox EQE type: {diag.get('strategy1_gamma_samples', '?')} samples found")

    print("Strategy 2 (results.eln.lab_ids + entry_type):")
    for etype, status in (diag.get("strategy2_http_status") or {}).items():
        raw = (diag.get("strategy2_raw_count") or {}).get(etype, 0)
        short = etype.split("_")[-1]
        print(f"  {short}: HTTP {status}, raw entries returned: {raw}")
    print(f"  new entries added: {diag.get('strategy2_new_entries', 0)}")
    if diag.get("strategy2_parse_errors"):
        print(f"  parse errors: {diag['strategy2_parse_errors'][:3]}")

    print("Strategy 3 (upload_id + entry_type):")
    print(f"  batch lookup HTTP: {diag.get('strategy3_batch_http_status', '?')}")
    print(f"  upload_ids found : {diag.get('strategy3_upload_ids', [])}")
    for etype, status in (diag.get("strategy3_http_status") or {}).items():
        raw = (diag.get("strategy3_raw_count") or {}).get(etype, 0)
        short = etype.split("_")[-1]
        print(f"  {short}: HTTP {status}, raw entries returned: {raw}")
    print(f"  new entries added: {diag.get('strategy3_new_entries', 0)}")
    if diag.get("strategy3_exception"):
        print(f"  exception: {diag['strategy3_exception']}")
    if diag.get("strategy3_parse_errors"):
        print(f"  parse errors: {diag['strategy3_parse_errors'][:3]}")

    print(f"\neqe_samples_found (total after all strategies): {diag.get('eqe_samples_found', 0)}")

    # --- Entry structure inspection ---
    if diag.get("entry_structure_sample"):
        print("\n--- Entry Structure (first entries) ---")
        for s in diag["entry_structure_sample"]:
            print(f"  sample_id  : {s['sample_id']}")
            print(f"  entry_type : {s['entry_type']}")
            print(f"  mainfile   : {s['mainfile']}")
            print(f"  top keys   : {s['top_level_keys']}")
            print(
                f"  eqe_data   : key present={s['has_eqe_data_key']}, type={s['eqe_data_type']}, len={s['eqe_data_len']}"
            )
            print()

    # --- Parsing results ---
    print("--- Parsing Results ---")
    for key in [
        "total_entries",
        "entries_without_eqe_data",
        "total_measurements_seen",
        "parsed_measurements",
        "dropped_measurements",
    ]:
        if key in diag:
            print(f"{key}: {diag[key]}")

    if diag.get("entry_types_detected"):
        print("entry_types_detected:")
        for et in diag["entry_types_detected"]:
            print(f"  - {et}")

    if diag.get("entry_names_preview"):
        print("entry_names_preview:")
        for name in diag["entry_names_preview"]:
            print(f"  - {name}")

    if diag.get("inferred_sample_ids_outside_batch"):
        print("inferred_sample_ids_outside_batch:")
        for sid in diag["inferred_sample_ids_outside_batch"]:
            print(f"  - {sid}")

    if diag.get("dropped_reasons"):
        print("\nDropped measurement reasons:")
        for reason, count in diag["dropped_reasons"].items():
            print(f"  - {reason}: {count}")

    if diag.get("first_measurement_type"):
        print("\nFirst measurement structure:")
        print(f"  type: {diag['first_measurement_type']}")
    if diag.get("first_measurement_keys"):
        print(f"  keys: {diag['first_measurement_keys']}")
    if diag.get("first_measurement_value_types"):
        print("  value types:")
        for k, t in diag["first_measurement_value_types"].items():
            print(f"    {k}: {t}")

    # --- Final dataframes ---
    data = data_manager.get_data() if hasattr(data_manager, "get_data") else {}
    params = data.get("params")
    curves = data.get("curves")
    print("\n--- Final DataFrames ---")
    print(f"params rows: {0 if params is None else len(params)}")
    print(f"curves rows: {0 if curves is None else len(curves)}")

    if (params is None or params.empty) and diag.get("eqe_samples_found", 0) == 0:
        print("\n[!] No EQE entries found at all.")
        print("    Check Strategy results above to identify which lookup failed.")
        print("    Common fixes:")
        print("    - entry_type name may differ (check NOMAD entry type in upload)")
        print("    - EQE files not uploaded in same upload as batch entry")
        print("    - results.eln.lab_ids not populated for this entry type")
    elif (params is None or params.empty) and diag.get("entries_without_eqe_data", 0) > 0:
        print("\n[!] Entries found but all lack 'eqe_data' key.")
        print("    Check 'top keys' in Entry Structure above.")
        print("    The curve arrays may be stored under a different key name.")

    print("=" * 70)


def diagnose_multijunction(app):
    """
    Print a detailed diagnostic report for multijunction sub-cell grouping.

    This checks whether top/mid/bottom sub-cells are correctly recognised and
    whether their plot_group values actually match so they end up in the same
    colour group in the plot.
    """
    import pandas as pd

    print("=" * 70)
    print("MULTIJUNCTION GROUPING DIAGNOSTIC")
    print("=" * 70)

    # ── 1. Raw params from data manager ──────────────────────────────────────
    data = app.data_manager.get_data() if hasattr(app, "data_manager") else {}
    params_raw = data.get("filtered_params", data.get("params", None))
    if params_raw is None or params_raw.empty:
        print("[!] No params loaded yet. Load a batch first.")
        return

    print(f"\nTotal rows in params_df: {len(params_raw)}")

    if "multijunction_position" not in params_raw.columns:
        print("[!] Column 'multijunction_position' is MISSING from params_df.")
        print("    This means the data_manager did not parse it at all.")
        print("    Available columns:", list(params_raw.columns))
        return

    # Normalise to plain strings — handle both float NaN and literal "nan"/"None" strings
    def _norm_pos(v):
        if v is None:
            return ""
        s = str(v).strip()
        return "" if s.lower() in ("nan", "none", "") else s

    pos_col = params_raw["multijunction_position"].map(_norm_pos)
    pos_counts = pos_col.value_counts(dropna=False)
    print("\nmultijunction_position value counts (raw params, NaN→empty):")
    for val, cnt in pos_counts.items():
        label = repr(val) if val == "" else val
        print(f"  {label!r:20s} : {cnt}")

    has_any_mj = pos_col.ne("").any()
    if not has_any_mj:
        print("\n[!] ALL multijunction_position values are empty strings.")
        print("    Either the NOMAD entries are truly SJ, or the field is not")
        print("    populated in the archive JSON. Check entry_data.get('multijunction_position')")
        print("    in data_manager.py line ~270.")

    # ── 2. Built plot_group values (what the plotter actually sees) ──────────
    try:
        filtered_params, _ = app._build_plot_dataframe()
    except Exception as e:
        print(f"\n[!] _build_plot_dataframe() raised: {e}")
        filtered_params = params_raw.copy()
        if "plot_group" not in filtered_params.columns:
            filtered_params["plot_group"] = filtered_params.get("sample_id", "?")

    print(f"\nTotal rows in filtered_params: {len(filtered_params)}")

    key_cols = [
        c
        for c in [
            "sample_id",
            "entry_idx",
            "measurement_idx",
            "pixel",
            "cycle",
            "multijunction_position",
            "plot_group",
            "entry_name",
        ]
        if c in filtered_params.columns
    ]
    view = filtered_params[key_cols].copy()

    print("\nPer-entry key columns (all rows):")
    print(view.to_string(index=False))

    # ── 3. plot_group × position matrix ──────────────────────────────────────
    print("\n--- plot_group → multijunction_position mapping ---")
    if (
        "multijunction_position" in filtered_params.columns
        and "plot_group" in filtered_params.columns
    ):
        fp2 = filtered_params.copy()
        fp2["_pos_norm"] = fp2["multijunction_position"].map(_norm_pos)
        grp = (
            fp2.groupby("plot_group", dropna=False)["_pos_norm"]
            .apply(lambda s: sorted(s.unique().tolist()))
            .reset_index()
        )
        grp.columns = ["plot_group", "positions_in_group"]
        for _, row in grp.iterrows():
            positions = row["positions_in_group"]
            nonempty = [p for p in positions if p]
            if len(nonempty) > 1:
                status = "✓ MULTI-JUNCTION (will be plotted together)"
            elif len(nonempty) == 1:
                status = f"  single position '{nonempty[0]}' — sub-cell WITHOUT partner"
            else:
                status = "  SJ / no position info"
            print(f"  plot_group={row['plot_group']!r:40s}  positions={positions}  → {status}")
    else:
        print("  'plot_group' or 'multijunction_position' column missing in filtered_params.")

    # ── 4. Hint: what would make sub-cells share a plot_group ────────────────
    if has_any_mj:
        fp3 = filtered_params.copy()
        fp3["_pos_norm"] = (
            fp3["multijunction_position"].map(_norm_pos)
            if "multijunction_position" in fp3.columns
            else ""
        )
        mj_rows = fp3[fp3["_pos_norm"].ne("")]
        isolated = (
            mj_rows.groupby("plot_group").filter(lambda g: g["_pos_norm"].ne("").sum() == 1)
            if not mj_rows.empty
            else pd.DataFrame()
        )
        if not isolated.empty:
            print("\n[!] These sub-cell entries have NO partner in their plot_group —")
            print("    they will be plotted alone instead of together:")
            iso_cols = [
                c
                for c in ["sample_id", "pixel", "cycle", "_pos_norm", "plot_group"]
                if c in isolated.columns
            ]
            print(
                isolated[iso_cols]
                .rename(columns={"_pos_norm": "multijunction_position"})
                .to_string(index=False)
            )
            print("\n    Likely cause: the plot_group string differs between sub-cells.")
            print("    Check whether 'pixel' or 'cycle' encodes the position (e.g. 'px1_top')")
            print("    and whether the sample IDs are identical across sub-cells.")
        else:
            print("\n✓ All multijunction sub-cells have at least one partner in their plot_group.")
    else:
        # ── 5. Inspect raw NOMAD archive to understand why position is empty ──
        print("\n--- Raw NOMAD archive field inspection ---")
        print("    'multijunction_position' is empty/NaN for ALL entries.")
        print("    Checking what the raw archive actually contains...")
        raw_entries = getattr(app.data_manager, "_raw_eqe_entries", None)
        if raw_entries:
            for i, ep in enumerate(raw_entries[:4]):
                entry_data = ep if isinstance(ep, dict) else ep.get("archive", ep)
                mj_val = entry_data.get("multijunction_position", "<key missing>")
                entry_type = entry_data.get("entry_type", entry_data.get("m_def", "?"))
                mainfile = ep.get("mainfile", "?") if isinstance(ep, dict) else "?"
                print(f"  Entry {i}: type={entry_type!r}, mainfile={mainfile!r}")
                print(f"    multijunction_position = {mj_val!r}")
                top_keys = list(entry_data.keys())[:12]
                print(f"    top-level keys: {top_keys}")
        else:
            print("    _raw_eqe_entries not available on data_manager.")
            print("    Look at 'entry_structure_sample' in the EQE Diagnostics output")
            print("    and verify 'multijunction_position' appears as a top-level key.")
            diag = getattr(app.data_manager, "last_diagnostics", {}) or {}
            if diag.get("entry_structure_sample"):
                for s in diag["entry_structure_sample"]:
                    print(f"  entry: {s.get('mainfile', '?')}")
                    print(f"    top_level_keys: {s.get('top_level_keys', [])}")

    print("=" * 70)


def add_diagnostic_button_to_app(app):
    """Add a diagnostics panel for quick troubleshooting in the UI."""
    button = widgets.Button(
        description="Run EQE Diagnostics",
        button_style="warning",
        tooltip="Show EQE loading and parsing diagnostics",
        layout=widgets.Layout(width="220px"),
    )
    mj_button = widgets.Button(
        description="Multijunction Diagnostics",
        button_style="info",
        tooltip="Show multijunction sub-cell grouping diagnostics",
        layout=widgets.Layout(width="220px"),
    )
    output = widgets.Output(layout=widgets.Layout(border="1px solid #ddd", padding="8px"))

    def _on_click(_b):
        with output:
            clear_output(wait=True)
            diagnose_eqe_loading(app.data_manager)

    def _on_mj_click(_b):
        with output:
            clear_output(wait=True)
            diagnose_multijunction(app)

    button.on_click(_on_click)
    mj_button.on_click(_on_mj_click)

    return widgets.VBox(
        [
            widgets.HTML("<h4>Data Diagnostics</h4>"),
            widgets.HTML(
                "<p>Use buttons after loading to inspect parsing and multijunction grouping.</p>"
            ),
            widgets.HBox([button, mj_button]),
            output,
        ],
        layout=widgets.Layout(border="1px solid #ddd", padding="10px", margin="10px 0 0 0"),
    )
