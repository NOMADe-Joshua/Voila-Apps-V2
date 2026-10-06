"""
Plot manager for AbsPL analysis.
Creates multiple figure types from filtered spectral data.
"""

import math

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy.optimize import curve_fit
from scipy.special import voigt_profile


class AbsPLPlotManager:
    def __init__(self):
        self.font_size_axis = 14
        self.font_size_title = 16
        self.font_size_legend = 10

    def set_font_sizes(self, axis_size=None, title_size=None, legend_size=None):
        if axis_size is not None:
            self.font_size_axis = int(axis_size)
        if title_size is not None:
            self.font_size_title = int(title_size)
        if legend_size is not None:
            self.font_size_legend = int(legend_size)

    def _apply_layout(self, fig, title, x_title, y_title):
        fig.update_layout(
            title=dict(text=title, font=dict(size=self.font_size_title)),
            xaxis_title=x_title,
            yaxis_title=y_title,
            template="plotly_white",
            legend=dict(font=dict(size=self.font_size_legend)),
            margin=dict(l=80, r=40, t=70, b=70),
            width=1400,
            height=850,
        )
        fig.update_xaxes(
            showgrid=True, gridwidth=1, gridcolor="#eaecf0", tickfont=dict(size=self.font_size_axis)
        )
        fig.update_yaxes(
            showgrid=True, gridwidth=1, gridcolor="#eaecf0", tickfont=dict(size=self.font_size_axis)
        )
        return fig

    def _rgba_from_color(self, color, alpha=0.18):
        if isinstance(color, str) and color.startswith("rgb("):
            return color.replace("rgb(", "rgba(").replace(")", f",{alpha})")
        if isinstance(color, str) and color.startswith("#") and len(color) == 7:
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
            return f"rgba({r},{g},{b},{alpha})"
        return f"rgba(31,119,180,{alpha})"

    def _get_spectrum_source(self, row, y_source="auto"):
        if y_source == "luminescence_flux_density":
            return row.get("luminescence_flux_density", None)
        if y_source == "raw_spectrum_counts":
            return row.get("raw_spectrum_counts", None)

        source = row.get("spectrum_source", None)
        if source == "luminescence_flux_density":
            return row.get("luminescence_flux_density", None)
        if source == "raw_spectrum_counts":
            return row.get("raw_spectrum_counts", None)
        return row.get("intensity", row.get("y_data", None))

    def _resolve_color_value(self, row, color_by):
        if color_by not in row.index:
            return "Unknown"
        value = row.get(color_by, "Unknown")
        if pd.isna(value):
            return "Unknown"
        return str(value)

    def _ordered_values(self, values, preferred_order=None):
        items = [str(v) for v in values]
        if not preferred_order:
            return items
        seen = set(items)
        ordered = [str(v) for v in preferred_order if str(v) in seen]
        remaining = [v for v in items if v not in ordered]
        return ordered + remaining

    def _palette_dict(self):
        return {
            "Viridis": px.colors.sequential.Viridis,
            "Plasma": px.colors.sequential.Plasma,
            "Inferno": px.colors.sequential.Inferno,
            "Magma": px.colors.sequential.Magma,
            "Blues": px.colors.sequential.Blues,
            "Reds": px.colors.sequential.Reds,
            "Greens": px.colors.sequential.Greens,
            "Plotly": px.colors.qualitative.Plotly,
            "D3": px.colors.qualitative.D3,
            "Set1": px.colors.qualitative.Set1,
            "Set2": px.colors.qualitative.Set2,
        }

    def _gaussian_model(self, x_values, amplitude, center, sigma, offset):
        sigma = max(abs(float(sigma)), 1e-9)
        return amplitude * np.exp(-0.5 * ((x_values - center) / sigma) ** 2) + offset

    def _voigt_model(self, x_values, amplitude, center, sigma, gamma, offset):
        sigma = max(abs(float(sigma)), 1e-9)
        gamma = max(abs(float(gamma)), 1e-9)
        return amplitude * voigt_profile(x_values - center, sigma, gamma) + offset

    def _fit_window_from_peak(self, x_values, y_values, peak_index):
        if len(x_values) < 5:
            return 0, len(x_values) - 1

        peak_height = float(y_values[peak_index])
        baseline = float(np.nanmin(y_values))
        half_level = baseline + 0.5 * (peak_height - baseline)

        left = peak_index
        while left > 0 and y_values[left] > half_level:
            left -= 1

        right = peak_index
        while right < len(y_values) - 1 and y_values[right] > half_level:
            right += 1

        width = max(right - left, 6)
        pad = max(4, width)
        return max(0, peak_index - pad), min(len(x_values) - 1, peak_index + pad)

    def _fit_peak_profile(
        self, x_values, y_values, fit_model="gaussian", fit_mode="auto", fit_min=None, fit_max=None
    ):
        x_arr = np.asarray(x_values, dtype=float)
        y_arr = np.asarray(y_values, dtype=float)
        valid = np.isfinite(x_arr) & np.isfinite(y_arr)
        x_arr = x_arr[valid]
        y_arr = y_arr[valid]
        if x_arr.size < 5:
            return None

        if fit_min is not None or fit_max is not None:
            mask = np.ones_like(x_arr, dtype=bool)
            if fit_min is not None:
                mask &= x_arr >= float(fit_min)
            if fit_max is not None:
                mask &= x_arr <= float(fit_max)
            x_fit = x_arr[mask]
            y_fit = y_arr[mask]
            if x_fit.size < 5:
                return None
            peak_index = int(np.nanargmax(y_fit))
        else:
            peak_index_full = int(np.nanargmax(y_arr))
            left, right = self._fit_window_from_peak(x_arr, y_arr, peak_index_full)
            x_fit = x_arr[left : right + 1]
            y_fit = y_arr[left : right + 1]
            peak_index = int(np.nanargmax(y_fit))

        center_guess = float(x_fit[peak_index])
        offset_guess = float(np.nanmin(y_fit))
        height_guess = max(float(np.nanmax(y_fit) - offset_guess), 1e-9)
        width_guess = max((float(np.nanmax(x_fit)) - float(np.nanmin(x_fit))) / 6.0, 1e-3)

        try:
            if str(fit_model).lower() == "voigt":
                popt, _ = curve_fit(
                    self._voigt_model,
                    x_fit,
                    y_fit,
                    p0=[height_guess, center_guess, width_guess, width_guess, offset_guess],
                    maxfev=10000,
                )
                y_line = self._voigt_model(x_fit, *popt)
                sigma = abs(float(popt[2]))
                gamma = abs(float(popt[3]))
                fwhm = 0.5346 * (2 * gamma) + math.sqrt(
                    0.2166 * (2 * gamma) ** 2 + (2.35482 * sigma) ** 2
                )
                return {
                    "model": "Voigt",
                    "center": float(popt[1]),
                    "fwhm": float(fwhm),
                    "x_fit": x_fit,
                    "y_fit": y_line,
                    "fit_min": float(np.nanmin(x_fit)),
                    "fit_max": float(np.nanmax(x_fit)),
                }

            popt, _ = curve_fit(
                self._gaussian_model,
                x_fit,
                y_fit,
                p0=[height_guess, center_guess, width_guess, offset_guess],
                maxfev=10000,
            )
            y_line = self._gaussian_model(x_fit, *popt)
            sigma = abs(float(popt[2]))
            return {
                "model": "Gaussian",
                "center": float(popt[1]),
                "fwhm": float(2.35482 * sigma),
                "x_fit": x_fit,
                "y_fit": y_line,
                "fit_min": float(np.nanmin(x_fit)),
                "fit_max": float(np.nanmax(x_fit)),
            }
        except Exception:
            return None

    def _quality_factor_from_qfls_slope(self, slope_value):
        k_b = 8.617333262e-5
        temperature_kelvin = 298.15
        kbt = k_b * temperature_kelvin
        if slope_value is None:
            return None
        return float(slope_value) / kbt

    def _resolve_fit_range(self, fit_curve_ranges, curve_keys, default_min=None, default_max=None):
        fit_min_local = default_min
        fit_max_local = default_max
        if not isinstance(fit_curve_ranges, dict):
            return fit_min_local, fit_max_local

        for key in curve_keys:
            if key is None:
                continue
            cfg = fit_curve_ranges.get(str(key))
            if not isinstance(cfg, dict):
                continue
            if cfg.get("fit_min", None) is not None:
                fit_min_local = cfg.get("fit_min")
            if cfg.get("fit_max", None) is not None:
                fit_max_local = cfg.get("fit_max")
            break
        return fit_min_local, fit_max_local

    def _scalar_intensity_plot(
        self,
        df,
        y_col,
        group_mode="combined",
        color_by="sample_id",
        log_x=False,
        title=None,
        fit_enabled=False,
        fit_min=None,
        fit_max=None,
        measurement_type=None,
        color_scheme="Viridis",
        color_sampling="sequential",
        color_count=8,
        trace_order=None,
        fit_quality_factor=False,
    ):
        if df is None or df.empty:
            return self._apply_layout(
                go.Figure(), title or "No data", "Laser Intensity (suns)", y_col
            )

        working_df = df.copy()
        if measurement_type is not None and "measurement_type" in working_df.columns:
            working_df = working_df[
                working_df["measurement_type"].astype(str) == str(measurement_type)
            ].copy()
        if working_df.empty or y_col not in working_df.columns:
            return self._apply_layout(
                go.Figure(), title or "No data", "Laser Intensity (suns)", y_col
            )

        working_df["_x"] = pd.to_numeric(working_df.get("laser_intensity_suns"), errors="coerce")
        working_df["_y"] = pd.to_numeric(working_df.get(y_col), errors="coerce")
        working_df = working_df.dropna(subset=["_x", "_y"])
        if working_df.empty:
            return self._apply_layout(
                go.Figure(), title or "No valid values", "Laser Intensity (suns)", y_col
            )

        groups = self._split_groups(working_df, group_mode=group_mode)
        figures = []
        names = []

        for group_name, group_df in groups:
            fig = go.Figure()
            color_by_effective = (
                color_by
                if color_by in group_df.columns
                else ("sample_id" if "sample_id" in group_df.columns else None)
            )
            group_values = (
                ["All"]
                if color_by_effective is None
                else self._ordered_values(
                    group_df[color_by_effective].fillna("Unknown").astype(str).unique().tolist(),
                    trace_order,
                )
            )
            colors = self._generate_palette(color_scheme, max(1, len(group_values)), color_sampling)
            color_map = {value: colors[idx % len(colors)] for idx, value in enumerate(group_values)}

            for value in group_values:
                sub = (
                    group_df
                    if color_by_effective is None
                    else group_df[
                        group_df[color_by_effective].fillna("Unknown").astype(str) == value
                    ]
                )
                sub = sub.sort_values("_x")
                if sub.empty:
                    continue
                x_values = sub["_x"].to_numpy(dtype=float)
                y_values = sub["_y"].to_numpy(dtype=float)
                customdata = np.stack(
                    [
                        sub.get("sample_id", pd.Series([""] * len(sub))).astype(str),
                        sub.get("cycle_number", pd.Series([""] * len(sub))).astype(str),
                        sub.get("measurement_type", pd.Series([""] * len(sub))).astype(str),
                    ],
                    axis=-1,
                )

                base_name = str(value)
                fig.add_trace(
                    go.Scatter(
                        x=x_values.tolist(),
                        y=y_values.tolist(),
                        mode="lines+markers",
                        name=base_name,
                        legendgroup=base_name,
                        line=dict(width=2, color=color_map.get(value, colors[0])),
                        marker=dict(size=7, color=color_map.get(value, colors[0])),
                        customdata=customdata,
                        hovertemplate=(
                            "<b>%{legendgroup}</b><br>"
                            "Sample: %{customdata[0]}<br>"
                            "Cycle: %{customdata[1]}<br>"
                            "Type: %{customdata[2]}<br>"
                            f"Intensity: %{{x:.4g}}<br>{y_col}: %{{y:.4g}}<extra></extra>"
                        ),
                    )
                )
                base_trace = fig.data[-1]

                if fit_enabled and x_values.size >= 2 and y_values.size >= 2:
                    fit_mask = np.isfinite(x_values) & np.isfinite(y_values)
                    if fit_min is not None:
                        fit_mask &= x_values >= float(fit_min)
                    if fit_max is not None:
                        fit_mask &= x_values <= float(fit_max)
                    x_fit = x_values[fit_mask]
                    y_fit = y_values[fit_mask]
                    if x_fit.size >= 2:
                        x_for_fit = np.log(x_fit) if log_x else x_fit
                        if np.all(np.isfinite(x_for_fit)) and np.nanstd(x_for_fit) > 0:
                            slope, intercept = np.polyfit(x_for_fit, y_fit, 1)
                            x_line = np.linspace(np.nanmin(x_fit), np.nanmax(x_fit), 120)
                            y_line = slope * (np.log(x_line) if log_x else x_line) + intercept
                            qf_text = ""
                            if fit_quality_factor and log_x:
                                qf_value = self._quality_factor_from_qfls_slope(slope)
                                if qf_value is not None:
                                    base_trace.name = f"{base_name}, A={qf_value:.3f}"
                                    qf_text = f"<br>Diode quality factor A: {qf_value:.4f}"
                            fig.add_trace(
                                go.Scatter(
                                    x=x_line.tolist(),
                                    y=y_line.tolist(),
                                    mode="lines",
                                    name=f"{value} fit",
                                    legendgroup=base_name,
                                    showlegend=False,
                                    line=dict(
                                        color=color_map.get(value, colors[0]), width=2, dash="dash"
                                    ),
                                    hovertemplate=(
                                        f"Fit for {value}<br>Slope: {slope:.4f}<br>Intercept: {intercept:.4f}{qf_text}<extra></extra>"
                                    ),
                                )
                            )

            plot_title = title if group_mode == "combined" else f"{title} - {group_name}"
            fig = self._apply_layout(fig, plot_title, "Laser Intensity (suns)", y_col)
            if log_x:
                fig.update_xaxes(type="log")
            else:
                fig.update_xaxes(tickformat=".3f", exponentformat="none")
            figures.append(fig)
            slug = group_name.replace(" ", "_").replace("/", "_") if group_name else "combined"
            names.append(f"{y_col}_{slug}.html")

        if len(figures) == 1:
            return figures[0]
        return figures, names

    def qfls_intensity_plot(
        self,
        df,
        group_mode="combined",
        color_by="sample_id",
        log_x=False,
        title=None,
        fit_enabled=False,
        fit_min=None,
        fit_max=None,
        measurement_type=None,
        color_scheme="Viridis",
        color_sampling="sequential",
        color_count=8,
        trace_order=None,
    ):
        return self._scalar_intensity_plot(
            df,
            y_col="quasi_fermi_level_splitting",
            group_mode=group_mode,
            color_by=color_by,
            log_x=log_x,
            title=title or "QFLS vs Laser Intensity",
            fit_enabled=fit_enabled,
            fit_min=fit_min,
            fit_max=fit_max,
            measurement_type=measurement_type,
            color_scheme=color_scheme,
            color_sampling=color_sampling,
            color_count=color_count,
            trace_order=trace_order,
            fit_quality_factor=True,
        )

    def plqy_qfls_dual_axis_plot(
        self,
        df,
        group_mode="combined",
        color_by="sample_id",
        log_x=False,
        title=None,
        fit_enabled=False,
        fit_min=None,
        fit_max=None,
        measurement_type=None,
        color_scheme="Viridis",
        color_sampling="sequential",
        color_count=8,
        trace_order=None,
    ):
        if df is None or df.empty:
            return self._apply_layout(
                go.Figure(), title or "No data", "Laser Intensity (suns)", "PLQY (%)"
            )

        working_df = df.copy()
        if measurement_type is not None and "measurement_type" in working_df.columns:
            working_df = working_df[
                working_df["measurement_type"].astype(str) == str(measurement_type)
            ].copy()
        if working_df.empty:
            return self._apply_layout(
                go.Figure(), title or "No data", "Laser Intensity (suns)", "PLQY (%)"
            )

        working_df["_x"] = pd.to_numeric(working_df.get("laser_intensity_suns"), errors="coerce")
        working_df["_plqy"] = pd.to_numeric(
            working_df.get("luminescence_quantum_yield"), errors="coerce"
        )
        working_df["_qfls"] = pd.to_numeric(
            working_df.get("quasi_fermi_level_splitting"), errors="coerce"
        )
        working_df = working_df.dropna(subset=["_x"])
        if working_df.empty:
            return self._apply_layout(
                go.Figure(), title or "No valid values", "Laser Intensity (suns)", "PLQY (%)"
            )

        from plotly.subplots import make_subplots

        groups = self._split_groups(working_df, group_mode=group_mode)
        figures = []
        names = []

        for group_name, group_df in groups:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            color_by_effective = (
                color_by
                if color_by in group_df.columns
                else ("sample_id" if "sample_id" in group_df.columns else None)
            )
            group_values = (
                ["All"]
                if color_by_effective is None
                else self._ordered_values(
                    group_df[color_by_effective].fillna("Unknown").astype(str).unique().tolist(),
                    trace_order,
                )
            )
            colors = self._generate_palette(color_scheme, max(1, len(group_values)), color_sampling)
            color_map = {value: colors[idx % len(colors)] for idx, value in enumerate(group_values)}

            for value in group_values:
                sub = (
                    group_df
                    if color_by_effective is None
                    else group_df[
                        group_df[color_by_effective].fillna("Unknown").astype(str) == value
                    ]
                )
                sub = sub.sort_values("_x")
                if sub.empty:
                    continue
                x_values = sub["_x"].to_numpy(dtype=float)
                plqy_values = sub["_plqy"].to_numpy(dtype=float)
                qfls_values = sub["_qfls"].to_numpy(dtype=float)

                valid_plqy = np.isfinite(x_values) & np.isfinite(plqy_values)
                if np.any(valid_plqy):
                    fig.add_trace(
                        go.Scatter(
                            x=x_values[valid_plqy].tolist(),
                            y=plqy_values[valid_plqy].tolist(),
                            mode="lines+markers",
                            name=f"{value} PLQY",
                            line=dict(width=2, color=color_map.get(value, colors[0])),
                            marker=dict(size=6, color=color_map.get(value, colors[0])),
                        ),
                        secondary_y=False,
                    )

                valid_qfls = np.isfinite(x_values) & np.isfinite(qfls_values)
                if np.any(valid_qfls):
                    qfls_name = f"{value} QFLS"
                    fig.add_trace(
                        go.Scatter(
                            x=x_values[valid_qfls].tolist(),
                            y=qfls_values[valid_qfls].tolist(),
                            mode="lines+markers",
                            name=qfls_name,
                            line=dict(width=2, color=color_map.get(value, colors[0]), dash="dot"),
                            marker=dict(
                                size=6, color=color_map.get(value, colors[0]), symbol="diamond"
                            ),
                        ),
                        secondary_y=True,
                    )
                    qfls_trace = fig.data[-1]

                    if fit_enabled:
                        fit_mask = valid_qfls.copy()
                        if fit_min is not None:
                            fit_mask &= x_values >= float(fit_min)
                        if fit_max is not None:
                            fit_mask &= x_values <= float(fit_max)
                        x_fit = x_values[fit_mask]
                        y_fit = qfls_values[fit_mask]
                        if x_fit.size >= 2:
                            x_for_fit = np.log(x_fit) if log_x else x_fit
                            if np.all(np.isfinite(x_for_fit)) and np.nanstd(x_for_fit) > 0:
                                slope, intercept = np.polyfit(x_for_fit, y_fit, 1)
                                x_line = np.linspace(np.nanmin(x_fit), np.nanmax(x_fit), 120)
                                y_line = slope * (np.log(x_line) if log_x else x_line) + intercept
                                if log_x:
                                    qf_value = self._quality_factor_from_qfls_slope(slope)
                                    if qf_value is not None:
                                        qfls_trace.name = f"{qfls_name}, A={qf_value:.3f}"
                                fig.add_trace(
                                    go.Scatter(
                                        x=x_line.tolist(),
                                        y=y_line.tolist(),
                                        mode="lines",
                                        name=f"{value} QFLS fit",
                                        showlegend=False,
                                        line=dict(
                                            color=color_map.get(value, colors[0]),
                                            width=2,
                                            dash="dash",
                                        ),
                                    ),
                                    secondary_y=True,
                                )

            fig.update_layout(
                title=dict(
                    text=title if group_mode == "combined" else f"{title} - {group_name}",
                    font=dict(size=self.font_size_title),
                ),
                template="plotly_white",
                legend=dict(font=dict(size=self.font_size_legend)),
                margin=dict(l=80, r=80, t=70, b=70),
                width=1400,
                height=850,
            )
            fig.update_xaxes(
                title_text="Laser Intensity (suns)",
                showgrid=True,
                gridwidth=1,
                gridcolor="#eaecf0",
                tickfont=dict(size=self.font_size_axis),
            )
            fig.update_yaxes(
                title_text="PLQY (%)",
                secondary_y=False,
                showgrid=True,
                gridwidth=1,
                gridcolor="#eaecf0",
                tickfont=dict(size=self.font_size_axis),
            )
            fig.update_yaxes(
                title_text="QFLS (eV)", secondary_y=True, tickfont=dict(size=self.font_size_axis)
            )
            if log_x:
                fig.update_xaxes(type="log")
            else:
                fig.update_xaxes(tickformat=".3f", exponentformat="none")
            figures.append(fig)
            slug = group_name.replace(" ", "_").replace("/", "_") if group_name else "combined"
            names.append(f"plqy_qfls_{slug}.html")

        if len(figures) == 1:
            return figures[0]
        return figures, names

    def _generate_palette(self, scheme="Viridis", n=8, sampling="sequential"):
        palettes = self._palette_dict()
        base = palettes.get(scheme, px.colors.sequential.Viridis)
        n = max(1, int(n or 8))
        if n <= len(base):
            if n == 1:
                return [base[len(base) // 2]]
            # Always spread colors across palette range so small-N plots are not clustered in one hue.
            idxs = [int(round(i * (len(base) - 1) / (n - 1))) for i in range(n)]
            return [base[i] for i in idxs]

        if len(base) > 1:
            return px.colors.sample_colorscale(base, [i / (n - 1) for i in range(n)])
        return [base[0] for _ in range(n)]

    def _split_groups(self, df, group_mode="combined"):
        if group_mode == "per_sample":
            if "sample_id" not in df.columns:
                return [("All samples", df.copy())]
            groups = []
            for sample_id, sample_df in df.groupby("sample_id"):
                groups.append((str(sample_id), sample_df.copy()))
            return groups
        if group_mode == "separate_substrates":
            group_col = (
                "substrate"
                if "substrate" in df.columns
                else ("condition" if "condition" in df.columns else "sample_id")
            )
            groups = []
            for substrate, substrate_df in df.groupby(group_col):
                groups.append((str(substrate), substrate_df.copy()))
            return groups
        return [("Combined", df.copy())]

    def _nearest_sweep_to_one_sun(self, sweep_df):
        if sweep_df is None or sweep_df.empty:
            return pd.DataFrame()

        w = sweep_df.copy()
        w["_laser"] = pd.to_numeric(w.get("laser_intensity_suns"), errors="coerce")
        w["_dist"] = (w["_laser"] - 1.0).abs()

        if "sample_id" not in w.columns:
            with_dist = w[w["_dist"].notna()]
            if not with_dist.empty:
                return with_dist.nsmallest(1, "_dist").drop(
                    columns=["_laser", "_dist"], errors="ignore"
                )
            return w.head(1).drop(columns=["_laser", "_dist"], errors="ignore")

        selected = []
        for _, gdf in w.groupby("sample_id"):
            with_dist = gdf[gdf["_dist"].notna()]
            if not with_dist.empty:
                selected.append(with_dist.nsmallest(1, "_dist"))
            else:
                selected.append(gdf.head(1))

        if not selected:
            return pd.DataFrame()

        merged = pd.concat(selected, ignore_index=False)
        return merged.drop(columns=["_laser", "_dist"], errors="ignore")

    def pl_plot(
        self,
        spectra_df,
        color_by="sample_id",
        y_source="auto",
        include_nearest_sweep=True,
        color_scheme="Viridis",
        color_sampling="sequential",
        color_count=8,
        trace_order=None,
        fit_enabled=False,
        fit_model="gaussian",
        fit_mode="auto",
        fit_min=None,
        fit_max=None,
        fit_curve_ranges=None,
    ):
        if spectra_df is None or spectra_df.empty:
            return self._apply_layout(go.Figure(), "No data", "Wavelength (nm)", "Intensity")

        pl_df = spectra_df[spectra_df["measurement_type"].astype(str) == "pl"].copy()
        if pl_df.empty:
            return self._apply_layout(
                go.Figure(), "No PL data available", "Wavelength (nm)", "Intensity"
            )

        if include_nearest_sweep:
            sweep_df = spectra_df[spectra_df["measurement_type"].astype(str) == "sweep"].copy()
            nearest_sweep_df = self._nearest_sweep_to_one_sun(sweep_df)
            if not nearest_sweep_df.empty:
                working_df = pd.concat([pl_df, nearest_sweep_df], ignore_index=True)
                title = "PL + PL (sweep, nearest to 1 sun)"
            else:
                working_df = pl_df
                title = "PL"
        else:
            working_df = pl_df
            title = "PL"

        return self._make_spectrum_figure(
            working_df,
            title=title,
            y_title="Intensity",
            color_by=color_by,
            normalize=False,
            log_y=False,
            y_source=y_source,
            color_scheme=color_scheme,
            color_sampling=color_sampling,
            color_count=color_count,
            trace_order=trace_order,
            fit_enabled=fit_enabled,
            fit_model=fit_model,
            fit_mode=fit_mode,
            fit_min=fit_min,
            fit_max=fit_max,
            fit_curve_ranges=fit_curve_ranges,
        )

    def _make_spectrum_figure(
        self,
        df,
        title,
        y_title,
        color_by="sample_id",
        normalize=False,
        log_y=False,
        y_source="auto",
        show_laser_intensity=False,
        color_scheme="Viridis",
        color_sampling="sequential",
        color_count=8,
        trace_order=None,
        fit_enabled=False,
        fit_model="gaussian",
        fit_mode="auto",
        fit_min=None,
        fit_max=None,
        fit_curve_ranges=None,
    ):
        fig = go.Figure()
        if df is None or df.empty:
            return self._apply_layout(go.Figure(), title, "Wavelength (nm)", y_title)

        if color_by not in df.columns:
            color_by = (
                "sample_id"
                if "sample_id" in df.columns
                else ("condition" if "condition" in df.columns else None)
            )

        if color_by is None:
            categories = ["All"]
        else:
            categories = df[color_by].fillna("Unknown").astype(str).unique().tolist()
            categories = self._ordered_values(categories, trace_order)

        colors = self._generate_palette(color_scheme, max(1, len(categories)), color_sampling)
        color_map = {c: colors[i % len(colors)] for i, c in enumerate(categories)}

        # Special sweep behavior: if all traces share one color-by value, color traces by intensity.
        intensity_colors = []
        use_intensity_palette = False
        single_group_name = None
        if show_laser_intensity and len(categories) == 1 and len(df) > 1:
            use_intensity_palette = True
            single_group_name = categories[0]
            df = df.copy()
            df["_laser_order"] = pd.to_numeric(df.get("laser_intensity_suns"), errors="coerce")
            df = df.sort_values("_laser_order", na_position="last")
            intensity_colors = self._generate_palette(color_scheme, max(len(df), 3), color_sampling)

        for row_idx, (_, row) in enumerate(df.iterrows()):
            x = row.get("wavelength", None)
            y = self._get_spectrum_source(row, y_source=y_source)
            if not isinstance(x, list) or not isinstance(y, list):
                continue
            if len(x) == 0 or len(y) == 0:
                continue

            n = min(len(x), len(y))
            x = np.asarray(x[:n], dtype=float)
            y = np.asarray(y[:n], dtype=float)
            mask = np.isfinite(x) & np.isfinite(y)
            x = x[mask]
            y = y[mask]
            if x.size == 0:
                continue

            if normalize:
                ymax = np.nanmax(y)
                if np.isfinite(ymax) and ymax > 0:
                    y = y / ymax

            if log_y:
                valid = y > 0
                x = x[valid]
                y = y[valid]
                if y.size == 0:
                    continue

            color_value = (
                self._resolve_color_value(row, color_by) if color_by is not None else "All"
            )
            laser_intensity = pd.to_numeric(row.get("laser_intensity_suns"), errors="coerce")
            measurement_uid = row.get("measurement_uid", None)

            if show_laser_intensity and np.isfinite(laser_intensity):
                trace_name = (
                    f"{laser_intensity:.4g} sun" if use_intensity_palette else f"{color_value}"
                )
                hover_extra = f"<br>Laser intensity: {laser_intensity:.4g} sun"
            else:
                trace_name = f"{color_value}"
                hover_extra = ""

            line_color = color_map.get(color_value, colors[0])
            legend_group_title = None
            if use_intensity_palette:
                line_color = intensity_colors[row_idx % len(intensity_colors)]
                legend_group_title = (
                    f"{color_by}: {single_group_name}" if color_by is not None else ""
                )

            fig.add_trace(
                go.Scatter(
                    x=x.tolist(),
                    y=y.tolist(),
                    mode="lines",
                    line=dict(width=2, color=line_color),
                    name=trace_name,
                    legendgroup=("sweep_single_group" if use_intensity_palette else color_value),
                    legendgrouptitle_text=legend_group_title
                    if use_intensity_palette and row_idx == 0
                    else None,
                    showlegend=True,
                    hovertemplate=(
                        "<b>%{fullData.name}</b><br>"
                        "Wavelength: %{x:.4g} nm<br>"
                        "Intensity: %{y:.4g}"
                        f"{hover_extra}<extra></extra>"
                    ),
                )
            )
            base_trace = fig.data[-1]

            if fit_enabled:
                fit_min_local, fit_max_local = self._resolve_fit_range(
                    fit_curve_ranges,
                    [
                        measurement_uid,
                        trace_name,
                        color_value,
                        row.get("sample_id", None),
                        row.get("condition", None),
                        row.get("batch", None),
                        row.get("laser_spot_size", None),
                    ],
                    default_min=fit_min,
                    default_max=fit_max,
                )
                peak_fit = self._fit_peak_profile(
                    x,
                    y,
                    fit_model=fit_model,
                    fit_mode=fit_mode,
                    fit_min=fit_min_local,
                    fit_max=fit_max_local,
                )
                if peak_fit is not None:
                    base_trace.name = f"{trace_name}, Peak = {peak_fit['center']:.2f} nm, FWHM = {peak_fit['fwhm']:.2f} nm"
                    fit_label = f"{trace_name} {peak_fit['model']} fit"
                    fig.add_trace(
                        go.Scatter(
                            x=peak_fit["x_fit"].tolist(),
                            y=peak_fit["y_fit"].tolist(),
                            mode="lines",
                            name=fit_label,
                            legendgroup=(
                                "sweep_single_group" if use_intensity_palette else color_value
                            ),
                            showlegend=False,
                            line=dict(color=line_color, width=2, dash="dash"),
                            hovertemplate=(
                                f"{peak_fit['model']} fit<br>"
                                f"Peak position: {peak_fit['center']:.3f} nm<br>"
                                f"FWHM: {peak_fit['fwhm']:.3f} nm<br>"
                                f"Fit window: {peak_fit['fit_min']:.3f} - {peak_fit['fit_max']:.3f} nm<extra></extra>"
                            ),
                        )
                    )
                    fig.add_trace(
                        go.Scatter(
                            x=[peak_fit["center"]],
                            y=[
                                float(
                                    np.interp(
                                        peak_fit["center"], peak_fit["x_fit"], peak_fit["y_fit"]
                                    )
                                )
                            ],
                            mode="markers",
                            name=f"{trace_name} peak",
                            legendgroup=(
                                "sweep_single_group" if use_intensity_palette else color_value
                            ),
                            showlegend=False,
                            marker=dict(color=line_color, size=9, symbol="x"),
                            hovertemplate=(
                                f"Peak position: {peak_fit['center']:.3f} nm<br>"
                                f"FWHM: {peak_fit['fwhm']:.3f} nm<extra></extra>"
                            ),
                        )
                    )

        fig = self._apply_layout(fig, title, "Wavelength (nm)", y_title)
        if log_y:
            fig.update_yaxes(type="log")
        return fig

    def spectra_overlay(
        self,
        df,
        measurement_type=None,
        group_mode="combined",
        color_by="sample_id",
        normalize=False,
        log_y=False,
        y_source="auto",
        title=None,
        color_scheme="Viridis",
        color_sampling="sequential",
        color_count=8,
        trace_order=None,
        fit_enabled=False,
        fit_model="gaussian",
        fit_mode="auto",
        fit_min=None,
        fit_max=None,
        fit_curve_ranges=None,
    ):
        """Plot PL or sweep spectra either combined or one figure per sample.

        For sweep measurements, always uses luminescence_flux_density.
        """
        if df is None or df.empty:
            empty_title = title or "No data"
            return self._apply_layout(go.Figure(), empty_title, "Wavelength (nm)", "Intensity")

        working_df = df.copy()
        if measurement_type is not None and "measurement_type" in working_df.columns:
            working_df = working_df[
                working_df["measurement_type"].astype(str) == str(measurement_type)
            ]

        if working_df.empty:
            empty_title = title or f"No {measurement_type or 'spectral'} data available"
            return self._apply_layout(go.Figure(), empty_title, "Wavelength (nm)", "Intensity")

        # For sweeps, force flux density source
        if measurement_type == "sweep":
            y_source = "luminescence_flux_density"

        groups = self._split_groups(working_df, group_mode=group_mode)
        figures = []
        names = []
        base_title = title or (
            "PL Spectra"
            if measurement_type == "pl"
            else "Sweep Spectra"
            if measurement_type == "sweep"
            else "AbsPL Spectra"
        )

        for group_name, group_df in groups:
            group_title = base_title if group_mode == "combined" else f"{base_title} - {group_name}"
            y_title = "Normalized intensity" if normalize else "Intensity"
            fig = self._make_spectrum_figure(
                group_df,
                group_title,
                y_title,
                color_by=color_by,
                normalize=normalize,
                log_y=log_y,
                y_source=y_source,
                show_laser_intensity=(measurement_type == "sweep"),
                color_scheme=color_scheme,
                color_sampling=color_sampling,
                color_count=color_count,
                trace_order=trace_order,
                fit_enabled=fit_enabled,
                fit_model=fit_model,
                fit_mode=fit_mode,
                fit_min=fit_min,
                fit_max=fit_max,
                fit_curve_ranges=fit_curve_ranges,
            )
            figures.append(fig)
            slug = group_name.replace(" ", "_").replace("/", "_") if group_name else "combined"
            names.append(f"{measurement_type or 'spectra'}_{slug}.html")

        if len(figures) == 1:
            return figures[0]
        return figures, names

    def average_spectra(self, df, group_by="condition", y_source="auto"):
        fig = go.Figure()
        if df is None or df.empty:
            return self._apply_layout(go.Figure(), "No data", "Wavelength (nm)", "Intensity")

        if group_by not in df.columns:
            group_by = "condition" if "condition" in df.columns else "sample"

        colors = px.colors.qualitative.D3
        for idx, (group_name, gdf) in enumerate(df.groupby(group_by)):
            curves = []
            wavelength_ref = None
            for _, row in gdf.iterrows():
                x = row.get("wavelength", None)
                if y_source == "luminescence_flux_density":
                    y = row.get("luminescence_flux_density", None)
                elif y_source == "raw_spectrum_counts":
                    y = row.get("raw_spectrum_counts", None)
                else:
                    y = row.get("y_data", None)
                if not isinstance(x, list) or not isinstance(y, list):
                    continue
                n = min(len(x), len(y))
                if n < 5:
                    continue
                x = np.asarray(x[:n], dtype=float)
                y = np.asarray(y[:n], dtype=float)
                mask = np.isfinite(x) & np.isfinite(y)
                x = x[mask]
                y = y[mask]
                if x.size < 5:
                    continue
                if wavelength_ref is None:
                    wavelength_ref = x
                if (
                    wavelength_ref is not None
                    and len(x) == len(wavelength_ref)
                    and np.allclose(x, wavelength_ref)
                ):
                    curves.append(y)

            if wavelength_ref is None or not curves:
                continue

            arr = np.vstack(curves)
            y_mean = np.nanmean(arr, axis=0)
            y_std = np.nanstd(arr, axis=0)

            color = colors[idx % len(colors)]
            fig.add_trace(
                go.Scatter(
                    x=wavelength_ref,
                    y=y_mean,
                    mode="lines",
                    name=f"{group_name} (mean)",
                    line=dict(color=color, width=3),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=np.concatenate([wavelength_ref, wavelength_ref[::-1]]),
                    y=np.concatenate([y_mean - y_std, (y_mean + y_std)[::-1]]),
                    fill="toself",
                    fillcolor=self._rgba_from_color(color, 0.18),
                    line=dict(color="rgba(0,0,0,0)"),
                    hoverinfo="skip",
                    showlegend=False,
                    name=f"{group_name} std",
                )
            )

        return self._apply_layout(fig, "Average Spectra by Group", "Wavelength (nm)", "Intensity")

    def plqy_intensity_plot(
        self,
        df,
        y_col="luminescence_quantum_yield",
        group_mode="combined",
        color_by="sample_id",
        log_x=False,
        title=None,
        fit_enabled=False,
        fit_min=None,
        fit_max=None,
        measurement_type=None,
        color_scheme="Viridis",
        color_sampling="sequential",
        color_count=8,
        trace_order=None,
    ):
        return self._scalar_intensity_plot(
            df,
            y_col=y_col,
            group_mode=group_mode,
            color_by=color_by,
            log_x=log_x,
            title=title or "PLQY vs Laser Intensity",
            fit_enabled=False,
            fit_min=fit_min,
            fit_max=fit_max,
            measurement_type=measurement_type,
            color_scheme=color_scheme,
            color_sampling=color_sampling,
            color_count=color_count,
            trace_order=trace_order,
            fit_quality_factor=False,
        )

    def sweep_heatmap(self, df, sample=None, intensity_source="luminescence_flux_density"):
        if df is None or df.empty:
            return self._apply_layout(go.Figure(), "No data", "Wavelength (nm)", "Cycle")

        sweep_df = df[df["measurement_type"] == "sweep"].copy()
        if sweep_df.empty:
            return self._apply_layout(
                go.Figure(), "No sweep data available", "Wavelength (nm)", "Cycle"
            )

        if sample is None:
            sample = sweep_df["sample_id"].value_counts().index[0]

        s = sweep_df[sweep_df["sample_id"] == sample].sort_values("cycle_number")
        if s.empty:
            return self._apply_layout(
                go.Figure(), f"No sweep data for sample {sample}", "Wavelength (nm)", "Cycle"
            )

        rows = []
        wavelengths = None
        cycle_labels = []
        for _, row in s.iterrows():
            x = row.get("wavelength")
            y = row.get(intensity_source, row.get("y_data"))
            if not isinstance(x, list) or not isinstance(y, list):
                continue
            n = min(len(x), len(y))
            if n < 5:
                continue
            x = np.asarray(x[:n], dtype=float)
            y = np.asarray(y[:n], dtype=float)
            mask = np.isfinite(x) & np.isfinite(y)
            x = x[mask]
            y = y[mask]
            if x.size < 5:
                continue
            if wavelengths is None:
                wavelengths = x
            if len(x) != len(wavelengths) or not np.allclose(x, wavelengths):
                continue
            rows.append(y)
            cycle_labels.append(int(row.get("cycle_number", len(cycle_labels) + 1)))

        if wavelengths is None or not rows:
            return self._apply_layout(
                go.Figure(),
                f"Could not build heatmap for sample {sample}",
                "Wavelength (nm)",
                "Cycle",
            )

        z = np.vstack(rows)
        fig = go.Figure(
            data=go.Heatmap(
                x=wavelengths,
                y=cycle_labels,
                z=z,
                colorscale="Viridis",
                colorbar=dict(title="Intensity"),
            )
        )
        fig = self._apply_layout(
            fig, f"Sweep Heatmap - Sample {sample}", "Wavelength (nm)", "Cycle"
        )
        return fig

    def scalar_boxplot(self, df, y_col="plqy", x_col="condition"):
        if df is None or df.empty or y_col not in df.columns:
            return self._apply_layout(go.Figure(), "No scalar data", x_col, y_col)
        data = df.copy()
        data[y_col] = pd.to_numeric(data[y_col], errors="coerce")
        data = data.dropna(subset=[y_col])
        if data.empty:
            return self._apply_layout(go.Figure(), f"No valid values in {y_col}", x_col, y_col)
        if x_col not in data.columns:
            x_col = "condition" if "condition" in data.columns else "sample"
        fig = px.box(data, x=x_col, y=y_col, color=x_col, points="all")
        return self._apply_layout(fig, f"{y_col} distribution by {x_col}", x_col, y_col)

    def scalar_scatter(self, df, x_col="laser_intensity_suns", y_col="plqy", color_col="condition"):
        if df is None or df.empty:
            return self._apply_layout(go.Figure(), "No scalar data", x_col, y_col)
        data = df.copy()
        for col in [x_col, y_col]:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce")
        if x_col not in data.columns or y_col not in data.columns:
            return self._apply_layout(go.Figure(), "Missing scalar columns", x_col, y_col)
        data = data.dropna(subset=[x_col, y_col])
        if data.empty:
            return self._apply_layout(go.Figure(), "No valid scalar pairs", x_col, y_col)
        if color_col not in data.columns:
            color_col = "condition" if "condition" in data.columns else None
        fig = px.scatter(
            data,
            x=x_col,
            y=y_col,
            color=color_col,
            hover_data=["sample_id", "cycle_number", "measurement_type"],
        )
        fig.update_traces(mode="markers+lines")
        return self._apply_layout(fig, f"{y_col} vs {x_col}", x_col, y_col)
