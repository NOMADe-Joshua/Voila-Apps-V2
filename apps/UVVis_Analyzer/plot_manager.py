"""
UVVis Plot Management Module
Handles all plotting operations for UVVis spectra.
"""

__author__ = "Joshua Damm"
__institution__ = "KIT"
__created__ = "December 2025"

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.interpolate import CubicSpline
from scipy.optimize import curve_fit
from scipy.signal import argrelextrema, savgol_filter
from scipy.stats import linregress


class UVVisPlotManager:
    """Manages UVVis spectroscopy plotting"""

    def __init__(self):
        self.plot_output_path = ""

    def set_output_path(self, path):
        self.plot_output_path = path

    def _pick_color(self, color_map, color_scheme, variation, idx):
        """Return color for a variation, fallback to cycling scheme."""
        if color_map and variation in color_map:
            return color_map[variation]
        return color_scheme[idx % len(color_scheme)] if color_scheme else None

    def create_spectra_plot(
        self,
        measurements,
        color_scheme=None,
        layout_mode="overlay",
        channels=None,
        x_axis="wavelength",
        color_map=None,
    ):
        """
        Create UV-Vis spectra plot with selectable channels (reflection/transmission/absorption)

        Args:
            measurements: List of measurement dictionaries
            color_scheme: List of colors
            layout_mode: 'overlay', 'grid', or 'separate'
            channels: list of strings in ['reflection','transmission','absorption']
            x_axis: 'wavelength' or 'energy' - applies to all plot types
        """
        if not measurements:
            fig = go.Figure()
            fig.update_layout(title="No data available")
            return fig, "uvvis_spectra.html"

        if color_scheme is None:
            color_scheme = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
        if not channels:
            channels = ["absorption"]

        # Filter measurements based on selected channels
        filtered_measurements = []
        for measurement in measurements:
            meas_name_lower = measurement["measurement_name"].lower()
            # Check if this measurement matches any selected channel
            for channel in channels:
                if channel.lower() in meas_name_lower:
                    filtered_measurements.append(measurement)
                    break  # Only add each measurement once

        if not filtered_measurements:
            fig = go.Figure()
            fig.update_layout(title="No measurements match selected channels")
            return fig, "uvvis_spectra_empty.html"

        if layout_mode == "overlay":
            return self._create_overlay_plot(
                filtered_measurements, color_scheme, channels, x_axis, color_map
            )
        elif layout_mode == "grid":
            return self._create_grid_plot(
                filtered_measurements, color_scheme, channels, x_axis, color_map
            )
        else:
            return self._create_separate_plots(
                filtered_measurements, color_scheme, channels, x_axis, color_map
            )

    def _resolve_series(self, measurement, channel):
        """Return (y, legend_channel) for a channel, or (None, None) if unavailable."""
        if channel == "reflection" and measurement.get("reflection") is not None:
            return measurement["reflection"], "reflection"
        if channel == "transmission" and measurement.get("transmission") is not None:
            return measurement["transmission"], "transmission"
        if channel == "absorption":
            r = measurement.get("reflection")
            t = measurement.get("transmission")
            if r is not None and t is not None:
                try:
                    absorption = 1 - r - t
                    return absorption, "absorption"
                except Exception:
                    pass
            if measurement.get("intensity") is not None:
                return measurement["intensity"], "absorption"
        return None, None

    def create_bandgap_derivative_plot(
        self, measurements, colors=None, x_axis="energy", color_map=None, bandgap_options=None
    ):
        """
        Create bandgap determination plot using derivative method
        Shows ONLY the derivative of absorption, not the absorption itself

        Args:
            measurements: List of measurement dictionaries
            colors: Color scheme
            x_axis: 'energy' or 'wavelength'
            bandgap_options: Dict with 'auto_fit', 'show_in_legend', 'show_table', 'manual_peaks'
        """
        if not measurements:
            fig = go.Figure()
            fig.update_layout(title="No data available")
            return fig, "uvvis_bandgap_derivative.html"

        if colors is None:
            colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]

        # Parse bandgap options
        if bandgap_options is None:
            bandgap_options = {
                "auto_fit": True,
                "show_in_legend": True,
                "show_table": True,
                "manual_peaks": [],
            }

        # Table to store all bandgaps
        bandgap_table_data = []

        # Filter to only include absorption measurements
        absorption_measurements = []
        for measurement in measurements:
            meas_name_lower = measurement["measurement_name"].lower()
            if "absorption" in meas_name_lower:
                absorption_measurements.append(measurement)

        if not absorption_measurements:
            fig = go.Figure()
            fig.update_layout(title="No absorption measurements available for bandgap analysis")
            return fig, "uvvis_bandgap_derivative.html"

        # Create single plot for derivative only
        fig = go.Figure()

        for i, measurement in enumerate(absorption_measurements):
            try:
                wavelength = measurement["wavelength"]
                intensity = measurement["intensity"]
                name = measurement.get("variation", measurement["sample_name"])
                color = self._pick_color(color_map, colors, name, i)

                # Convert to photon energy
                photon_energy = 1239.841984 / wavelength

                # Sort by energy
                sorted_indices = np.argsort(photon_energy)
                energy_sorted = photon_energy[sorted_indices]
                absorption_sorted = intensity[sorted_indices]

                # Interpolate and smooth
                energy_range = np.linspace(energy_sorted.min(), energy_sorted.max(), 1001)
                spline = CubicSpline(energy_sorted, absorption_sorted)
                interpolated_absorption = spline(energy_range)
                smoothed_absorption = savgol_filter(
                    interpolated_absorption, window_length=101, polyorder=3
                )
                derivative = np.gradient(smoothed_absorption, energy_range)

                # Find bandgap peaks - auto or manual
                peaks_result = []
                bandgap_energies = []

                if bandgap_options["auto_fit"]:
                    # Automatic peak finding with Gaussian fitting
                    peaks_result = self._find_peaks_and_fit_gaussian(energy_range, derivative)
                    bandgap_energies = [peak[0] for peak in peaks_result]

                # Add manual peaks
                if bandgap_options["manual_peaks"]:
                    for manual_peak in bandgap_options["manual_peaks"]:
                        if energy_range.min() <= manual_peak <= energy_range.max():
                            # Find closest point in energy_range
                            idx = np.argmin(np.abs(energy_range - manual_peak))
                            # Create a fitting range around the manual peak
                            fitting_range = (energy_range > manual_peak - 0.1) & (
                                energy_range < manual_peak + 0.1
                            )

                            try:
                                # Fit Gaussian at manual position
                                popt, _ = curve_fit(
                                    UVVisPlotManager._gaussian,
                                    energy_range[fitting_range],
                                    derivative[fitting_range],
                                    p0=[derivative[idx], manual_peak, 0.05],
                                )
                                peaks_result.append((popt[1], popt, fitting_range))
                                bandgap_energies.append(popt[1])
                            except:
                                # If fit fails, just use the manual value
                                bandgap_energies.append(manual_peak)

                # Create legend label with bandgaps if requested
                if bandgap_options["show_in_legend"] and bandgap_energies:
                    bandgap_str = ", ".join([f"{bg:.2f} eV" for bg in sorted(bandgap_energies)])
                    legend_label = f"{name}<br>Eg: {bandgap_str}"
                else:
                    legend_label = name

                # Store for table
                if bandgap_energies:
                    bandgap_table_data.append({"Sample": name, "Bandgaps (eV)": bandgap_energies})

                if x_axis == "wavelength":
                    # Convert back to wavelength
                    wavelength_range = 1239.841984 / energy_range[::-1]
                    derivative = derivative[::-1]

                    x_smooth = wavelength_range
                    x_label = "Wavelength [nm]"

                    # Add derivative trace with legend
                    fig.add_trace(
                        go.Scatter(
                            x=x_smooth,
                            y=derivative,
                            mode="lines",
                            name=legend_label,
                            line=dict(color=color, width=2),
                            showlegend=True,
                            hovertemplate=f"<b>{name}</b><br>λ: %{{x:.1f}} nm<br>d(A)/dλ: %{{y:.4f}}<extra></extra>",
                        )
                    )

                    # Add bandgap markers and Gaussian fits
                    for bandgap_energy, popt, fitting_range in peaks_result:
                        lambda_bg = 1239.841984 / bandgap_energy
                        lambda_fit = 1239.841984 / energy_range[fitting_range][::-1]

                        fig.add_trace(
                            go.Scatter(
                                x=lambda_fit,
                                y=UVVisPlotManager._gaussian(energy_range[fitting_range], *popt)[
                                    ::-1
                                ],
                                mode="lines",
                                line=dict(color=color, dash="dot", width=1.5),
                                showlegend=False,
                                hovertemplate=f"<b>{name}</b><br>Bandgap: {bandgap_energy:.2f} eV<extra></extra>",
                            )
                        )

                        fig.add_vline(
                            x=lambda_bg,
                            line_dash="dash",
                            line_color=color,
                            opacity=0.6,
                            annotation_text=f"{bandgap_energy:.2f} eV",
                            annotation_position="top",
                        )

                else:  # x_axis == 'energy'
                    x_smooth = energy_range
                    x_label = "Photon Energy [eV]"

                    # Add derivative trace with legend
                    fig.add_trace(
                        go.Scatter(
                            x=x_smooth,
                            y=derivative,
                            mode="lines",
                            name=legend_label,
                            line=dict(color=color, width=2),
                            showlegend=True,
                            hovertemplate=f"<b>{name}</b><br>E: %{{x:.3f}} eV<br>d(A)/dE: %{{y:.4f}}<extra></extra>",
                        )
                    )

                    # Add bandgap markers and Gaussian fits
                    for bandgap_energy, popt, fitting_range in peaks_result:
                        fig.add_trace(
                            go.Scatter(
                                x=energy_range[fitting_range],
                                y=UVVisPlotManager._gaussian(energy_range[fitting_range], *popt),
                                mode="lines",
                                line=dict(color=color, dash="dot", width=1.5),
                                showlegend=False,
                                hovertemplate=f"<b>{name}</b><br>Bandgap: {bandgap_energy:.2f} eV<extra></extra>",
                            )
                        )

                        fig.add_vline(
                            x=bandgap_energy,
                            line_dash="dash",
                            line_color=color,
                            opacity=0.6,
                            annotation_text=f"{bandgap_energy:.2f} eV",
                            annotation_position="top",
                        )

            except Exception as e:
                print(f"Error processing {measurement['sample_name']}: {e}")
                import traceback

                traceback.print_exc()
                continue

        # Update layout
        fig.update_xaxes(title_text=x_label, showgrid=True)
        fig.update_yaxes(title_text="d(Absorption)/dE", showgrid=True)

        fig.update_layout(
            title="UVVis Bandgap Determination (Derivative of Absorption)",
            template="plotly_white",
            width=1200,
            height=700,
            hovermode="closest",
            legend=dict(
                x=0.02, y=0.98, bgcolor="rgba(255,255,255,0.85)", bordercolor="black", borderwidth=1
            ),
        )

        filename = f"uvvis_bandgap_derivative_{x_axis}.html"

        # Return figure, filename, and bandgap table data
        return fig, filename, bandgap_table_data

    def create_tauc_plot(self, measurements, colors=None, thickness_nm=550, color_map=None):
        """
        Create Tauc plot for direct bandgap determination

        Args:
            measurements: List of measurement dictionaries (must include reflection/transmission)
            colors: Color scheme
            thickness_nm: Film thickness in nanometers
        """
        if not measurements:
            fig = go.Figure()
            fig.update_layout(title="No data available")
            return fig, "uvvis_tauc_plot.html"

        if colors is None:
            colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]

        fig = go.Figure()
        messages = []  # collected user-facing diagnostics
        traces_added = 0

        for i, measurement in enumerate(measurements):
            try:
                wavelength = np.asarray(measurement["wavelength"])
                name = measurement.get("variation", measurement["sample_name"])

                # Check if reflection/transmission data available
                if "reflection" not in measurement or "transmission" not in measurement:
                    messages.append(f"{name}: missing reflection/transmission data")
                    continue

                reflection = np.asarray(measurement["reflection"])
                transmission = np.asarray(measurement["transmission"])

                # Validate input lengths
                if len(wavelength) == 0 or len(reflection) == 0 or len(transmission) == 0:
                    messages.append(f"{name}: empty wavelength/reflection/transmission arrays")
                    continue

                # Calculate absorption coefficient safely
                numerator = (1 - reflection) ** 2
                valid_mask = (
                    np.isfinite(numerator)
                    & np.isfinite(transmission)
                    & (transmission > 0)
                    & (numerator > 0)
                )
                if valid_mask.sum() < 5:
                    messages.append(
                        f"{name}: not enough valid reflection/transmission points for Tauc plot"
                    )
                    continue

                wavelength = wavelength[valid_mask]
                numerator = numerator[valid_mask]
                transmission = transmission[valid_mask]
                ratio = numerator / transmission
                ratio = np.where(ratio > 0, ratio, 1e-12)
                alpha = (1 / thickness_nm) * np.log(ratio)

                # Convert to photon energy and Tauc variable
                photon_energy = 1239.841984 / wavelength
                tauc = (alpha * photon_energy) ** 2

                # Sort by energy
                sorted_indices = np.argsort(photon_energy)
                energy_sorted = photon_energy[sorted_indices]
                tauc_sorted = tauc[sorted_indices]

                if len(energy_sorted) < 5:
                    messages.append(f"{name}: insufficient points after sorting for Tauc plot")
                    continue

                # Smooth data with a valid odd window <= length
                window_length = min(
                    51, len(tauc_sorted) if len(tauc_sorted) % 2 == 1 else len(tauc_sorted) - 1
                )
                if window_length < 3:
                    if len(tauc_sorted) >= 3:
                        window_length = 3
                    else:
                        messages.append(f"{name}: too few points for smoothing")
                        continue
                tauc_smooth = savgol_filter(tauc_sorted, window_length, 3)

                # Find best fit
                fit_result = self._find_best_tauc_fit(energy_sorted, tauc_smooth)

                color = self._pick_color(color_map, colors, name, i)

                if fit_result is None:
                    label = f"{name} (no fit)"

                    fig.add_trace(
                        go.Scatter(
                            x=energy_sorted,
                            y=tauc_sorted,
                            mode="lines",
                            name=label,
                            line=dict(color=color, width=2, dash="dot"),
                            opacity=0.5,
                            hovertemplate=f"<b>{name}</b><br>Energy: %{{x:.3f}} eV<br>Tauc: %{{y:.4f}}<extra></extra>",
                        )
                    )
                    traces_added += 1
                else:
                    bandgap = fit_result["bandgap"]
                    r2 = fit_result["r2"]
                    label = f"{name} (Eg = {bandgap:.2f} eV, R² = {r2:.3f})"

                    # Plot data
                    fig.add_trace(
                        go.Scatter(
                            x=energy_sorted,
                            y=tauc_sorted,
                            mode="lines",
                            name=label,
                            line=dict(color=color, width=2),
                            opacity=0.7,
                            hovertemplate=f"<b>{name}</b><br>Energy: %{{x:.3f}} eV<br>Tauc: %{{y:.4f}}<extra></extra>",
                        )
                    )

                    # Plot fit line
                    x_fit = fit_result["x_fit"]
                    slope = fit_result["slope"]
                    intercept = fit_result["intercept"]

                    max_index = np.where(energy_sorted >= x_fit[-1])[0][0]
                    x_line = np.linspace(bandgap, energy_sorted[max_index], 100)
                    y_line = slope * x_line + intercept

                    fig.add_trace(
                        go.Scatter(
                            x=x_line,
                            y=y_line,
                            mode="lines",
                            line=dict(color=color, dash="dash", width=2),
                            showlegend=False,
                        )
                    )

                    # Mark bandgap
                    fig.add_trace(
                        go.Scatter(
                            x=[bandgap],
                            y=[0],
                            mode="markers",
                            marker=dict(color=color, size=10, symbol="circle"),
                            showlegend=False,
                            hovertemplate=f"<b>{name}</b><br>Bandgap: {bandgap:.2f} eV<extra></extra>",
                        )
                    )
                    traces_added += 1

            except Exception:
                messages.append(
                    f"{measurement.get('sample_name', 'Unknown')}: failed to process Tauc plot"
                )
                continue

        # If no traces were added, provide an on-plot message so Voila users see feedback
        if traces_added == 0:
            info = "; ".join(messages) if messages else "No valid data points for Tauc plot"
            fig.add_annotation(
                text=f"No Tauc data to display. {info}",
                xref="paper",
                yref="paper",
                x=0.5,
                y=0.5,
                showarrow=False,
                font=dict(color="red"),
            )

        fig.update_layout(
            title=f"Tauc Plot (Direct Bandgap, thickness={thickness_nm} nm)",
            xaxis_title="Photon Energy [eV]",
            yaxis_title="(αhν)² [a.u.]",
            template="plotly_white",
            width=1200,
            height=800,
            hovermode="closest",
        )

        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="lightgray")
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="lightgray")

        return fig, "uvvis_tauc_plot.html"

    @staticmethod
    def _gaussian(x, amp, cen, wid):
        """Gaussian function for peak fitting"""
        return amp * np.exp(-((x - cen) ** 2) / (2 * wid**2))

    @staticmethod
    def _find_peaks_and_fit_gaussian(x, y):
        """Find peaks in derivative and fit Gaussian"""
        peaks = argrelextrema(y, np.greater)[0]
        if peaks.size == 0:
            return []

        results = []
        y_masked = np.copy(y)

        while True:
            peaks = argrelextrema(y_masked, np.greater)[0]
            if peaks.size == 0:
                break

            peak = peaks[np.argmax(y_masked[peaks])]
            peak_energy = x[peak]

            if len(results) > 0 and y_masked[peak] < results[0][1][0] / 4:
                break

            fitting_range = (x > peak_energy - 0.1) & (x < peak_energy + 0.1)
            width = 0.05

            try:
                popt, _ = curve_fit(
                    UVVisPlotManager._gaussian,
                    x[fitting_range],
                    y[fitting_range],
                    p0=[y[peak], peak_energy, width],
                )
                results.append((popt[1], popt, fitting_range))
            except RuntimeError:
                break

            y_masked[fitting_range] = 0

        return results

    @staticmethod
    def _find_best_tauc_fit(x, y, min_range=0.15, max_range=0.35):
        """Find best linear fit in Tauc plot"""
        best_fit = None
        best_r2 = -np.inf

        for start in range(len(x)):
            for end in range(start + 5, len(x)):
                x_fit = x[start:end]
                y_fit = y[start:end]

                if len(x_fit) < 10:
                    continue

                energy_range = x_fit[-1] - x_fit[0]
                if energy_range < min_range or energy_range > max_range:
                    continue

                slope, intercept, r_value, *_ = linregress(x_fit, y_fit)
                r_squared = r_value**2

                if slope < 0 or r_squared < 0.98:
                    continue

                x0 = -intercept / slope
                if 0.5 < x0 < 3.5:
                    if r_squared > best_r2:
                        best_r2 = r_squared
                        best_fit = {
                            "x_fit": x_fit,
                            "y_fit": y_fit,
                            "slope": slope,
                            "intercept": intercept,
                            "bandgap": x0,
                            "r2": r_squared,
                        }

        return best_fit

    def _create_overlay_plot(
        self, measurements, color_scheme, channels, x_axis="wavelength", color_map=None
    ):
        fig = go.Figure()
        for i, measurement in enumerate(measurements):
            wavelength = measurement["wavelength"]
            display_name = measurement.get("variation", measurement["sample_name"])
            meas_name = measurement["measurement_name"]

            # Get the data - use intensity which should contain the correct measurement
            y = measurement.get("intensity")
            if y is None or len(y) == 0:
                continue

            color = self._pick_color(color_map, color_scheme, display_name, i)

            # Abbreviate channel names: reflection->R, transmission->T, absorption->A
            channel_abbrev = ""
            meas_name_lower = meas_name.lower()
            if "reflection" in meas_name_lower:
                channel_abbrev = "R"
            elif "transmission" in meas_name_lower:
                channel_abbrev = "T"
            elif "absorption" in meas_name_lower:
                channel_abbrev = "A"

            # Compact legend: "variation, R/T/A"
            legend_label = (
                f"{display_name}, {channel_abbrev}"
                if channel_abbrev
                else f"{display_name} - {meas_name}"
            )

            # Convert x-axis if needed
            if x_axis == "energy":
                x_data = 1239.841984 / wavelength
                x_title = "Photon Energy [eV]"
            else:
                x_data = wavelength
                x_title = "Wavelength [nm]"

            fig.add_trace(
                go.Scatter(
                    x=x_data,
                    y=y,
                    mode="lines",
                    name=legend_label,
                    line=dict(color=color, width=2),
                    hovertemplate=f"<b>{display_name}</b><br>{x_title}: %{{x:.2f}}<br>Value: %{{y:.4f}}<extra></extra>",
                )
            )
        fig.update_layout(
            title="UV-Vis Spectra",
            xaxis_title=x_title if x_axis == "energy" else "Wavelength [nm]",
            yaxis_title="Intensity [%]",
            template="plotly_white",
            legend=dict(
                x=0.02, y=0.98, bgcolor="rgba(255,255,255,0.85)", bordercolor="black", borderwidth=1
            ),
            width=1600,
            height=1000,
            hovermode="closest",
        )
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="lightgray")
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="lightgray")
        return fig, "uvvis_overlay_spectra.html"

    def _create_grid_plot(
        self, measurements, color_scheme, channels, x_axis="wavelength", color_map=None
    ):
        num_measurements = len(measurements)
        cols = 2
        rows = (num_measurements + cols - 1) // cols
        fig = make_subplots(
            rows=rows,
            cols=cols,
            subplot_titles=[
                f"{m.get('variation', m['sample_name'])}<br>{m['measurement_name']}"
                for m in measurements
            ],
            vertical_spacing=0.12,
            horizontal_spacing=0.10,
        )
        for i, measurement in enumerate(measurements):
            row = (i // cols) + 1
            col = (i % cols) + 1
            wavelength = measurement["wavelength"]
            display_name = measurement.get("variation", measurement["sample_name"])
            meas_name = measurement["measurement_name"]
            color = self._pick_color(color_map, color_scheme, display_name, i)

            y = measurement.get("intensity")
            if y is None or len(y) == 0:
                continue

            # Abbreviate channel names
            channel_abbrev = ""
            meas_name_lower = meas_name.lower()
            if "reflection" in meas_name_lower:
                channel_abbrev = "R"
            elif "transmission" in meas_name_lower:
                channel_abbrev = "T"
            elif "absorption" in meas_name_lower:
                channel_abbrev = "A"

            legend_label = (
                f"{display_name}, {channel_abbrev}"
                if channel_abbrev
                else f"{display_name} - {meas_name}"
            )

            # Convert x-axis if needed
            if x_axis == "energy":
                x_data = 1239.841984 / wavelength
                x_title = "Photon Energy [eV]"
            else:
                x_data = wavelength
                x_title = "Wavelength [nm]"

            fig.add_trace(
                go.Scatter(
                    x=x_data,
                    y=y,
                    mode="lines",
                    name=legend_label,
                    line=dict(color=color, width=2),
                    showlegend=True,
                    hovertemplate=f"<b>{display_name}</b><br>{x_title}: %{{x:.2f}}<br>Value: %{{y:.4f}}<extra></extra>",
                ),
                row=row,
                col=col,
            )
        fig.update_xaxes(
            title_text=x_title if x_axis == "energy" else "Wavelength [nm]", showgrid=True
        )
        fig.update_yaxes(title_text="Value", showgrid=True)
        fig.update_layout(
            title="UV-Vis Spectra (Grid)",
            template="plotly_white",
            width=1600,
            height=600 * rows,
            hovermode="closest",
        )
        return fig, "uvvis_grid_spectra.html"

    def _create_separate_plots(
        self, measurements, color_scheme, channels, x_axis="wavelength", color_map=None
    ):
        figs, names = [], []
        for i, measurement in enumerate(measurements):
            fig = go.Figure()
            wavelength = measurement["wavelength"]
            display_name = measurement.get("variation", measurement["sample_name"])
            meas_name = measurement["measurement_name"]
            color = self._pick_color(color_map, color_scheme, display_name, i)

            y = measurement.get("intensity")
            if y is None or len(y) == 0:
                continue

            # Abbreviate channel names
            channel_abbrev = ""
            meas_name_lower = meas_name.lower()
            if "reflection" in meas_name_lower:
                channel_abbrev = "R"
            elif "transmission" in meas_name_lower:
                channel_abbrev = "T"
            elif "absorption" in meas_name_lower:
                channel_abbrev = "A"

            legend_label = channel_abbrev if channel_abbrev else meas_name

            # Convert x-axis if needed
            if x_axis == "energy":
                x_data = 1239.841984 / wavelength
                x_title = "Photon Energy [eV]"
            else:
                x_data = wavelength
                x_title = "Wavelength [nm]"

            fig.add_trace(
                go.Scatter(
                    x=x_data,
                    y=y,
                    mode="lines",
                    name=legend_label,
                    line=dict(color=color, width=2),
                    hovertemplate=f"<b>{display_name}</b><br>{x_title}: %{{x:.2f}}<br>Value: %{{y:.4f}}<extra></extra>",
                )
            )
            fig.update_layout(
                title=f"{display_name} - {meas_name}",
                xaxis_title=x_title,
                yaxis_title="Value",
                template="plotly_white",
                width=1200,
                height=700,
                showlegend=True,
            )
            fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="lightgray")
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="lightgray")
            figs.append(fig)
            names.append(f"uvvis_{display_name}_{meas_name}.html")
        return figs, names

    @staticmethod
    def _find_peaks_and_fit_gaussian(x, y):
        """Find peaks in derivative and fit Gaussian"""
        peaks = argrelextrema(y, np.greater)[0]
        if peaks.size == 0:
            return []

        results = []
        y_masked = np.copy(y)

        while True:
            peaks = argrelextrema(y_masked, np.greater)[0]
            if peaks.size == 0:
                break

            peak = peaks[np.argmax(y_masked[peaks])]
            peak_energy = x[peak]

            if len(results) > 0 and y_masked[peak] < results[0][1][0] / 4:
                break

            fitting_range = (x > peak_energy - 0.1) & (x < peak_energy + 0.1)
            width = 0.05

            try:
                popt, _ = curve_fit(
                    UVVisPlotManager._gaussian,
                    x[fitting_range],
                    y[fitting_range],
                    p0=[y[peak], peak_energy, width],
                )
                results.append((popt[1], popt, fitting_range))
            except RuntimeError:
                break

            y_masked[fitting_range] = 0

        return results

    @staticmethod
    def _find_best_tauc_fit(x, y, min_range=0.15, max_range=0.35):
        """Find best linear fit in Tauc plot"""
        best_fit = None
        best_r2 = -np.inf

        for start in range(len(x)):
            for end in range(start + 5, len(x)):
                x_fit = x[start:end]
                y_fit = y[start:end]

                if len(x_fit) < 10:
                    continue

                energy_range = x_fit[-1] - x_fit[0]
                if energy_range < min_range or energy_range > max_range:
                    continue

                slope, intercept, r_value, *_ = linregress(x_fit, y_fit)
                r_squared = r_value**2

                if slope < 0 or r_squared < 0.98:
                    continue

                x0 = -intercept / slope
                if 0.5 < x0 < 3.5:
                    if r_squared > best_r2:
                        best_r2 = r_squared
                        best_fit = {
                            "x_fit": x_fit,
                            "y_fit": y_fit,
                            "slope": slope,
                            "intercept": intercept,
                            "bandgap": x0,
                            "r2": r_squared,
                        }

        return best_fit
