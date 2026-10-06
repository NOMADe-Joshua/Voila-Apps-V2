"""
Plot manager for EQE curves.
"""

import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import integrate as sp_integrate

# ---------------------------------------------------------------------------
# AM1.5G spectrum — loaded once, cached at module level
# File format: [empty], energy (eV), photon flux (photons/cm²/s/eV)
# ---------------------------------------------------------------------------
_AM15G_ENERGY = None  # eV, ascending
_AM15G_FLUX = None  # photons/cm²/s/eV


def _get_am15g():
    global _AM15G_ENERGY, _AM15G_FLUX
    if _AM15G_ENERGY is None:
        _dir = os.path.dirname(os.path.realpath(__file__))
        _fpath = os.path.join(_dir, "AM15G.dat.txt")
        _df = pd.read_csv(_fpath, header=None)
        _AM15G_ENERGY = np.array(_df[_df.columns[1]], dtype=float)
        _AM15G_FLUX = np.array(_df[_df.columns[2]], dtype=float)
    return _AM15G_ENERGY, _AM15G_FLUX


def _compute_cumulative_jsc_am15g(x_vals, eqe_vals, jsc_total, x_col):
    """
    Compute cumulative Jsc(λ) weighted by the AM1.5G photon flux.

    The curve grows from short wavelength (UV) to long wavelength (IR),
    ending at jsc_total. Returns (x_out, cum_mA) aligned with x_vals order.
    """
    q = 1.602e-19
    energy_AM15, flux_AM15_per_eV = _get_am15g()

    x_arr = np.array(x_vals, dtype=float)
    eqe = np.array(eqe_vals, dtype=float)

    # Convert to wavelength (nm) for integration
    if "energy" in x_col.lower():
        wl_nm = 1239.8 / x_arr  # eV → nm
    else:
        wl_nm = x_arr.copy()  # already nm

    # Sort by ascending wavelength (UV → IR)
    sort_idx = np.argsort(wl_nm)
    wl_sorted = wl_nm[sort_idx]
    eqe_sorted = eqe[sort_idx]

    # Convert AM1.5G flux from per-eV to per-nm:
    #   Φ(λ) [/nm] = Φ(E) [/eV] × |dE/dλ| = Φ(E) × 1239.8 / λ²
    # energy_AM15 is ascending eV → wavelength is descending nm
    wl_am15 = 1239.8 / energy_AM15  # nm, descending
    flux_per_nm = flux_AM15_per_eV * 1239.8 / wl_am15**2  # photons/cm²/s/nm
    # Sort to ascending wavelength for np.interp
    order = np.argsort(wl_am15)
    wl_am15_asc = wl_am15[order]
    flux_nm_asc = flux_per_nm[order]

    # Interpolate AM1.5G to EQE wavelength grid
    flux_interp = np.interp(wl_sorted, wl_am15_asc, flux_nm_asc, left=0.0, right=0.0)

    # Cumulative trapezoid: ∫₀^λ EQE(λ') Φ(λ') dλ'  [photons/cm²/s]
    # × q [C] × 1e3 → mA/cm²
    integrand = eqe_sorted * flux_interp
    cum_raw = sp_integrate.cumulative_trapezoid(integrand, wl_sorted, initial=0.0)
    cum_mA = cum_raw * q * 1e3  # mA/cm²

    # Scale so the curve ends exactly at jsc_total
    if cum_mA[-1] > 0:
        cum_mA = cum_mA * (jsc_total / cum_mA[-1])

    # Restore original order (matching x_vals)
    inv_idx = np.empty_like(sort_idx)
    inv_idx[sort_idx] = np.arange(len(sort_idx))
    cum_out = cum_mA[inv_idx]

    return x_arr, cum_out


def _compute_group_stats(x_grid, curves_interp, stats_mode):
    df = pd.DataFrame(curves_interp)
    if stats_mode == "mean_std":
        center = df.mean(axis=0)
        low = center - df.std(axis=0)
        high = center + df.std(axis=0)
    else:
        center = df.median(axis=0)
        low = df.quantile(0.25, axis=0, interpolation="linear")
        high = df.quantile(0.75, axis=0, interpolation="linear")

    return pd.DataFrame(
        {"x": x_grid, "center": center.values, "low": low.values, "high": high.values}
    )


