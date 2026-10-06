"""
Utility Functions Module
Contains Excel export, file operations, and other utility functions.
Extracted from main.py for better organization.
"""

__author__ = "Edgar Nandayapa"
__institution__ = "Helmholtz-Zentrum Berlin"
__created__ = "August 2025"

import os

import openpyxl
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows


def save_full_data_frame(data):
    """
    Create and return an Excel workbook with the full dataframe.
    Simplified version that just creates a workbook without saving to file.
    """
    wb = openpyxl.Workbook()
    if wb.active is not None:
        wb.remove(wb.active)  # Remove the default sheet

    # Add main data sheet
    ws = wb.create_sheet(title="All_data")
    for r in dataframe_to_rows(data, index=True, header=True):
        ws.append(r)

    return wb


def save_combined_excel_data(path, wb, data, filtered_info, var_x, name_y, var_y, other_df):
    """Save combined data to Excel workbook with multiple sheets"""
    trash, filters = filtered_info

    # Create sheet name based on variables
    sheet_title = f"{var_y}-by-{var_x}"

    # Check if the sheet already exists and remove it
    if sheet_title in wb.sheetnames:
        del wb[sheet_title]
    ws = wb.create_sheet(title=sheet_title)

    # Insert header
    ws.append([f"Contents of boxplot for {var_y} by {var_x}"])
    ws.append([])  # Empty row

    # Process and append main data
    combined_data = data.copy()
    combined_data["_index"] = combined_data.groupby(var_x).cumcount()
    pivot_table = combined_data.pivot_table(
        index="_index", columns=var_x, values=name_y, aggfunc="mean"
    )

    for r in dataframe_to_rows(pivot_table, index=True, header=True):
        ws.append(r)

    # Add statistical summary
    next_row = ws.max_row + 3
    ws.cell(row=next_row, column=1, value="Statistical summary")
    ws.append([])

    for r in dataframe_to_rows(other_df.T, index=True, header=True):
        ws.append(r)

    # Add filtered data section
    next_row = ws.max_row + 3
    ws.cell(row=next_row, column=1, value="This is the filtered data")
    ws.append([])

    if not trash.empty:
        combined_trash = trash.copy()
        combined_trash["_index"] = combined_trash.groupby(var_x).cumcount()
        pivot_table_trash = combined_trash.pivot_table(
            index="_index", columns=var_x, values=name_y, aggfunc="mean"
        )

        for r in dataframe_to_rows(pivot_table_trash, index=True, header=True):
            ws.append(r)

    # Add filter information
    next_row = ws.max_row + 3
    filter_words = ["Only data within these limits is shown:"] + filters
    for cc, strings in enumerate(filter_words):
        ws.cell(row=next_row + cc, column=1, value=strings)

    return wb


def is_running_in_jupyter():
    """Check if code is running in Jupyter notebook"""
    try:
        from IPython.core.getipython import get_ipython

        return get_ipython() is not None
    except (ImportError, AttributeError):
        return False


def create_new_results_folder(path):
    """Create a results folder if it doesn't exist"""
    folder_path = os.path.join(path, "Results")
    try:
        os.makedirs(folder_path, exist_ok=True)
    except Exception as e:
        print(f"Warning: Could not create results folder: {e}")
        return path
    return folder_path


def clean_filename(filename):
    """Clean filename for safe saving"""
    import re

    # Remove invalid characters for filenames
    filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
    return filename


