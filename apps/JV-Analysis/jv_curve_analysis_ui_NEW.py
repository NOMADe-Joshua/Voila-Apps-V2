"""
Enhanced JV Curve Analysis UI Component
Features improved filtering, sample selection, and legend configuration
"""

import ipywidgets as widgets
import pandas as pd
import plotly.express as px
from IPython.display import HTML, clear_output, display


class EnhancedJVCurveAnalysisUI:
    """Enhanced UI for detailed JV curve analysis with per-sample filtering."""

    def __init__(self):
        self.filter_rows = []
        self.sample_specific_filters = {}  # Dict: sample -> {pixels: [...], cycles: [...], directions: [...]}
        self.filter_columns = [
            "Voc(V)",
            "Jsc(mA/cm2)",
            "FF(%)",
            "PCE(%)",
            "V_mpp(V)",
            "J_mpp(mA/cm2)",
            "P_mpp(mW/cm2)",
            "R_series(Ohmcm2)",
            "R_shunt(Ohmcm2)",
        ]
        self.all_samples = []
        self.data_cache = None
        self._create_widgets()
        self._setup_observers()

    def _create_widgets(self):
        """Create all UI components."""

        # ========== PLOT SETTINGS ==========
        self.mode_dropdown = widgets.Dropdown(
            options=[
                ("Best device per condition", "best_per_condition"),
                ("All JV curves (no numeric filter)", "all_curves_unfiltered"),
            ],
            value="best_per_condition",
            description="Plot mode:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="350px"),
        )

        self.scale_dropdown = widgets.Dropdown(
            options=[("Linear", "linear"), ("Logarithmic ln(|J|)", "log_e")],
            value="linear",
            description="Current axis:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="350px"),
        )

        # Color scheme selector
        color_schemes = {
            "Viridis": "viridis",
            "Plasma": "plasma",
            "Inferno": "inferno",
            "Magma": "magma",
            "Blues": "blues",
            "Reds": "reds",
            "Greens": "greens",
            "Plotly": "plotly",
            "Set1": "set1",
            "Set2": "set2",
        }
        self.color_scheme_dropdown = widgets.Dropdown(
            options=list(color_schemes.keys()),
            value="Viridis",
            description="Color scheme:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="350px"),
        )
        self.color_schemes_dict = color_schemes

        # Plot style: Points + Lines
        self.plot_style_dropdown = widgets.Dropdown(
            options=[
                ("Lines only", "lines"),
                ("Points + Lines", "lines+markers"),
                ("Points only", "markers"),
            ],
            value="lines+markers",
            description="Plot style:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="350px"),
        )

        plot_settings_box = widgets.VBox(
            [
                widgets.HTML("<b>📊 Plot Settings</b>"),
                self.mode_dropdown,
                self.scale_dropdown,
                self.color_scheme_dropdown,
                self.plot_style_dropdown,
            ],
            layout=widgets.Layout(border="1px solid #ddd", padding="10px"),
        )

        # ========== CONDITION FILTER ==========
        self.exclude_conditions_select = widgets.SelectMultiple(
            options=[],
            value=(),
            description="Exclude:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="350px", height="120px"),
        )

        condition_box = widgets.VBox(
            [
                widgets.HTML("<b>🔍 Condition Filter</b>"),
                widgets.HTML(
                    "<p style='margin:0 0 8px 0; color:#666;'>Select conditions to exclude.</p>"
                ),
                self.exclude_conditions_select,
            ],
            layout=widgets.Layout(border="1px solid #ddd", padding="10px"),
        )

        # ========== NUMERIC FILTERS (comes FIRST before pixel/cycle) ==========
        self.add_filter_button = widgets.Button(
            description="Add Filter", button_style="primary", layout=widgets.Layout(width="120px")
        )
        self.remove_filter_button = widgets.Button(
            description="Remove Filter", button_style="danger", layout=widgets.Layout(width="120px")
        )

        self.numeric_filter_rows = widgets.VBox()
        self._add_filter_row(None)

        numeric_box = widgets.VBox(
            [
                widgets.HTML("<b>🎯 Numeric Filters (applies to all samples)</b>"),
                widgets.HTML(
                    "<p style='margin:0 0 8px 0; color:#666;'>Set value ranges - applies BEFORE sample selection.</p>"
                ),
                widgets.HBox([self.add_filter_button, self.remove_filter_button]),
                self.numeric_filter_rows,
            ],
            layout=widgets.Layout(border="1px solid #ddd", padding="10px"),
        )

        # ========== SAMPLE DROPDOWN + PIXEL/CYCLE SELECTION ==========
        self.sample_dropdown = widgets.Dropdown(
            options=[],
            value=None,
            description="Select sample:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="350px"),
        )
        self.sample_dropdown.observe(self._on_sample_changed, names="value")

        self.pixel_select = widgets.SelectMultiple(
            options=[],
            value=(),
            description="Pixels:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px", height="120px"),
        )
        self.pixel_select.observe(self._on_pixel_cycle_changed, names="value")

        self.cycle_select = widgets.SelectMultiple(
            options=[],
            value=(),
            description="Cycles:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px", height="120px"),
        )
        self.cycle_select.observe(self._on_pixel_cycle_changed, names="value")

        self.set_for_all_button = widgets.Button(
            description="Copy to all samples",
            button_style="info",
            tooltip="Apply pixel/cycle selection to all samples",
            layout=widgets.Layout(width="180px"),
        )
        self.set_for_all_button.on_click(self._on_set_for_all)

        self.direction_select = widgets.SelectMultiple(
            options=[],
            value=(),
            description="Scan directions:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px", height="120px"),
        )
        self.direction_select.observe(self._on_pixel_cycle_changed, names="value")

        sample_box = widgets.VBox(
            [
                widgets.HTML("<b>📦 Sample-Specific Pixel / Cycle Selection</b>"),
                widgets.HTML(
                    "<p style='margin:0 0 8px 0; color:#666;'>Choose which pixels, cycles, and scan directions to include for each sample. Leave a list empty to include all values.</p>"
                ),
                self.sample_dropdown,
                widgets.HBox([self.pixel_select, self.cycle_select, self.direction_select]),
                self.set_for_all_button,
            ],
            layout=widgets.Layout(border="1px solid #ddd", padding="10px"),
        )

        # ========== LEGEND CONFIGURATION ==========
        self.legend_batch_checkbox = widgets.Checkbox(value=True, description="Batch name")
        self.legend_condition_checkbox = widgets.Checkbox(value=True, description="Condition")
        self.legend_sample_checkbox = widgets.Checkbox(value=True, description="Sample")
        self.legend_pixel_checkbox = widgets.Checkbox(value=True, description="Pixel")
        self.legend_cycle_checkbox = widgets.Checkbox(value=True, description="Cycle")
        self.legend_direction_checkbox = widgets.Checkbox(value=True, description="Scan direction")
        self.legend_pce_checkbox = widgets.Checkbox(value=False, description="PCE (%)")

        legend_box = widgets.VBox(
            [
                widgets.HTML("<b>📝 Legend Configuration</b>"),
                widgets.HTML(
                    "<p style='margin:0 0 8px 0; color:#666;'>Choose which information to display in legend for each curve.</p>"
                ),
                widgets.HBox(
                    [
                        widgets.VBox([self.legend_batch_checkbox, self.legend_condition_checkbox]),
                        widgets.VBox([self.legend_sample_checkbox, self.legend_pixel_checkbox]),
                        widgets.VBox([self.legend_cycle_checkbox, self.legend_direction_checkbox]),
                        widgets.VBox([self.legend_pce_checkbox]),
                    ]
                ),
            ],
            layout=widgets.Layout(border="1px solid #ddd", padding="10px"),
        )

        # ========== PLOT FILTER OPTIONS ==========
        self.plot_filter_checkbox = widgets.Checkbox(
            value=True, description="Apply plot filter (remove boundary artifacts)", indent=False
        )

        plot_filter_box = widgets.VBox(
            [
                widgets.HTML("<b>🔧 Plot Processing Options</b>"),
                self.plot_filter_checkbox,
                widgets.HTML(
                    "<p style='margin:5px 0 0 0; color:#666; font-size:11px;'>Removes stray zero points and unusual jumps at curve boundaries.</p>"
                ),
            ],
            layout=widgets.Layout(border="1px solid #ddd", padding="10px"),
        )

        # ========== PLOT BUTTON ==========
        self.plot_button = widgets.Button(
            description="Plot JV Curves",
            button_style="success",
            layout=widgets.Layout(width="200px", height="40px"),
        )

        # ========== COMBINE ALL ==========
        self.layout = widgets.VBox(
            [
                widgets.HTML("<h3>🔬 JV Curve Analysis</h3>"),
                widgets.HTML(
                    "<p>Analyze JV curves with advanced filtering and legend customization.</p>"
                ),
                plot_settings_box,
                condition_box,
                numeric_box,
                sample_box,
                legend_box,
                plot_filter_box,
                widgets.HBox([self.plot_button], layout=widgets.Layout(padding="10px")),
                widgets.HTML("<hr style='margin: 20px 0;'>"),
                widgets.HTML("<h4>📊 Analysis Results</h4>"),
            ]
        )

        # Output areas
        self.status_output = widgets.Output(
            layout=widgets.Layout(
                border="1px solid #ccc",
                padding="12px",
                margin="8px 0",
                overflow_y="auto",
                height="150px",
            )
        )
        self.plotted_content = widgets.Output(
            layout=widgets.Layout(
                border="1px solid #ccc", padding="12px", margin="8px 0", overflow_y="auto"
            )
        )

        self.layout.children = list(self.layout.children) + [
            self.status_output,
            self.plotted_content,
        ]

    def _setup_observers(self):
        """Setup event observers."""
        self.add_filter_button.on_click(self._add_filter_row)
        self.remove_filter_button.on_click(self._remove_filter_row)

    def _create_numeric_filter_row(self):
        """Create a single numeric filter row."""
        column_dropdown = widgets.Dropdown(
            options=self.filter_columns,
            value=self.filter_columns[0],
            layout=widgets.Layout(width="42%"),
        )
        operator_dropdown = widgets.Dropdown(
            options=[">", ">=", "<", "<=", "==", "!="],
            value=">",
            layout=widgets.Layout(width="18%"),
        )
        value_input = widgets.Text(placeholder="Value", layout=widgets.Layout(width="20%"))
        delete_button = widgets.Button(
            description="✕", button_style="", layout=widgets.Layout(width="30px")
        )

        row = widgets.HBox([column_dropdown, operator_dropdown, value_input, delete_button])
        delete_button.on_click(lambda b: self._remove_specific_filter_row(row))
        return row

    def _add_filter_row(self, _):
        """Add a new filter row."""
        self.filter_rows.append(self._create_numeric_filter_row())
        self.numeric_filter_rows.children = tuple(self.filter_rows)

    def _remove_filter_row(self, _):
        """Remove the last filter row."""
        if len(self.filter_rows) > 1:
            self.filter_rows.pop()
            self.numeric_filter_rows.children = tuple(self.filter_rows)

    def _remove_specific_filter_row(self, row):
        """Remove a specific filter row."""
        if row in self.filter_rows and len(self.filter_rows) > 1:
            self.filter_rows.remove(row)
            self.numeric_filter_rows.children = tuple(self.filter_rows)

    def _on_sample_changed(self, change):
        """Handle sample selection change."""
        selected_sample = change["new"]
        if selected_sample is None or self.data_cache is None:
            return

        # Update pixel and cycle options for selected sample
        df = self.data_cache
        sample_data = df[df["sample"] == selected_sample]

        if "px_number" in sample_data.columns:
            pixels = sorted([str(v) for v in sample_data["px_number"].dropna().unique().tolist()])
        else:
            pixels = []
        self.pixel_select.options = pixels

        if "cycle_number" in sample_data.columns:
            cycles = sorted(
                [int(v) for v in sample_data["cycle_number"].dropna().unique().tolist()]
            )
            cycle_options = [(f"Cycle {c}", c) for c in cycles]
        else:
            cycle_options = []
        self.cycle_select.options = cycle_options

        if "direction" in sample_data.columns:
            directions = sorted(
                [str(v) for v in sample_data["direction"].dropna().unique().tolist()]
            )
        else:
            directions = []
        self.direction_select.options = directions

        # Load stored values for this sample if they exist
        if selected_sample in self.sample_specific_filters:
            stored = self.sample_specific_filters[selected_sample]
            self.pixel_select.value = tuple(stored.get("pixels", []))
            self.cycle_select.value = tuple(stored.get("cycles", []))
            self.direction_select.value = tuple(stored.get("directions", []))
        else:
            self.pixel_select.value = ()
            self.cycle_select.value = ()
            self.direction_select.value = ()

    def _on_pixel_cycle_changed(self, change):
        """Store pixel/cycle/direction selection for current sample."""
        selected_sample = self.sample_dropdown.value
        if selected_sample is None:
            return

        self.sample_specific_filters[selected_sample] = {
            "pixels": list(self.pixel_select.value),
            "cycles": list(self.cycle_select.value),
            "directions": list(self.direction_select.value),
        }

    def _on_set_for_all(self, b):
        """Apply current pixel/cycle/direction selection to all samples."""
        current_pixels = list(self.pixel_select.value)
        current_cycles = list(self.cycle_select.value)
        current_directions = list(self.direction_select.value)

        for sample in self.all_samples:
            self.sample_specific_filters[sample] = {
                "pixels": current_pixels,
                "cycles": current_cycles,
                "directions": current_directions,
            }

    def set_data(self, data):
        """Update available options from loaded JV data."""
        if not data or "jvc" not in data or data["jvc"].empty:
            self.exclude_conditions_select.options = []
            self.sample_dropdown.options = []
            self.all_samples = []
            self.data_cache = None
            self.direction_select.options = []
            return

        df = data["jvc"]
        self.data_cache = df

        # Update conditions
        if "condition" in df.columns:
            conditions = sorted([str(v) for v in df["condition"].dropna().unique().tolist()])
        else:
            conditions = sorted([str(v) for v in df["sample"].dropna().unique().tolist()])
        self.exclude_conditions_select.options = conditions

        # Update samples
        samples = sorted([str(v) for v in df["sample"].dropna().unique().tolist()])
        self.all_samples = samples
        self.sample_dropdown.options = samples if samples else []

        if samples:
            # Set first sample as default and update pixel/cycle
            self.sample_dropdown.value = samples[0]

    # Getter methods
    def get_plot_mode(self):
        return self.mode_dropdown.value

    def use_log_current(self):
        return self.scale_dropdown.value == "log_e"

    def get_color_scheme(self):
        return self.color_schemes_dict.get(self.color_scheme_dropdown.value, "viridis")

    def get_plot_style(self):
        return self.plot_style_dropdown.value

    def get_excluded_conditions(self):
        return list(self.exclude_conditions_select.value)

    def get_sample_specific_filters(self):
        """Return per-sample pixel/cycle filters."""
        return self.sample_specific_filters.copy()

    def get_numeric_filters(self):
        """Return numeric filters."""
        filters = []
        for group in self.filter_rows:
            if len(group.children) < 3:
                continue
            column = group.children[0].value
            operator = group.children[1].value
            raw_value = str(group.children[2].value).strip()
            if raw_value == "":
                continue
            try:
                float(raw_value)
            except ValueError:
                continue
            filters.append((column, operator, raw_value))
        return filters

    def get_legend_config(self):
        """Return legend configuration checkboxes."""
        return {
            "batch": self.legend_batch_checkbox.value,
            "condition": self.legend_condition_checkbox.value,
            "sample": self.legend_sample_checkbox.value,
            "pixel": self.legend_pixel_checkbox.value,
            "cycle": self.legend_cycle_checkbox.value,
            "direction": self.legend_direction_checkbox.value,
            "pce": self.legend_pce_checkbox.value,
        }

    def use_plot_filter(self):
        """Return whether to apply plot filter."""
        return self.plot_filter_checkbox.value

    def set_plot_callback(self, callback):
        """Set callback for plot button."""
        self.plot_button.on_click(callback)

    def get_widget(self):
        """Return the main widget."""
        return self.layout