_ANNOTATION_FMT = {
    "bandgap_eqe": ("{:.2f}", "eV"),
    "integrated_jsc": ("{:.1f}", "mA/cm²"),
    "integrated_j0rad": ("{:.2e}", "mA/cm²"),
    "voc_rad": ("{:.3f}", "V"),
    "urbach_energy": ("{:.1f}", "meV"),
}


def _format_ann_val(col, val, unit, scale):
    if pd.isna(val):
        return None
    v = float(val) * scale
    fmt = _ANNOTATION_FMT.get(col, ("{:.3g}", ""))[0]
    return f"{fmt.format(v)}{(' ' + unit) if unit else ''}"


def _build_legend_annotation(params_rows, annotate_cols):
    """Return a legend suffix like '<br>Eg: 1.23 eV, Jsc: 20.1 mA/cm\u00b2' computed from mean column values."""
    if not annotate_cols or params_rows is None or params_rows.empty:
        return ""
    parts = []
    for col, abbr, unit, scale in annotate_cols:
        if col not in params_rows.columns:
            continue
        vals = pd.to_numeric(params_rows[col], errors="coerce").dropna()
        if vals.empty:
            continue
        s = _format_ann_val(col, vals.mean(), unit, scale)
        if s is not None:
            parts.append(f"{abbr}: {s}")
    return ("<br>" + ", ".join(parts)) if parts else ""


def _build_mj_legend_annotation(pos_params_list, annotate_cols):
    """
    Build a multi-position annotation for MJ entries.

    pos_params_list: list of (pos_str, params_df)  sorted top → mid → bottom.
    Returns e.g. '<br>Eg: 1.60, 1.10 eV<br>Jsc: 14.2, 18.5 mA/cm\u00b2'
    (one value per sub-cell per quantity, one line per quantity).
    """
    if not annotate_cols or not pos_params_list:
        return ""
    lines = []
    for col, abbr, unit, scale in annotate_cols:
        values = []
        for _pos, prows in pos_params_list:
            if prows is None or prows.empty or col not in prows.columns:
                continue
            vals = pd.to_numeric(prows[col], errors="coerce").dropna()
            if vals.empty:
                continue
            fmt = _ANNOTATION_FMT.get(col, ("{:.3g}", ""))[0]
            values.append(fmt.format(float(vals.mean()) * scale))
        if not values:
            continue
        unit_str = f" {unit}" if unit else ""
        lines.append(f"{abbr}: {', '.join(values)}{unit_str}")
    return ("<br>" + "<br>".join(lines)) if lines else ""


def _positions_label(positions):
    """Return ' (top, mid, bottom)' string for the non-empty positions present, in logical order."""
    order = {"top": 0, "mid": 1, "middle": 1, "bottom": 2}
    sorted_pos = sorted([p for p in positions if p], key=lambda p: order.get(p, 9))
    return f" ({', '.join(sorted_pos)})" if sorted_pos else ""