def generate_detailed_export_excel(export_df, filtered_info=None, variable_order=None):
    """
    Generate Excel workbook with detailed export data.

    Creates multiple sheets:
    - Rohdaten: All pixel-level data with filter info and champion/median markings
    - Zusammenfassung: Summary statistics per variation
    - Filter-Log: Detailed log of excluded data with reasons

    Args:
        export_df: DataFrame from export_detailed_pixel_data()
        filtered_info: Tuple of (trash_df, filter_reasons_list) for additional context
        variable_order: Optional list of 'identifier' values in the order the user
            set via the app's "Reorder Variables for Boxplots" widget. When given,
            every per-variation sheet (Zusammenfassung, Boxplot_RawData,
            Boxplot_IndexedData) lists variations in this same order, so the xlsx
            export matches the app's own plots. Any identifier present in the data
            but missing from this list is appended afterwards, in its natural order.

    Returns:
        openpyxl.Workbook object ready for saving
    """
    wb = openpyxl.Workbook()
    if wb.active is not None:
        wb.remove(wb.active)  # Remove default sheet

    # ==================== Sheet 1: Rohdaten ====================
    ws_raw = wb.create_sheet(title="Rohdaten")

    # Add header
    ws_raw.append(["DETAILED PIXEL-LEVEL DATA"])
    ws_raw.append(
        ["All measurements with filter status, filter reasons, and champion/median markings"]
    )
    ws_raw.append([])

    # Add data
    for r in dataframe_to_rows(export_df, index=False, header=True):
        ws_raw.append(r)

    # Format header row
    header_fill = PatternFill(start_color="1F3964", end_color="1F3964", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)

    for cell in ws_raw[4]:  # Row 4 is the header
        if cell.value:
            cell.fill = header_fill
            cell.font = header_font

    # Auto-adjust column widths
    for column in ws_raw.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws_raw.column_dimensions[column_letter].width = adjusted_width

    # Freeze header rows
    ws_raw.freeze_panes = "A5"

    # ==================== Sheet 2: Zusammenfassung ====================
    ws_summary = wb.create_sheet(title="Zusammenfassung")

    ws_summary.append(["SUMMARY STATISTICS PER VARIATION"])
    ws_summary.append(
        [
            "Distribution statistics per variation (Included data only) "
            "- ready to use for Origin box plots (mean, median, std dev, quartiles, whiskers)"
        ]
    )
    ws_summary.append([])

    # Group by variation/identifier
    groupby_col = "identifier" if "identifier" in export_df.columns else "sample"

    def _ordered_variations(df):
        """Variation order matching the app's 'Reorder Variables for Boxplots'
        widget (variable_order), falling back to natural appearance order."""
        actual = list(df[groupby_col].unique())
        if not variable_order:
            return actual
        actual_set = set(actual)
        ordered = [v for v in variable_order if v in actual_set]
        ordered_set = set(ordered)
        ordered += [v for v in actual if v not in ordered_set]
        return ordered

    # Same order/parameters as the app's "Boxplot - all" 2x2 grid (PCE, FF, Jsc, Voc)
    stat_params = [
        {"col": "PCE(%)", "label": "PCE(%)", "ndigits": 2, "abs": False},
        {"col": "FF(%)", "label": "FF(%)", "ndigits": 2, "abs": False},
        {"col": "Jsc(mA/cm2)", "label": "Jsc(mA/cm2)", "ndigits": 2, "abs": True},
        {"col": "Voc(V)", "label": "Voc(V)", "ndigits": 3, "abs": False},
    ]
    stat_names = [
        "N",
        "Mean",
        "Median",
        "StdDev",
        "SEM",
        "Min",
        "Max",
        "Q1 (25%)",
        "Q3 (75%)",
        "IQR",
        "Whisker Low",
        "Whisker High",
        "CV(%)",
    ]

    def _box_stats(series, ndigits):
        """Compute the statistics needed for an Origin/Tukey-style box plot."""
        s = pd.to_numeric(series, errors="coerce").dropna()
        n = int(s.count())
        if n == 0:
            return [0] + [None] * (len(stat_names) - 1)

        mean = s.mean()
        median = s.median()
        std = s.std(ddof=1) if n > 1 else 0.0
        sem = std / (n**0.5) if n > 1 else 0.0
        s_min = s.min()
        s_max = s.max()
        q1 = s.quantile(0.25)
        q3 = s.quantile(0.75)
        iqr = q3 - q1
        whisker_low = max(s_min, q1 - 1.5 * iqr)
        whisker_high = min(s_max, q3 + 1.5 * iqr)
        cv = (std / mean * 100) if mean not in (0, None) else None

        values = [
            n,
            mean,
            median,
            std,
            sem,
            s_min,
            s_max,
            q1,
            q3,
            iqr,
            whisker_low,
            whisker_high,
            cv,
        ]
        return [
            round(v, ndigits) if isinstance(v, (int, float)) and v is not None else v
            for v in values
        ]

    # Header row 1: parameter name spanning its block of stat columns
    base_cols = ["Variation", "Total Pixels", "Included", "Excluded"]
    header_block_row = list(base_cols) + [""] * (len(stat_params) * len(stat_names))
    ws_summary.append(header_block_row)
    header_row1_idx = ws_summary.max_row

    # Header row 2: the stat names, repeated per parameter
    header_row2 = list(base_cols)
    for p in stat_params:
        header_row2.extend([f"{p['label']} {name}" for name in stat_names])
    ws_summary.append(header_row2)
    header_row2_idx = ws_summary.max_row

    # Fill in parameter labels + merge over their block in header row 1
    start_col = len(base_cols) + 1
    for p in stat_params:
        end_col = start_col + len(stat_names) - 1
        ws_summary.cell(row=header_row1_idx, column=start_col, value=p["label"])
        ws_summary.merge_cells(
            start_row=header_row1_idx,
            start_column=start_col,
            end_row=header_row1_idx,
            end_column=end_col,
        )
        start_col = end_col + 1

    for variation in _ordered_variations(export_df):
        var_data = export_df[export_df[groupby_col] == variation]
        included_data = var_data[var_data["filter_status"] == "Included"]
        included = len(included_data)
        excluded = len(var_data[var_data["filter_status"] == "Excluded"])

        row = [str(variation), len(var_data), included, excluded]
        for p in stat_params:
            if p["col"] in included_data.columns:
                series = included_data[p["col"]].abs() if p["abs"] else included_data[p["col"]]
                row.extend(_box_stats(series, p["ndigits"]))
            else:
                row.extend([None] * len(stat_names))
        ws_summary.append(row)

    # Format header rows
    for header_row in (ws_summary[header_row1_idx], ws_summary[header_row2_idx]):
        for cell in header_row:
            if cell.value:
                cell.fill = header_fill
                cell.font = header_font

    ws_summary.freeze_panes = ws_summary.cell(
        row=header_row2_idx + 1, column=len(base_cols) + 1
    ).coordinate

    # Auto-adjust column widths
    for column in ws_summary.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 30)
        ws_summary.column_dimensions[column_letter].width = adjusted_width

    # ==================== Sheet: Boxplot_RawData ====================
    # Wide/indexed format (one column per variation, per parameter block) ready
    # to paste straight into Origin for a "raw data by column group" box chart -
    # matching the app's "Boxplot - all - by Variation" 2x2 grid (PCE, FF, Jsc, Voc).
    ws_raw_box = wb.create_sheet(title="Boxplot_RawData")

    ws_raw_box.append(["RAW DATA FOR ORIGIN BOX PLOTS (grouped by Variation)"])
    ws_raw_box.append(
        [
            "Included data only. Jsc shown as absolute value (matches the app boxplot). "
            "Forward + Reverse combined. Blank cells are padding (ragged group sizes)."
        ]
    )
    ws_raw_box.append([])

    header_block_row2 = []
    header_row2b = []
    columns_per_param = []  # list of list-of-values per parameter, in variation order

    variations = _ordered_variations(export_df)

    for p in stat_params:
        col_name = p["col"]
        per_variation_values = []
        for variation in variations:
            var_data = export_df[export_df[groupby_col] == variation]
            included_data = var_data[var_data["filter_status"] == "Included"]
            if col_name in included_data.columns:
                series = pd.to_numeric(included_data[col_name], errors="coerce").dropna()
                if p["abs"]:
                    series = series.abs()
                per_variation_values.append(series.tolist())
            else:
                per_variation_values.append([])
        columns_per_param.append(per_variation_values)
        header_block_row2.extend([p["label"]] + [""] * (len(variations) - 1))
        header_row2b.extend([str(v) for v in variations])

    ws_raw_box.append(header_block_row2)
    raw_header_row1_idx = ws_raw_box.max_row
    ws_raw_box.append(header_row2b)
    raw_header_row2_idx = ws_raw_box.max_row

    # Merge parameter label across its block of variation columns
    start_col = 1
    for p, per_variation_values in zip(stat_params, columns_per_param):
        end_col = start_col + len(variations) - 1
        if end_col > start_col:
            ws_raw_box.merge_cells(
                start_row=raw_header_row1_idx,
                start_column=start_col,
                end_row=raw_header_row1_idx,
                end_column=end_col,
            )
        start_col = end_col + 1

    # Write the ragged data columns, padded with blanks
    max_len = max(
        (len(vals) for per_variation_values in columns_per_param for vals in per_variation_values),
        default=0,
    )
    for row_idx in range(max_len):
        row = []
        for per_variation_values in columns_per_param:
            for vals in per_variation_values:
                row.append(vals[row_idx] if row_idx < len(vals) else None)
        ws_raw_box.append(row)

    for header_row in (ws_raw_box[raw_header_row1_idx], ws_raw_box[raw_header_row2_idx]):
        for cell in header_row:
            if cell.value:
                cell.fill = header_fill
                cell.font = header_font

    ws_raw_box.freeze_panes = ws_raw_box.cell(row=raw_header_row2_idx + 1, column=2).coordinate

    for column in ws_raw_box.columns:
        column_letter = column[0].column_letter
        ws_raw_box.column_dimensions[column_letter].width = 14

    # ==================== Sheet: Boxplot_IndexedData ====================
    # Long/indexed format (one row per included measurement) for Origin's
    # nested indexed box chart (plot_gboxindexed): Variation (outer group) x
    # Direction (inner group) x each parameter's value. Unlike Boxplot_RawData
    # this needs no column padding, and lets Origin pair Reverse/Forward boxes
    # under one shared Variation tick.
    ws_idx = wb.create_sheet(title="Boxplot_IndexedData")

    ws_idx.append(["INDEXED DATA FOR ORIGIN NESTED BOX PLOTS (Variation x Direction)"])
    ws_idx.append(
        [
            "Included data only. Jsc shown as absolute value (matches the app boxplot). "
            'One row per measurement. Variation is "identifier" with the batch prefix '
            'stripped (text after the first "&", matching how the app itself derives the '
            "variation name). Rows are ordered Reverse before Forward within each variation."
        ]
    )
    ws_idx.append([])

    idx_header = ["Variation", "Direction"] + [p["label"] for p in stat_params]
    ws_idx.append(idx_header)
    idx_header_row = ws_idx.max_row

    def _display_variation(v):
        s = str(v)
        return s.split("&", 1)[1] if "&" in s else s

    has_direction = "direction" in export_df.columns
    direction_order = ["Reverse", "Forward"] if has_direction else [None]

    for variation in _ordered_variations(export_df):
        var_data = export_df[export_df[groupby_col] == variation]
        included_data = var_data[var_data["filter_status"] == "Included"]
        display_name = _display_variation(variation)

        for direction in direction_order:
            dir_data = (
                included_data[included_data["direction"] == direction]
                if has_direction
                else included_data
            )

            for _, row_data in dir_data.iterrows():
                row = [display_name, direction if has_direction else "N/A"]
                for p in stat_params:
                    val = row_data.get(p["col"])
                    if pd.notna(val) and p["abs"]:
                        val = abs(val)
                    row.append(val)
                ws_idx.append(row)

    for cell in ws_idx[idx_header_row]:
        if cell.value:
            cell.fill = header_fill
            cell.font = header_font

    ws_idx.freeze_panes = ws_idx.cell(row=idx_header_row + 1, column=1).coordinate

    for column in ws_idx.columns:
        column_letter = column[0].column_letter
        ws_idx.column_dimensions[column_letter].width = 16

    # ==================== Sheet 3: Filter-Log ====================
    ws_log = wb.create_sheet(title="Filter-Log")

    ws_log.append(["FILTER LOG - EXCLUDED DATA"])
    ws_log.append(["Details of all measurements that were filtered out and reasons"])
    ws_log.append([])

    excluded_data = export_df[export_df["filter_status"] == "Excluded"].copy()

    if not excluded_data.empty:
        # Select relevant columns for the log
        log_cols = [
            "sample",
            "cell",
            "px_number",
            "cycle_number",
            "Voc(V)",
            "Jsc(mA/cm2)",
            "FF(%)",
            "PCE(%)",
            "filter_reason",
            "identifier",
        ]
        log_cols = [col for col in log_cols if col in excluded_data.columns]

        log_df = excluded_data[log_cols].copy()

        for r in dataframe_to_rows(log_df, index=False, header=True):
            ws_log.append(r)

        # Format header row
        for cell in ws_log[4]:
            if cell.value:
                cell.fill = header_fill
                cell.font = header_font

        # Auto-adjust column widths
        for column in ws_log.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws_log.column_dimensions[column_letter].width = adjusted_width

        # Freeze header rows
        ws_log.freeze_panes = "A5"
    else:
        ws_log.append(["No excluded data - all measurements passed filters"])

    # ==================== Sheet 4: Filter-Gründe Summary ====================
    ws_reasons = wb.create_sheet(title="Filter-Gruende")

    ws_reasons.append(["FILTER REASONS SUMMARY"])
    ws_reasons.append(["Count of measurements excluded for each reason"])
    ws_reasons.append([])

    if not excluded_data.empty and "filter_reason" in excluded_data.columns:
        reason_counts = excluded_data["filter_reason"].value_counts()

        ws_reasons.append(["Reason", "Count", "Percentage"])
        total_excluded = len(excluded_data)

        for reason, count in reason_counts.items():
            percentage = round((count / total_excluded) * 100, 1) if total_excluded > 0 else 0
            ws_reasons.append([str(reason), count, f"{percentage}%"])
    else:
        ws_reasons.append(["No filter reasons recorded"])

    # Format header row
    for cell in ws_reasons[4]:
        if cell.value:
            cell.fill = header_fill
            cell.font = header_font

    # Auto-adjust column widths
    for column in ws_reasons.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 40)
        ws_reasons.column_dimensions[column_letter].width = adjusted_width

    return wb