def create_eqe_figure(
    curves_df,
    params_df,
    x_mode="wavelength",
    group_curves=True,
    stats_mode="median_iqr",
    colors=None,
    font_size_axis=12,
    font_size_legend=10,
    line_width=2.0,
    annotate_cols=None,
    show_eg_vline=False,
    vline_width=1.5,
    show_jsc_cumulative=False,
    jsc_line_width=1.5,
):
    """Create an EQE plotly figure from filtered curve and parameter tables."""
    if curves_df is None or curves_df.empty:
        return None

    x_col = "wavelength_array" if x_mode == "wavelength" else "photon_energy_array"
    x_title = "Wavelength (nm)" if x_mode == "wavelength" else "Photon Energy (eV)"

    # Include multijunction_position if available so the plot loop can group sub-cells
    merge_cols = ["sample_id", "entry_idx", "measurement_idx", "plot_group"]
    if "multijunction_position" in params_df.columns:
        merge_cols.append("multijunction_position")

    merged = curves_df.merge(
        params_df[merge_cols],
        on=["sample_id", "entry_idx", "measurement_idx"],
        how="left",
    )

    fig = make_subplots(specs=[[{"secondary_y": True}]]) if show_jsc_cumulative else go.Figure()
    cum_jsc_traces = []  # (x_vals, y_vals, color, group_name) for secondary y-axis
    color_list = colors or [
        "rgba(93,164,214,0.9)",
        "rgba(255,144,14,0.9)",
        "rgba(44,160,101,0.9)",
        "rgba(255,65,54,0.9)",
        "rgba(79,90,117,0.9)",
    ]

    def pick_color(idx):
        return color_list[idx % len(color_list)]

    if group_curves:
        for idx, (group_name, gdf) in enumerate(merged.groupby("plot_group", dropna=False)):
            # Build curve list — each item is (key_tuple, position, curve_df)
            # key = (sample_id, entry_idx, measurement_idx), position = multijunction label or ""
            curve_list = []  # [(key_tuple, position, curve_df), ...]
            for (sid, eidx, midx), cdf in gdf.groupby(
                ["sample_id", "entry_idx", "measurement_idx"]
            ):
                cdf = cdf.dropna(subset=[x_col, "eqe_array"]).sort_values(x_col)
                if cdf.empty:
                    continue
                pos = ""
                if "multijunction_position" in cdf.columns:
                    pos_vals = cdf["multijunction_position"].dropna().unique()
                    pos = str(pos_vals[0]).strip() if len(pos_vals) > 0 else ""
                curve_list.append(((sid, eidx, midx), pos, cdf[[x_col, "eqe_array"]]))

            if not curve_list:
                continue

            color = pick_color(idx)

            # Determine if this group contains multijunction sub-cells.
            # Multijunction: group the curves by (sample_id, pixel, cycle) to find
            # devices with >1 sub-cell. If any device has multijunction positions,
            # all sub-cells belonging to the same device are rendered together.
            has_mj = any(pos != "" for _, pos, _ in curve_list)

            # Gather params rows for this group
            group_keys = pd.DataFrame(
                [
                    {"sample_id": k[0], "entry_idx": k[1], "measurement_idx": k[2]}
                    for k, _, _ in curve_list
                ]
            )
            group_params = params_df.merge(
                group_keys, on=["sample_id", "entry_idx", "measurement_idx"], how="inner"
            )

            # ---- Position ordering so top/mid/bottom are always drawn in logical order ----
            _POS_ORDER = {"top": 0, "mid": 1, "middle": 1, "bottom": 2, "": 3}

            if stats_mode == "best":
                if has_mj:
                    top_curves = [(k, pos, c) for k, pos, c in curve_list if pos in ("top", "")]
                    if not top_curves:
                        top_curves = curve_list
                    best_top_key = max(top_curves, key=lambda t: t[2]["eqe_array"].max())[0]
                    best_sample_id = best_top_key[0]

                    _POS_ORDER = {"top": 0, "mid": 1, "middle": 1, "bottom": 2, "": 3}
                    device_curves = sorted(
                        [(k, pos, c) for k, pos, c in curve_list if k[0] == best_sample_id],
                        key=lambda t: _POS_ORDER.get(t[1], 3),
                    )

                    # Build per-position params list for the annotation
                    pos_params_list = []
                    for k, pos, _ in device_curves:
                        sub_p = group_params[
                            (group_params["sample_id"] == k[0])
                            & (group_params["entry_idx"] == k[1])
                            & (group_params["measurement_idx"] == k[2])
                        ]
                        pos_params_list.append((pos, sub_p))

                    all_positions = [pos for _, pos, _ in device_curves]
                    pos_suffix = _positions_label(all_positions)
                    ann = _build_mj_legend_annotation(pos_params_list, annotate_cols)
                    legend_label = str(group_name) + pos_suffix + ann

                    first = True
                    for (k, pos, curve), (_, sub_params) in zip(device_curves, pos_params_list):
                        fig.add_scatter(
                            x=curve[x_col],
                            y=curve["eqe_array"],
                            mode="lines",
                            name=legend_label,
                            legendgroup=str(group_name),
                            showlegend=first,
                            line=dict(color=color, width=float(line_width)),
                        )
                        if show_jsc_cumulative:
                            jsc_ser = pd.to_numeric(
                                sub_params.get("integrated_jsc", pd.Series(dtype=float)),
                                errors="coerce",
                            ).dropna()
                            if not jsc_ser.empty:
                                bc = curve.sort_values(x_col).dropna(subset=["eqe_array"])
                                x_out, cum = _compute_cumulative_jsc_am15g(
                                    bc[x_col].values,
                                    bc["eqe_array"].values,
                                    float(jsc_ser.mean()),
                                    x_col,
                                )
                                cum_jsc_traces.append((x_out, cum, color, str(group_name)))
                        first = False
                else:
                    best_key, _, best_curve = max(curve_list, key=lambda t: t[2]["eqe_array"].max())
                    best_params = group_params[
                        (group_params["sample_id"] == best_key[0])
                        & (group_params["entry_idx"] == best_key[1])
                        & (group_params["measurement_idx"] == best_key[2])
                    ]
                    ann = _build_legend_annotation(best_params, annotate_cols)
                    fig.add_scatter(
                        x=best_curve[x_col],
                        y=best_curve["eqe_array"],
                        mode="lines",
                        name=str(group_name) + ann,
                        legendgroup=str(group_name),
                        line=dict(color=color, width=float(line_width)),
                    )
                    if show_jsc_cumulative:
                        jsc_ser = pd.to_numeric(
                            best_params.get("integrated_jsc", pd.Series(dtype=float)),
                            errors="coerce",
                        ).dropna()
                        if not jsc_ser.empty:
                            bc = best_curve.sort_values(x_col).dropna(subset=["eqe_array"])
                            x_out, cum = _compute_cumulative_jsc_am15g(
                                bc[x_col].values,
                                bc["eqe_array"].values,
                                float(jsc_ser.mean()),
                                x_col,
                            )
                            cum_jsc_traces.append((x_out, cum, color, str(group_name)))
                continue

            # ---- median_iqr / mean_std stats mode ----
            curves_only = [c for _, _, c in curve_list]
            min_x = max(c.iloc[:, 0].min() for c in curves_only)
            max_x = min(c.iloc[:, 0].max() for c in curves_only)
            if not np.isfinite(min_x) or not np.isfinite(max_x) or min_x >= max_x:
                continue

            x_grid = np.linspace(min_x, max_x, 500)
            interpolated = []
            for _, _, curve in curve_list:
                interpolated.append(
                    np.interp(x_grid, curve.iloc[:, 0], curve.iloc[:, 1], left=np.nan, right=np.nan)
                )

            stats_df = _compute_group_stats(x_grid, interpolated, stats_mode)
            rgba_fill = color.replace("0.9", "0.2") if "0.9" in color else "rgba(93,164,214,0.2)"
            ann = _build_legend_annotation(group_params, annotate_cols)
            legend_name = str(group_name) + ann

            fig.add_scatter(
                x=np.concatenate([stats_df["x"].values, stats_df["x"].values[::-1]]),
                y=np.concatenate([stats_df["high"].values, stats_df["low"].values[::-1]]),
                mode="lines",
                line=dict(color="rgba(255,255,255,0)", width=0),
                fill="toself",
                fillcolor=rgba_fill,
                showlegend=False,
                legendgroup=str(group_name),
                name=legend_name,
            )

            fig.add_scatter(
                x=stats_df["x"],
                y=stats_df["center"],
                mode="lines",
                name=legend_name,
                legendgroup=str(group_name),
                line=dict(color=color, width=float(line_width)),
            )
            # Cumulative Jsc (AM1.5G weighted, averaged over group curves)
            if show_jsc_cumulative:
                jsc_ser = pd.to_numeric(
                    group_params.get("integrated_jsc", pd.Series(dtype=float)), errors="coerce"
                ).dropna()
                if not jsc_ser.empty and len(interpolated) > 0:
                    jsc_mean = float(jsc_ser.mean())
                    cum_list = []
                    for y_interp in interpolated:
                        y_v = np.where(np.isfinite(y_interp), y_interp, 0.0)
                        _, c = _compute_cumulative_jsc_am15g(x_grid, y_v, jsc_mean, x_col)
                        cum_list.append(c)
                    if cum_list:
                        mean_cum = np.mean(cum_list, axis=0)
                        cum_jsc_traces.append((x_grid, mean_cum, color, str(group_name)))
    else:
        # Build a device key per entry: (plot_group, sample_id).
        # Sub-cells of the same device (same plot_group + sample_id) share a color index.
        device_order = {}  # (plot_group, sample_id) -> color_idx
        _dev_counter = 0

        _U_POS_ORDER = {"top": 0, "mid": 1, "middle": 1, "bottom": 2, "": 3}

        # Collect all entries, grouped so that same-device entries are consecutive
        ungrouped_entries = []
        for (pg, sid, eidx, midx), cdf in merged.groupby(
            ["plot_group", "sample_id", "entry_idx", "measurement_idx"]
        ):
            cdf = cdf.dropna(subset=[x_col, "eqe_array"]).sort_values(x_col)
            if cdf.empty:
                continue
            pos = ""
            if "multijunction_position" in cdf.columns:
                pos_v = cdf["multijunction_position"].dropna().unique()
                pos = str(pos_v[0]).strip() if len(pos_v) > 0 else ""
            dev_key = (pg, sid)
            if dev_key not in device_order:
                device_order[dev_key] = _dev_counter
                _dev_counter += 1
            ungrouped_entries.append((dev_key, (pg, sid, eidx, midx), pos, cdf))

        # Sort so sub-cells of the same device are adjacent and in top→mid→bottom order
        ungrouped_entries.sort(key=lambda t: (device_order[t[0]], _U_POS_ORDER.get(t[2], 3)))

        # Track which device legends have been shown, and pre-built label per device
        shown_devices = set()
        device_labels = {}  # dev_key -> full legend label string (built once per device)

        for dev_key, (pg, sid, eidx, midx), pos, cdf in ungrouped_entries:
            color_idx = device_order[dev_key]
            color = pick_color(color_idx)
            ind_params = params_df[
                (params_df["sample_id"] == sid)
                & (params_df["entry_idx"] == eidx)
                & (params_df["measurement_idx"] == midx)
            ]
            first_for_device = dev_key not in shown_devices

            # Build legend label once per device using all sub-cells for MJ annotation
            if first_for_device:
                dev_entries = [
                    (dk2, dp2, dpos2, dcdf2)
                    for dk2, dp2, dpos2, dcdf2 in ungrouped_entries
                    if dk2 == dev_key
                ]
                all_pos = [dpos2 for _, _, dpos2, _ in dev_entries]
                has_dev_mj = any(p for p in all_pos)
                if has_dev_mj:
                    _UPO2 = {"top": 0, "mid": 1, "middle": 1, "bottom": 2, "": 3}
                    sorted_dev = sorted(dev_entries, key=lambda t: _UPO2.get(t[2], 3))
                    pp_list = []
                    for _, (dpg2, dsid, deidx, dmidx), dpos, _ in sorted_dev:
                        dp2 = params_df[
                            (params_df["sample_id"] == dsid)
                            & (params_df["entry_idx"] == deidx)
                            & (params_df["measurement_idx"] == dmidx)
                        ]
                        pp_list.append((dpos, dp2))
                    ann = _build_mj_legend_annotation(pp_list, annotate_cols)
                    device_labels[dev_key] = str(pg) + _positions_label(all_pos) + ann
                else:
                    ann = _build_legend_annotation(ind_params, annotate_cols)
                    device_labels[dev_key] = str(pg) + ann

            fig.add_scatter(
                x=cdf[x_col],
                y=cdf["eqe_array"],
                mode="lines",
                name=device_labels[dev_key],
                legendgroup=str(pg),
                showlegend=first_for_device,
                line=dict(color=color, width=float(line_width)),
            )
            shown_devices.add(dev_key)
            # Cumulative Jsc (AM1.5G weighted) — one curve per sub-cell, each clipped to its own x-range
            if show_jsc_cumulative:
                jsc_ser = pd.to_numeric(
                    ind_params.get("integrated_jsc", pd.Series(dtype=float)), errors="coerce"
                ).dropna()
                if not jsc_ser.empty:
                    x_out, cum = _compute_cumulative_jsc_am15g(
                        cdf[x_col].values, cdf["eqe_array"].values, float(jsc_ser.mean()), x_col
                    )
                    cum_jsc_traces.append((x_out, cum, color, str(pg)))

    # --- Cumulative Jsc traces (secondary y-axis) ---
    # legendgroup ties them to the EQE curve so legend clicks show/hide both together.
    if show_jsc_cumulative and cum_jsc_traces:
        for x_c, y_c, col_c, grp_name in cum_jsc_traces:
            fig.add_trace(
                go.Scatter(
                    x=x_c,
                    y=y_c,
                    mode="lines",
                    line=dict(color=col_c, width=float(jsc_line_width), dash="dot"),
                    showlegend=False,
                    legendgroup=str(grp_name),
                    yaxis="y2",
                )
            )

    # --- Eg vertical lines (one per sub-cell, so MJ gets one line per junction) ---
    # Implemented as scatter traces (not shapes) so they share legendgroup with the
    # EQE curve and are toggled together on legend click.
    # EQE is normalised 0-1, so y=[0, 1] covers the full axis height without expanding it.
    if show_eg_vline and "bandgap_eqe" in params_df.columns:
        if group_curves:
            group_color_map = {
                gn: i for i, (gn, _) in enumerate(merged.groupby("plot_group", dropna=False))
            }
            for group_name, gdf in merged.groupby("plot_group", dropna=False):
                color = pick_color(group_color_map.get(group_name, 0))
                for (sid, eidx, midx), _ in gdf.groupby(
                    ["sample_id", "entry_idx", "measurement_idx"]
                ):
                    sub_p = params_df[
                        (params_df["sample_id"] == sid)
                        & (params_df["entry_idx"] == eidx)
                        & (params_df["measurement_idx"] == midx)
                    ]
                    if "bandgap_eqe" not in sub_p.columns:
                        continue
                    eg_vals = pd.to_numeric(sub_p["bandgap_eqe"], errors="coerce").dropna()
                    if eg_vals.empty:
                        continue
                    eg_ev = float(eg_vals.mean())
                    x_val = eg_ev if x_mode == "photon_energy" else 1239.8 / eg_ev
                    fig.add_scatter(
                        x=[x_val, x_val],
                        y=[0, 1.0],
                        mode="lines",
                        line=dict(color=color, width=float(vline_width), dash="dash"),
                        legendgroup=str(group_name),
                        showlegend=False,
                        hoverinfo="skip",
                    )
        else:
            _eg_device_order = {}
            _eg_dev_counter = 0
            for (pg, sid, eidx, midx), _cdf in merged.groupby(
                ["plot_group", "sample_id", "entry_idx", "measurement_idx"]
            ):
                dev_key = (pg, sid)
                if dev_key not in _eg_device_order:
                    _eg_device_order[dev_key] = _eg_dev_counter
                    _eg_dev_counter += 1
            for (pg, sid, eidx, midx), _cdf in merged.groupby(
                ["plot_group", "sample_id", "entry_idx", "measurement_idx"]
            ):
                dev_key = (pg, sid)
                ind_params = params_df[
                    (params_df["sample_id"] == sid)
                    & (params_df["entry_idx"] == eidx)
                    & (params_df["measurement_idx"] == midx)
                ]
                if "bandgap_eqe" not in ind_params.columns:
                    continue
                eg_vals = pd.to_numeric(ind_params["bandgap_eqe"], errors="coerce").dropna()
                if eg_vals.empty:
                    continue
                eg_ev = float(eg_vals.mean())
                x_val = eg_ev if x_mode == "photon_energy" else 1239.8 / eg_ev
                fig.add_scatter(
                    x=[x_val, x_val],
                    y=[0, 1.0],
                    mode="lines",
                    line=dict(
                        color=pick_color(_eg_device_order[dev_key]),
                        width=float(vline_width),
                        dash="dash",
                    ),
                    legendgroup=str(pg),
                    showlegend=False,
                    hoverinfo="skip",
                )

    fig.update_layout(
        template="plotly_white",
        xaxis_title=x_title,
        yaxis_title="External Quantum Efficiency",
        legend=dict(
            font=dict(size=font_size_legend),
            x=0.01,
            y=0.99,
            xanchor="left",
            yanchor="top",
            bgcolor="rgba(255,255,255,0.7)",
            bordercolor="rgba(0,0,0,0.15)",
            borderwidth=1,
        ),
    )
    fig.update_xaxes(titlefont=dict(size=font_size_axis), tickfont=dict(size=font_size_axis))
    if show_jsc_cumulative:
        fig.update_yaxes(
            titlefont=dict(size=font_size_axis),
            tickfont=dict(size=font_size_axis),
            rangemode="tozero",
            secondary_y=False,
        )
    else:
        fig.update_yaxes(titlefont=dict(size=font_size_axis), tickfont=dict(size=font_size_axis))
    if show_jsc_cumulative and cum_jsc_traces:
        fig.update_layout(
            yaxis2=dict(
                title="J<sub>sc</sub> (mA/cm\u00b2)",
                overlaying="y",
                side="right",
                showgrid=False,
                titlefont=dict(size=font_size_axis),
                tickfont=dict(size=font_size_axis),
                rangemode="tozero",
            )
        )

    return fig
