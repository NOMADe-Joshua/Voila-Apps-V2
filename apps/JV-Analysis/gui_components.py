"""
GUI Components Module
Contains all UI components for the JV Analysis Dashboard.
"""

__author__ = "Edgar Nandayapa"
__institution__ = "Helmholtz-Zentrum Berlin"
__created__ = "August 2025"
# adjusted by Joshua from KIT :)

import base64
import io
import json
import zipfile

import ipywidgets as widgets
import plotly.express as px
import plotly.graph_objects as go
import requests
from diagnostic_helper import debug_logger
from IPython.display import HTML, Javascript, Markdown, clear_output, display

from perotf_utils.auth_ui import AuthenticationUI  # noqa: F401  (re-exported for app.py)


class WidgetFactory:
    @staticmethod
    def create_button(description, button_style="", tooltip="", icon="", min_width=True):
        layout = widgets.Layout(min_width="150px") if min_width else widgets.Layout(width="auto")
        return widgets.Button(
            description=description,
            button_style=button_style,
            tooltip=tooltip,
            icon=icon,
            layout=layout,
        )

    @staticmethod
    def create_dropdown(options, description="", width="standard", value=None):
        dropdown = widgets.Dropdown(options=options, description=description)
        if value is not None:
            dropdown.value = value
        return dropdown

    @staticmethod
    def create_text_input(placeholder="", description="", width="standard", password=False):
        widget_class = widgets.Password if password else widgets.Text
        return widget_class(
            placeholder=placeholder, description=description, style={"description_width": "initial"}
        )

    @staticmethod
    def create_output(min_height="standard", scrollable=False, border=True):
        layout_props = {}
        if scrollable:
            layout_props.update({"width": "400px", "height": "300px", "overflow": "scroll"})
        if border:
            layout_props.update(
                {"border": "1px solid #eee", "padding": "10px", "margin": "10px 0 0 0"}
            )
        return widgets.Output(layout=widgets.Layout(**layout_props))

    @staticmethod
    def create_radio_buttons(
        options, description="", value=None, width="standard"
    ):  # FIXED: Added missing closing parenthesis
        radio = widgets.RadioButtons(options=options, description=description)
        if value is not None:
            radio.value = value
        return radio

    @staticmethod
    def create_filter_row():
        dropdown1 = widgets.Dropdown(
            options=["Voc(V)", "Jsc(mA/cm2)", "FF(%)", "PCE(%)", "V_MPP(V)", "J_MPP(mA/cm2)"],
            layout=widgets.Layout(width="66%"),
        )
        dropdown2 = widgets.Dropdown(
            options=[">", ">=", "<", "<=", "==", "!="], layout=widgets.Layout(width="33%")
        )
        text_input = widgets.Text(placeholder="Write a value", layout=widgets.Layout(width="33%"))
        return widgets.HBox([dropdown1, dropdown2, text_input])


class FilterUI:
    """Handles filter-related UI components with sample-based condition selection"""

    def __init__(self):
        self.filter_presets = {
            "Default": [
                ("PCE(%)", "<", "40"),
                ("FF(%)", "<", "89"),
                ("FF(%)", ">", "24"),
                ("Voc(V)", "<", "2.5"),
                ("Voc(V)", ">", "0.5"),
                ("Jsc(mA/cm2)", "<", "0"),
                ("Jsc(mA/cm2)", ">", "-30"),
            ],
            "Preset 2": [("FF(%)", "<", "15"), ("PCE(%)", ">=", "10")],
        }
        self._create_widgets()
        self._setup_observers()
        self._apply_preset()  # Initialize with default preset

    def _create_widgets(self):
        """Create filter widgets"""
        self.preset_dropdown = WidgetFactory.create_dropdown(
            options=list(self.filter_presets.keys()), description="Filters"
        )
        self.preset_dropdown.layout.width = "fit-content"
        self.preset_dropdown.layout.align_self = "flex-end"

        # Direction filter
        self.direction_radio = WidgetFactory.create_radio_buttons(
            options=["Both", "Reverse", "Forward"], value="Both", description="Direction:"
        )

        self.add_button = WidgetFactory.create_button("Add Filter", "primary")
        self.remove_button = WidgetFactory.create_button("Remove Filter", "danger")
        self.apply_preset_button = WidgetFactory.create_button("Load Preset", "info")
        self.apply_filter_button = WidgetFactory.create_button("Apply Filter", "success")

        self.confirmation_output = WidgetFactory.create_output()
        self.main_output = WidgetFactory.create_output(scrollable=True)

        # Create initial filter row
        self.widget_groups = [WidgetFactory.create_filter_row()]
        self.groups_container = widgets.VBox(self.widget_groups)

        # Sample-based condition selection
        self.condition_toggle_button = widgets.Button(
            description="▼ Sample Selection",
            button_style="",
            layout=widgets.Layout(width="250px"),
            style={"font_weight": "bold"},
        )

        self.condition_selection_content = widgets.Output(
            layout=widgets.Layout(display="flex", width="100%", overflow="visible")
        )

        # Store data and selections
        self.sample_data = None
        self.selected_samples = set()
        self.sample_checkboxes = {}

        # Status widgets
        self.condition_status_output = widgets.Output()

        self.condition_selection_box = widgets.VBox(
            [self.condition_toggle_button, self.condition_selection_content],
            layout=widgets.Layout(border="1px solid #ddd", padding="10px", margin="5px 0"),
        )

        # ========================================
        # CYCLE FILTER WIDGETS - CREATE ONLY ONCE! ✅
        # ========================================
        self.cycle_filter_label = widgets.HTML(
            value="<b>Cycle Filter:</b>",
            layout=widgets.Layout(display="none", margin="10px 0 5px 0"),
        )

        self.cycle_dropdown = widgets.Dropdown(
            options=["All Cycles", "Best Cycle Only", "Specific Cycles"],
            value="Best Cycle Only",
            description="Show:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="250px", margin="5px 0", display="none"),
        )

        self.specific_cycles_dropdown = widgets.SelectMultiple(
            options=[],
            description="Specific:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="250px", height="100px", margin="5px 0", display="none"),
        )

        self.cycle_info_label = widgets.HTML(
            value="", layout=widgets.Layout(margin="10px 0", display="none")
        )

        # ========================================
        # CREATE direction_container - USING THE WIDGETS WE JUST CREATED ✅
        # ========================================
        self.direction_container = widgets.VBox(
            [
                widgets.HTML("<b>Filter by Cell Direction:</b>"),
                self.direction_radio,
                widgets.HTML("<hr style='margin: 15px 0 10px 0;'>"),
                self.cycle_filter_label,
                self.cycle_dropdown,
                self.specific_cycles_dropdown,
                self.cycle_info_label,
            ]
        )

        self.filter_conditions_container = widgets.VBox(
            [widgets.HTML("<b>Filter Conditions:</b>"), self.groups_container]
        )

        self.controls = widgets.VBox(
            [
                self.add_button,
                self.remove_button,
                self.preset_dropdown,
                self.apply_preset_button,
                widgets.HBox([self.apply_filter_button]),
            ],
            layout=widgets.Layout(width="200px"),
        )

        self.top_section = widgets.HBox(
            [
                self.controls,
                widgets.VBox([self.direction_container, self.filter_conditions_container]),
                self.main_output,
            ]
        )

        # FINAL LAYOUT
        self.layout = widgets.VBox([self.top_section, self.condition_selection_box])

    def _setup_observers(self):
        """Setup event observers"""
        self.add_button.on_click(self._add_filter_row)
        self.remove_button.on_click(self._remove_filter_row)
        self.apply_preset_button.on_click(self._apply_preset)
        self.condition_toggle_button.on_click(self._toggle_condition_selection)

        # CRITICAL: Cycle dropdown observer MUST be added
        self.cycle_dropdown.observe(self._on_cycle_mode_change, names="value")

    def _on_cycle_mode_change(self, change):
        """Handle cycle mode changes"""
        # CRITICAL: Log the change for debugging
        print(f"🔄 Cycle mode changed to: {change['new']}")

        if change["new"] == "Specific Cycles":
            self.specific_cycles_dropdown.layout.display = "flex"
            print("   ✅ Showing specific cycles dropdown")
        else:
            self.specific_cycles_dropdown.layout.display = "none"
            print("   ❌ Hiding specific cycles dropdown")

    def _add_filter_row(self, b):
        """Add a new filter row"""
        self.widget_groups.append(WidgetFactory.create_filter_row())
        self.groups_container.children = self.widget_groups

    def _remove_filter_row(self, b):
        """Remove the last filter row"""
        if len(self.widget_groups) > 1:
            self.widget_groups.pop()
            self.groups_container.children = self.widget_groups

    def _apply_preset(self, b=None):
        """Apply selected preset"""
        selected_preset = self.preset_dropdown.value
        self.widget_groups.clear()

        if selected_preset in self.filter_presets:
            for variable, operator, value in self.filter_presets[selected_preset]:
                group = WidgetFactory.create_filter_row()
                group.children[0].value = variable
                group.children[1].value = operator
                group.children[2].value = value
                self.widget_groups.append(group)
        else:
            self.widget_groups.append(WidgetFactory.create_filter_row())

        self.groups_container.children = self.widget_groups

    def _toggle_condition_selection(self, b):
        """Toggle sample selection visibility"""
        if self.condition_selection_content.layout.display == "none":
            self.condition_selection_content.layout.display = "flex"
            self.condition_toggle_button.description = "▼ Sample Selection"
        else:
            self.condition_selection_content.layout.display = "none"
            self.condition_toggle_button.description = "▶ Sample Selection"

    def set_sample_data(self, data):
        """Set the data and create the sample selector"""
        self.sample_data = data

        if data and "jvc" in data:
            df = data["jvc"]

            # Check for cycle data
            has_cycles = "cycle_number" in df.columns and df["cycle_number"].notna().any()

            # CRITICAL DEBUG: Print current state
            print("\n🔍 DEBUG - Cycle Widget Visibility Check:")
            print(f"   has_cycles: {has_cycles}")
            print(f"   cycle_filter_label exists: {hasattr(self, 'cycle_filter_label')}")
            print(f"   cycle_dropdown exists: {hasattr(self, 'cycle_dropdown')}")

            if has_cycles:
                print("\n✅ Cycle data FOUND - Making widgets VISIBLE")

                # CRITICAL FIX: Set display to 'flex' (NOT 'block'!)
                self.cycle_filter_label.layout.display = "flex"
                self.cycle_dropdown.layout.display = "flex"
                self.cycle_info_label.layout.display = "flex"

                # DIAGNOSTIC: Verify the change took effect
                print("   After setting visible:")
                print(
                    f"      cycle_filter_label.layout.display = '{self.cycle_filter_label.layout.display}'"
                )
                print(
                    f"      cycle_dropdown.layout.display = '{self.cycle_dropdown.layout.display}'"
                )
                print(
                    f"      cycle_info_label.layout.display = '{self.cycle_info_label.layout.display}'"
                )

                # Get available cycles
                cycle_pixels = df[df["cycle_number"].notna()]
                available_cycles = sorted(cycle_pixels["cycle_number"].unique().tolist())

                # Update dropdown options
                self.cycle_dropdown.options = ["All Cycles", "Best Cycle Only", "Specific Cycles"]
                self.specific_cycles_dropdown.options = [
                    f"Cycle {int(c)}" for c in available_cycles
                ]

                print("   Dropdown options set:")
                print(f"      Main dropdown: {self.cycle_dropdown.options}")
                print(f"      Specific cycles: {self.specific_cycles_dropdown.options}")

                # Statistics
                unique_pixels = cycle_pixels.groupby(["sample", "px_number"]).size()
                pixels_with_multiple_cycles = (
                    cycle_pixels.groupby(["sample", "px_number"])["cycle_number"].nunique() > 1
                ).sum()

                # Enhanced info label
                info_html = f"""
                <div style="background-color: #d4edda; padding: 12px; border-radius: 6px; margin: 5px 0; border-left: 4px solid #28a745;">
                    <b>✅ Cycle Data Detected:</b><br>
                    • <b>{len(available_cycles)}</b> cycles available: {available_cycles}<br>
                    • <b>{len(unique_pixels)}</b> pixels with cycle data<br>
                    • <b>{pixels_with_multiple_cycles}</b> pixels with multiple cycles<br>
                    <br>
                    <b>Filter Options:</b><br>
                    • <b>All Cycles:</b> Show all measurements (no filtering)<br>
                    • <b>Best Cycle Only:</b> Keep only highest PCE per pixel (DEFAULT)<br>
                    • <b>Specific Cycles:</b> Select which cycles to include from dropdown below
                </div>
                """
                self.cycle_info_label.value = info_html

                print("\n🎯 Cycle Filter UI Configured:")
                print(f"   Available cycles: {available_cycles}")
                print("   Widgets should now be VISIBLE in the UI")
                print(f"   Default selection: {self.cycle_dropdown.value}")

                # EXTRA DEBUG: Check if widgets are actually in the container
                print(
                    f"\n   Widget container children count: {len(self.direction_container.children)}"
                )
                for i, child in enumerate(self.direction_container.children):
                    child_type = type(child).__name__
                    print(f"      [{i}] {child_type}")
                    if hasattr(child, "layout") and hasattr(child.layout, "display"):
                        print(f"          display: {child.layout.display}")

            else:
                print("\n❌ NO cycle data - Hiding widgets")

                # HIDE cycle filter controls
                self.cycle_filter_label.layout.display = "none"
                self.cycle_dropdown.layout.display = "none"
                self.specific_cycles_dropdown.layout.display = "none"

                # Show "no cycles" info
                self.cycle_info_label.value = """
                <div style="background-color: #d1ecf1; padding: 10px; border-radius: 4px; margin: 5px 0; border-left: 4px solid #0c5460;">
                    ℹ️ <b>No cycle data</b> in this dataset
                </div>
                """
                self.cycle_info_label.layout.display = "flex"

                print("   Cycle filter hidden")

            # Create sample selector
            self._create_condition_selector()
        else:
            print("   ⚠️ No data or 'jvc' column available")

    def get_cycle_filter_settings(self):
        """Get cycle filter settings"""
        if self.cycle_dropdown.layout.display == "none":
            # No cycle data available
            return {"mode": "disabled"}

        mode = self.cycle_dropdown.value

        if mode == "Best Cycle Only":
            return {"mode": "best_only"}
        elif mode == "All Cycles":
            return {"mode": "all"}
        elif mode == "Specific Cycles":
            selected = self.specific_cycles_dropdown.value
            # Extract cycle numbers from "Cycle 0", "Cycle 1", etc.
            cycle_numbers = [int(c.split()[1]) for c in selected]
            return {"mode": "specific", "cycles": cycle_numbers}
        else:
            return {"mode": "all"}

    def _create_condition_selector(self):
        """Create sample-based selector interface grouped by batch"""
        with self.condition_selection_content:
            clear_output(wait=True)

            if not self.sample_data or "jvc" not in self.sample_data:
                print("No data available for sample selection")
                return

            df = self.sample_data["jvc"]

            # Title
            display(widgets.HTML("<h4>Select Samples to Include in Analysis:</h4>"))

            # Group by batch and sample, then get condition and counts
            batch_sample_info = (
                df.groupby(["batch", "sample", "condition"])
                .agg(
                    {
                        "cell": "nunique",  # unique cells per sample
                        "sample": "size",  # total measurements per sample
                    }
                )
                .rename(columns={"cell": "num_cells", "sample": "num_measurements"})
            )

            print("Dataset Overview:")
            total_samples = len(batch_sample_info)
            total_cells = batch_sample_info["num_cells"].sum()
            total_measurements = batch_sample_info["num_measurements"].sum()
            print(f"   • {total_samples} samples")
            print(f"   • {total_cells} cells")
            print(f"   • {total_measurements} measurements")

            # Quick selection buttons
            clear_all_button = widgets.Button(
                description="Clear All",
                button_style="warning",
                layout=widgets.Layout(width="100px"),
            )

            select_all_button = widgets.Button(
                description="Select All", button_style="info", layout=widgets.Layout(width="100px")
            )

            # Button handlers for sample-based selection
            def clear_all_samples(b):
                """Clear all sample selections"""
                self.selected_samples.clear()
                self._update_sample_display()
                self._update_sample_status()

            def select_all_samples(b):
                """Select all available samples"""
                self.selected_samples = set()
                selected_count = 0
                for index, info in batch_sample_info.iterrows():
                    batch, sample, condition = index
                    sample_key = f"{batch}_{sample}"
                    self.selected_samples.add(sample_key)
                    selected_count += 1

                self._update_sample_display()
                self._update_sample_status()

            clear_all_button.on_click(clear_all_samples)
            select_all_button.on_click(select_all_samples)

            button_row = widgets.HBox([clear_all_button, select_all_button])
            display(button_row)

            # Create sample checkboxes grouped by batch
            self.sample_checkboxes = {}

            # Group data by batch for display
            batches = df["batch"].unique()
            batch_widgets = []

            for batch in sorted(batches):
                batch_df = df[df["batch"] == batch]
                batch_sample_info_for_display = (
                    batch_df.groupby(["sample", "condition"])
                    .agg({"cell": "nunique", "sample": "size"})
                    .rename(columns={"cell": "num_cells", "sample": "num_measurements"})
                )

                # Get display batch name if available
                display_batch = batch
                if "display_batch" in batch_df.columns:
                    display_batch = batch_df["display_batch"].iloc[0]

                # Create batch header
                batch_header = widgets.HTML(f"<h5>📁 Batch: {display_batch}</h5>")

                # Create sample checkboxes for this batch
                sample_widgets = []
                for index, info in batch_sample_info_for_display.iterrows():
                    sample, condition = index
                    num_cells = info["num_cells"]
                    num_measurements = info["num_measurements"]

                    checkbox_label = f"{sample} ({condition}) - {num_cells} cells, {num_measurements} measurements"

                    checkbox = widgets.Checkbox(
                        value=True,
                        description=checkbox_label,
                        style={"description_width": "initial"},
                        layout=widgets.Layout(margin="2px 0 2px 20px", width="auto"),
                    )

                    sample_key = f"{batch}_{sample}"

                    # Handler for sample selection
                    def create_sample_checkbox_handler(sample_key):
                        def handler(change):
                            if change["new"]:
                                self.selected_samples.add(sample_key)
                            else:
                                self.selected_samples.discard(sample_key)
                            self._update_sample_status()

                        return handler

                    checkbox.observe(create_sample_checkbox_handler(sample_key), names="value")
                    self.sample_checkboxes[sample_key] = checkbox
                    sample_widgets.append(checkbox)

                # Add batch section
                batch_section = widgets.VBox([batch_header] + sample_widgets)
                batch_widgets.append(batch_section)

            # Display all batches
            all_batches_display = widgets.VBox(
                batch_widgets, layout=widgets.Layout(width="100%", overflow="visible")
            )
            display(all_batches_display)

            # Status display
            display(widgets.HTML("<h4>Selection Status:</h4>"))
            display(self.condition_status_output)

            # Initialize with all samples selected
            self.selected_samples = set()
            for index, info in batch_sample_info.iterrows():
                batch, sample, condition = index
                sample_key = f"{batch}_{sample}"
                self.selected_samples.add(sample_key)
            self._update_sample_status()

    def _update_sample_display(self):
        """Update checkbox display to match selected_samples set"""
        for sample_key, checkbox in self.sample_checkboxes.items():
            checkbox.value = sample_key in self.selected_samples

    def _update_sample_status(self):
        """Update status display for sample-based selection"""
        with self.condition_status_output:
            clear_output(wait=True)

            if not self.selected_samples:
                print("No samples selected")
                return

            if not self.sample_data or "jvc" not in self.sample_data:
                print("No sample data available")
                return

            df = self.sample_data["jvc"]

            # Calculate statistics for selected samples
            selected_conditions = {}
            total_measurements = 0
            total_cells = 0

            for sample_key in self.selected_samples:
                batch, sample = sample_key.split("_", 1)

                sample_df = df[(df["batch"] == batch) & (df["sample"] == sample)]
                if not sample_df.empty:
                    condition = sample_df["condition"].iloc[0]
                    num_cells = sample_df["cell"].nunique()
                    num_measurements = len(sample_df)

                    if condition not in selected_conditions:
                        selected_conditions[condition] = {
                            "samples": 0,
                            "cells": 0,
                            "measurements": 0,
                        }

                    selected_conditions[condition]["samples"] += 1
                    selected_conditions[condition]["cells"] += num_cells
                    selected_conditions[condition]["measurements"] += num_measurements

                    total_cells += num_cells
                    total_measurements += num_measurements

            print(f"📋 Selected {len(self.selected_samples)} samples:")
            print(f"   📊 Total: {total_cells} cells, {total_measurements} measurements")
            print()

            for condition, stats in sorted(selected_conditions.items()):
                samples = stats["samples"]
                cells = stats["cells"]
                measurements = stats["measurements"]
                print(
                    f"   • {condition}: {samples} samples, {cells} cells, {measurements} measurements"
                )

            # Check if only expected conditions
            expected = {"BL Printing", "Slot_SAM", "Spin_SAM"}
            selected_condition_names = set(selected_conditions.keys())

            if selected_condition_names == expected:
                print("\n🎯 Perfect! Only expected conditions selected.")
            elif selected_condition_names.issubset(expected):
                print("\n✅ Good! Only expected conditions (subset).")
            else:
                unexpected = selected_condition_names - expected
                if unexpected:
                    print(f"\n⚠️ Note: Additional conditions selected: {sorted(unexpected)}")

    def get_selected_items(self):
        """Get list of selected sample_cell combinations from sample selection"""
        if not hasattr(self, "selected_samples") or not self.selected_samples:
            return None

        if not self.sample_data or "jvc" not in self.sample_data:
            return None

        df = self.sample_data["jvc"]
        selected_cell_combinations = []

        # Recreate the batch_sample_info mapping locally
        batch_sample_groups = (
            df.groupby(["batch", "sample", "condition"])
            .agg({"cell": "nunique", "sample": "size"})
            .rename(columns={"cell": "num_cells", "sample": "num_measurements"})
        )

        # Create a mapping from sample_key to (batch, sample)
        sample_key_mapping = {}
        for index, info in batch_sample_groups.iterrows():
            batch, sample, condition = index
            sample_key = f"{batch}_{sample}"
            sample_key_mapping[sample_key] = (batch, sample)

        # Process each selected sample
        for sample_key in self.selected_samples:
            if sample_key in sample_key_mapping:
                batch, sample = sample_key_mapping[sample_key]

                # Get all cells for this sample
                sample_df = df[(df["batch"] == batch) & (df["sample"] == sample)]

                for _, row in sample_df.iterrows():
                    cell_key = f"{row['sample']}_{row['cell']}"
                    if cell_key not in selected_cell_combinations:
                        selected_cell_combinations.append(cell_key)
            else:
                print(f"Sample key '{sample_key}' not found in mapping")

        return selected_cell_combinations

    def get_filter_values(self):
        """Get current filter values"""
        filter_values = []
        for group in self.widget_groups:
            variable = group.children[0].value
            operator = group.children[1].value
            value = group.children[2].value
            filter_values.append((variable, operator, value))
        return filter_values

    def get_direction_value(self):
        """Get selected direction"""
        return self.direction_radio.value

    def set_apply_callback(self, callback):
        """Set callback for apply filter button"""
        self.apply_filter_button.on_click(callback)

    def get_widget(self):
        """Get the main filter widget"""
        return widgets.VBox(
            [
                widgets.HTML("<h3>Select Filters</h3>"),
                widgets.HTML(
                    "<p>Using the dropdowns below, select filters for the data you want to keep, not remove.</p>"
                ),
                self.layout,
            ]
        )


class PlotUI:
    """Handles plot selection UI components"""

    def __init__(self):
        self.plot_presets = {
            "Default": [
                ("Boxplot", "PCE", "by Variable"),
                ("Boxplot", "Voc", "by Variable"),
                ("Boxplot", "Jsc", "by Variable"),
                ("Boxplot", "FF", "by Variable"),
                ("Boxplot", "Hysteresis", "by Variable"),
                ("JV Curve", "Best device per condition", ""),
                ("Boxplot", "all", "by Variable"),  # Added
            ],
            "Preset 2": [
                ("Boxplot", "Voc", "by Cell"),
                ("JV Curve", "Best device only", ""),
                ("Boxplot", "all", "by Variable"),  # Added
            ],
            "Advanced Analysis": [
                ("Boxplot", "PCE", "by Subbatch"),
                ("Boxplot", "Voc", "by Subbatch"),
                ("Boxplot", "Jsc", "by Subbatch"),
                ("Boxplot", "FF", "by Subbatch"),
                ("JV Curve", "Best device per condition", ""),
                ("Boxplot", "all", "by Subbatch"),
            ],
        }
        self.plot_callback = None
        self.reorder_update_callback = None  # Callback to notify when reorder changes
        self.variable_order_state = None
        self.variable_disabled_state = None
        self.variable_disabled_list = []
        self._create_widgets()
        self._setup_observers()
        self._load_preset()

    def _create_widgets(self):
        """Create plot widgets"""
        self.preset_dropdown = WidgetFactory.create_dropdown(
            options=list(self.plot_presets.keys()),
            description="Presets",
        )
        self.preset_dropdown.layout = widgets.Layout(width="150px")

        self.add_button = WidgetFactory.create_button("Add Plot Type", "primary")
        self.remove_button = WidgetFactory.create_button("Remove Plot Type", "danger")
        self.load_preset_button = WidgetFactory.create_button("Load Preset", "info")
        self.plot_button = WidgetFactory.create_button("Plot Selection", "success")

        self.plotted_content = WidgetFactory.create_output()

        # Create initial plot type row
        self.plot_type_groups = [self._create_plot_type_row()]
        self.groups_container = widgets.VBox(self.plot_type_groups)

        # Checkbox for separating scan directions in boxplots
        self.separate_scan_dir_checkbox = widgets.Checkbox(
            value=True,  # CHANGED: Default is now True
            description="Separate Forward/Reverse in Boxplots",
            style={"description_width": "initial"},
            layout=widgets.Layout(margin="10px 0"),
        )

        # Variable reordering widget for boxplots
        self._create_variable_reorder_section()

        # Controls WITHOUT the reorder section (will be placed separately)
        self.controls = widgets.VBox(
            [
                self.add_button,
                self.remove_button,
                self.preset_dropdown,
                self.load_preset_button,
                self.separate_scan_dir_checkbox,
                self.plot_button,
            ]
        )

    def _create_plot_type_row(self):
        """Create a plot type selection row"""
        plot_type_dropdown = WidgetFactory.create_dropdown(
            options=["Boxplot", "JV Curve"], description="Plot Type:", width="100px"
        )

        option1_dropdown = WidgetFactory.create_dropdown(
            options=[], description="Option 1:", width="100px"
        )

        option2_dropdown = WidgetFactory.create_dropdown(
            options=[], description="Option 2:", width="100px"
        )

        # Update options based on plot type
        self._update_plot_options(plot_type_dropdown, option1_dropdown, option2_dropdown)
        plot_type_dropdown.observe(
            lambda change: self._update_plot_options(
                plot_type_dropdown, option1_dropdown, option2_dropdown
            ),
            names="value",
        )

        return widgets.HBox([plot_type_dropdown, option1_dropdown, option2_dropdown])

    def _update_plot_options(self, plot_type_dropdown, option1_dropdown, option2_dropdown):
        """Update option dropdowns based on plot type"""
        plot_type = plot_type_dropdown.value

        if plot_type == "Boxplot":
            # ADD 'all' to the beginning of the options list
            option1_dropdown.options = [
                "all",
                "Voc",
                "Jsc",
                "FF",
                "Hysteresis",
                "PCE",
                "R_ser",
                "R_shu",
                "V_mpp",
                "J_mpp",
                "P_mpp",
            ]
            # Option 2 is ALWAYS the same for boxplots - this is CORRECT
            option2_dropdown.options = [
                "by Batch",
                "by Variable",
                "by Sample",
                "by Cell",
                "by Scan Direction",
                "by Subbatch",
            ]
        elif plot_type == "JV Curve":
            option1_dropdown.options = [
                "All cells",
                "Only working cells",
                "Rejected cells",
                "Best device only",
                "Best device per condition",
                "Separated by cell (all)",
                "Separated by cell (working only)",
                "Separated by substrate (all)",
                "Separated by substrate (working only)",
            ]
            option2_dropdown.options = [""]
        else:
            option1_dropdown.options = []
            option2_dropdown.options = []

    def _setup_observers(self):
        """Setup event observers"""
        self.add_button.on_click(self._add_plot_type)
        self.remove_button.on_click(self._remove_plot_type)
        self.load_preset_button.on_click(self._load_preset)

    def _add_plot_type(self, b):
        """Add new plot type row"""
        self.plot_type_groups.append(self._create_plot_type_row())
        self.groups_container.children = tuple(self.plot_type_groups)

    def _remove_plot_type(self, b):
        """Remove last plot type row"""
        if len(self.plot_type_groups) > 1:
            self.plot_type_groups.pop()
            self.groups_container.children = tuple(self.plot_type_groups)

    def _load_preset(self, b=None):
        """Load selected preset"""
        selected_preset = self.preset_dropdown.value
        self.plot_type_groups.clear()

        if selected_preset in self.plot_presets:
            for plot_type, option1, option2 in self.plot_presets[selected_preset]:
                new_group = self._create_plot_type_row()
                new_group.children[0].value = plot_type
                new_group.children[1].value = option1
                new_group.children[2].value = option2
                self.plot_type_groups.append(new_group)
        else:
            self.plot_type_groups.append(self._create_plot_type_row())

        self.groups_container.children = tuple(self.plot_type_groups)

    def _create_variable_reorder_section(self):
        """Create section for reordering variables in boxplots"""
        self.variable_reorder_section = widgets.VBox(
            layout=widgets.Layout(
                width="100%",
                border="1px solid #ddd",
                padding="15px",
                margin="10px 0",
                border_radius="8px",
                background_color="#fafafa",
                display="none",  # Hidden by default
            )
        )

        # Store for variable order (will be set when data is loaded)
        self.variable_order_list = []
        self.variable_move_up_buttons = []
        self.variable_move_down_buttons = []
        self.reorder_update_callback = None  # Callback to trigger plot regeneration
        self.variable_order_state = widgets.Text(value="[]", layout=widgets.Layout(display="none"))
        self.variable_order_state.add_class("reorder-order-state")
        self.variable_order_state.observe(self._on_variable_order_state_change, names="value")

        self.variable_disabled_list = []
        self.variable_disabled_state = widgets.Text(
            value="[]", layout=widgets.Layout(display="none")
        )
        self.variable_disabled_state.add_class("reorder-disabled-state")
        self.variable_disabled_state.observe(self._on_variable_disabled_state_change, names="value")

    def update_variable_reorder(self, available_variables):
        """Update variable reorder section with available variables"""
        debug_logger.add("REORDER", f"update_variable_reorder() called with: {available_variables}")

        if not available_variables or len(available_variables) == 0:
            debug_logger.add("REORDER", "No variables provided, hiding widget")
            self.variable_reorder_section.layout.display = "none"
            return

        self.variable_order_list = list(available_variables)
        self.variable_disabled_list = []
        debug_logger.add("REORDER", f"Saved variable_order_list: {self.variable_order_list}")
        if self.variable_order_state is not None:
            self.variable_order_state.value = json.dumps(self.variable_order_list)
        if self.variable_disabled_state is not None:
            self.variable_disabled_state.value = "[]"

        self.variable_move_up_buttons = []
        self.variable_move_down_buttons = []

        # Build table rows as HTML
        table_rows_html = ""
        for i, var in enumerate(self.variable_order_list):
            # Parse batch and variation names
            if "&" in str(var):
                parts = str(var).split("&", 1)
                batch_name = parts[0].strip()
                variation_name = parts[1].strip()
            else:
                batch_name = "Unknown"
                variation_name = str(var)

            # Create HTML row with drag-and-drop and enable/disable checkbox
            row_html = f"""
            <tr class="reorder-row" draggable="true" data-index="{i}" data-value="{var}">
                <td style="text-align: center; color: #999; cursor: grab;"><span class="reorder-drag-handle">≡</span></td>
                <td style="text-align: center; padding: 0 6px;">
                    <input type="checkbox" class="reorder-enable-checkbox" checked
                           style="width:15px; height:15px; cursor:pointer; accent-color:#667eea;"
                           title="Include this variation in plots">
                </td>
                <td style="text-align: center; font-weight:600; color:#667eea; font-size:16px;">
                    <span class="reorder-number">{i + 1}</span>
                </td>
                <td>
                    <div style="display:flex; gap:20px; align-items:center;">
                        <span style="color:#999; font-size:13px;">{batch_name}</span>
                        <span style="color:#667eea; font-weight:600;">{variation_name}</span>
                    </div>
                </td>
            </tr>
            """
            table_rows_html += row_html

        # Create full HTML table with drag-and-drop support
        html_content = f"""
        <style>
            .reorder-table {{
                width: 100%;
                border-collapse: collapse;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }}
            .reorder-table tr {{
                border-bottom: 1px solid #e0e0e0;
            }}
            .reorder-table tr:hover {{
                background-color: #f5f5f5;
            }}
            .reorder-table td {{
                padding: 12px;
                vertical-align: middle;
            }}
            .reorder-row {{
                cursor: move;
                transition: background-color 0.2s;
                user-select: none;
            }}
            .reorder-row:hover {{
                background-color: #f0f7ff !important;
            }}
            .reorder-row.drag-over {{
                background-color: #e3f2fd;
                border-top: 3px solid #667eea;
            }}
            .reorder-drag-handle {{
                cursor: grab;
                color: #999;
                font-size: 18px;
                padding: 0 8px;
            }}
            .reorder-drag-handle:active {{
                cursor: grabbing;
            }}
        </style>
        
        <div id="reorder_container">
            <table class="reorder-table">
                <thead>
                    <tr style="background-color: #f9f9f9; border-bottom: 2px solid #ddd;">
                        <th style="width: 30px; text-align: center;">≡</th>
                        <th style="width: 30px; text-align: center;" title="Include in plots">✓</th>
                        <th style="width: 60px; text-align: center;">#</th>
                        <th>Variation</th>
                    </tr>
                </thead>
                <tbody id="reorder_tbody">
                    {table_rows_html}
                </tbody>
            </table>
            <input type="hidden" id="reorder_hidden_order" value="{json.dumps(list(available_variables))}">
            <input type="hidden" id="reorder_hidden_disabled" value="[]">
        </div>
        """

        # Create the HTML widget
        table_widget = widgets.HTML(html_content)

        # Add title and instructions
        title = widgets.HTML(
            "<div style='font-size: 15px; font-weight: 600; margin-bottom: 12px; color: #333;'>"
            "📊 Reorder Variables for Boxplots</div>"
        )

        instructions = widgets.HTML(
            "<div style='font-size: 12px; color: #666; margin-bottom: 15px; background: #f0f7ff; padding: 10px; border-left: 4px solid #667eea; border-radius: 4px;'>"
            "<b>💡 Instructions:</b> Drag the ≡ handle to reorder variations. Use the ✓ checkbox to include/exclude individual variations from all plots. Changes apply when you click <b>Plot Selection</b>.</div>"
        )

        # Create container with all components (no Apply button - use Plot Selection instead)
        all_widgets = [
            title,
            instructions,
            table_widget,
            self.variable_order_state,
            self.variable_disabled_state,
        ]

        self.variable_reorder_section.children = all_widgets
        self.variable_reorder_section.layout = widgets.Layout(
            width="100%",
            border="1px solid #ddd",
            padding="15px",
            margin="10px 0",
            border_radius="8px",
            background_color="#fafafa",
        )

        # Add JavaScript for drag and drop
        self._setup_drag_and_drop()

        debug_logger.add("REORDER", "Widget updated and displayed")

    def _setup_comm_handler(self):
        """Legacy no-op: Comm-based sync removed in favor of widget-state sync."""
        return

    def _setup_drag_and_drop(self):
        """Setup JavaScript for drag and drop functionality"""
        js_code = """
        (function() {
            setTimeout(function() {
                const tbody = document.querySelector('#reorder_tbody');
                if (!tbody) {
                    console.log('[DND] Tbody not found');
                    return;
                }
                
                const rows = tbody.querySelectorAll('tr.reorder-row');
                console.log('[DND] Found ' + rows.length + ' draggable rows');
                
                let draggedElement = null;
                
                rows.forEach((row, index) => {
                    row.addEventListener('dragstart', function(e) {
                        draggedElement = this;
                        this.style.opacity = '0.5';
                        e.dataTransfer.effectAllowed = 'move';
                        e.dataTransfer.setData('text/html', this.innerHTML);
                        console.log('[DND] Started dragging row ' + (index + 1));
                    });
                    
                    row.addEventListener('dragend', function(e) {
                        this.style.opacity = '1';
                        rows.forEach(r => r.classList.remove('drag-over'));
                    });
                    
                    row.addEventListener('dragover', function(e) {
                        e.preventDefault();
                        e.dataTransfer.dropEffect = 'move';
                        this.classList.add('drag-over');
                    });
                    
                    row.addEventListener('dragleave', function(e) {
                        if (e.target === this) {
                            this.classList.remove('drag-over');
                        }
                    });
                    
                    row.addEventListener('drop', function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                        this.classList.remove('drag-over');
                        
                        if (draggedElement && draggedElement !== this) {
                            const allRows = Array.from(tbody.querySelectorAll('tr.reorder-row'));
                            const draggedIndex = allRows.indexOf(draggedElement);
                            const targetIndex = allRows.indexOf(this);
                            
                            if (draggedIndex < targetIndex) {
                                this.parentNode.insertBefore(draggedElement, this.nextSibling);
                            } else {
                                this.parentNode.insertBefore(draggedElement, this);
                            }
                            
                            console.log('[DND] Dropped at new position');
                            updateNumbersAfterDrag();
                            sendReorderToCommHandler();
                            if (typeof window.syncDisabledStateToWidget === 'function') {
                                window.syncDisabledStateToWidget();
                            }
                        }
                    });
                });
                
                // Add checkbox enable/disable listeners
                rows.forEach((row) => {
                    const cb = row.querySelector('.reorder-enable-checkbox');
                    if (cb) {
                        cb.addEventListener('change', function() {
                            row.style.opacity = this.checked ? '1.0' : '0.35';
                            if (typeof window.syncDisabledStateToWidget === 'function') {
                                window.syncDisabledStateToWidget();
                            }
                        });
                    }
                });
                
                window.updateNumbersAfterDrag = function() {
                    const allRows = tbody.querySelectorAll('tr.reorder-row');
                    allRows.forEach((row, idx) => {
                        const numSpan = row.querySelector('.reorder-number');
                        if (numSpan) {
                            numSpan.textContent = (idx + 1);
                        }
                    });
                };

                window.syncReorderStateToWidget = function(newOrder) {
                    try {
                        const serialized = JSON.stringify(newOrder || []);
                        const stateInput = document.querySelector('.reorder-order-state input, .reorder-order-state textarea');
                        if (stateInput) {
                            stateInput.value = serialized;
                            stateInput.dispatchEvent(new Event('input', { bubbles: true }));
                            stateInput.dispatchEvent(new Event('change', { bubbles: true }));
                            console.log('[DND-STATE] Synced order to hidden widget');
                        } else {
                            console.log('[DND-STATE] Hidden reorder state widget not found');
                        }

                        const hiddenInput = document.querySelector('#reorder_hidden_order');
                        if (hiddenInput) {
                            hiddenInput.value = serialized;
                        }
                    } catch (err) {
                        console.log('[DND-STATE] Error syncing state:', err);
                    }
                };
                
                window.sendReorderToCommHandler = function(action) {
                    const allRows = tbody.querySelectorAll('tr.reorder-row');
                    const newOrder = [];
                    allRows.forEach((row) => {
                        const value = row.getAttribute('data-value');
                        if (value) {
                            newOrder.push(value);
                        }
                    });
                    console.log('[DND-ORDER] New order to sync:', newOrder);
                    const commAction = action || 'reorder';

                    // Sync via hidden ipywidget state
                    if (typeof window.syncReorderStateToWidget === 'function') {
                        window.syncReorderStateToWidget(newOrder);
                    }
                    console.log('[DND-SYNC] Synced order to widget-state only (action=' + commAction + ')');
                };

                window.syncDisabledStateToWidget = function() {
                    const allRows = tbody.querySelectorAll('tr.reorder-row');
                    const disabledValues = [];
                    allRows.forEach((row) => {
                        const cb = row.querySelector('.reorder-enable-checkbox');
                        if (cb && !cb.checked) {
                            const value = row.getAttribute('data-value');
                            if (value) disabledValues.push(value);
                        }
                    });
                    try {
                        const serialized = JSON.stringify(disabledValues);
                        const disabledInput = document.querySelector('.reorder-disabled-state input, .reorder-disabled-state textarea');
                        if (disabledInput) {
                            disabledInput.value = serialized;
                            disabledInput.dispatchEvent(new Event('input', { bubbles: true }));
                            disabledInput.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        const hiddenDisabled = document.querySelector('#reorder_hidden_disabled');
                        if (hiddenDisabled) { hiddenDisabled.value = serialized; }
                        console.log('[DND-DISABLED] Synced disabled state:', disabledValues);
                    } catch(err) {
                        console.log('[DND-DISABLED] Error syncing disabled state:', err);
                    }
                };

                // Initialize hidden state with current DOM order
                window.sendReorderToCommHandler('sync_order');
                window.syncDisabledStateToWidget();
                
            }, 100);
        })();
        """

        # Display JavaScript widget (hidden but executes)
        display(Javascript(js_code))

    def _extract_variable_order_from_current_dom(self):
        """Extract variable order by reading the data-index attribute values in DOM order"""
        try:
            if not hasattr(self, "variable_order_list") or not self.variable_order_list:
                debug_logger.add("REORDER", "[DOM_EXTRACT] No variable_order_list to work with")
                return None

            debug_logger.add(
                "REORDER", "[DOM_EXTRACT] Attempting to extract from DOM using data-index"
            )

            # We'll read the rows by their data-index values and reconstruct the order
            # The key insight: the data-index attribute tells us which variable is at each position

            # Since we can't directly access the DOM from Python, we'll use the current HTML state
            # and try to infer the new order by looking at the row order

            # Fallback: use variable_order_list with re-read attempt
            # This is a workaround - we use the HTML widget's current value
            if hasattr(self, "variable_reorder_section") and self.variable_reorder_section.children:
                for widget in self.variable_reorder_section.children:
                    if hasattr(widget, "value") and "reorder_tbody" in str(widget.value):
                        html_str = str(widget.value)

                        # Extract rows with their full HTML to maintain order
                        import re

                        # Find all rows in the order they appear in the HTML
                        pattern = r'<tr[^>]*data-value="([^"]*)"[^>]*data-index="(\d+)"'
                        matches = re.findall(pattern, html_str)

                        if not matches:
                            # Try alternate pattern without data-index
                            pattern = r'<tr[^>]*data-value="([^"]*)"'
                            matches = re.findall(pattern, html_str)

                        if matches:
                            # Extract just the values in their current order
                            order = [
                                match[0] if isinstance(match, tuple) else match for match in matches
                            ]
                            debug_logger.add("REORDER", f"[DOM_EXTRACT] Found order: {order}")
                            return order

            debug_logger.add("REORDER", "[DOM_EXTRACT] Could not extract from DOM")
            return None
        except Exception as e:
            debug_logger.add("REORDER", f"[DOM_EXTRACT] Error: {e}")
            import traceback

            debug_logger.add("REORDER", f"[DOM_EXTRACT] Traceback: {traceback.format_exc()}")
            return None

    def _make_move_up_handler(self, index):
        """Create handler for move up with correct index captured"""

        def handler(btn):
            self._move_variable_up(index)

        return handler

    def _make_move_down_handler(self, index):
        """Create handler for move down with correct index captured"""

        def handler(btn):
            self._move_variable_down(index)

        return handler

    def _move_variable_up(self, index):
        """Move variable up in the list"""
        if index > 0:
            debug_logger.add(
                "REORDER", f"Moving '{self.variable_order_list[index]}' up from position {index}"
            )
            self.variable_order_list[index], self.variable_order_list[index - 1] = (
                self.variable_order_list[index - 1],
                self.variable_order_list[index],
            )
            debug_logger.add("REORDER", f"New order: {self.variable_order_list}")
            self.update_variable_reorder(self.variable_order_list)
            if self.reorder_update_callback:
                self.reorder_update_callback()

    def _move_variable_down(self, index):
        """Move variable down in the list"""
        if index < len(self.variable_order_list) - 1:
            debug_logger.add(
                "REORDER", f"Moving '{self.variable_order_list[index]}' down from position {index}"
            )
            self.variable_order_list[index], self.variable_order_list[index + 1] = (
                self.variable_order_list[index + 1],
                self.variable_order_list[index],
            )
            debug_logger.add("REORDER", f"New order: {self.variable_order_list}")
            self.update_variable_reorder(self.variable_order_list)
            if self.reorder_update_callback:
                self.reorder_update_callback()

    def _extract_variable_order_from_html(self):
        """Extract the current variable order from the HTML table by reading data-value from rows"""
        try:
            if (
                not hasattr(self, "variable_reorder_section")
                or not self.variable_reorder_section.children
            ):
                debug_logger.add("REORDER", "[EXTRACT] No reorder_section found")
                return None

            # Look for table widget in children
            for widget in self.variable_reorder_section.children:
                if (
                    hasattr(widget, "value")
                    and "<table" in str(widget.value)
                    and "reorder_tbody" in str(widget.value)
                ):
                    # Found the HTML table
                    html_content = str(widget.value)
                    debug_logger.add("REORDER", "[EXTRACT] Found HTML table widget")

                    # Parse the data-value attributes from rows in order
                    import re

                    # Find all data-value attributes in tr elements (in document order)
                    pattern = r'<tr[^>]*data-value="([^"]*)"'
                    matches = re.findall(pattern, html_content)

                    if matches and len(matches) > 0:
                        debug_logger.add(
                            "REORDER",
                            f"[EXTRACT] Found {len(matches)} rows with data-value attributes",
                        )
                        debug_logger.add("REORDER", f"[EXTRACT] Extracted order: {matches}")
                        return matches
                    else:
                        debug_logger.add(
                            "REORDER", "[EXTRACT] No rows found with data-value attributes"
                        )

            debug_logger.add("REORDER", "[EXTRACT] Could not find HTML table")
            return None
        except Exception as e:
            debug_logger.add("REORDER", f"[EXTRACT] Error: {e}")
            import traceback

            debug_logger.add("REORDER", f"[EXTRACT] Traceback: {traceback.format_exc()}")
            return None

    def sync_variable_order_from_dom(self):
        """Read the current variable order from the DOM and update variable_order_list"""
        try:
            debug_logger.add("REORDER", "[DOM_SYNC] Reading current DOM order for variables...")

            # Send JavaScript code to read and return the current DOM order
            js_code = """
            (function() {
                if (typeof window.sendReorderToCommHandler === 'function') {
                    window.sendReorderToCommHandler('sync_order');
                    return;
                }

                const tbody = document.querySelector('#reorder_tbody');
                if (!tbody) {
                    console.log('[DOM_SYNC-JS] Could not find tbody element');
                    return;
                }

                const rows = Array.from(tbody.querySelectorAll('tr.reorder-row'));
                const currentOrder = rows.map(row => row.getAttribute('data-value')).filter(v => v);
                console.log('[DOM_SYNC-JS] Current DOM order:', currentOrder);

                if (typeof window.syncReorderStateToWidget === 'function') {
                    window.syncReorderStateToWidget(currentOrder);
                }
            })();
            """

            debug_logger.add("REORDER", "[DOM_SYNC] Executing JavaScript to read DOM...")
            display(Javascript(js_code))
            debug_logger.add("REORDER", "[DOM_SYNC] JavaScript executed")

        except Exception as e:
            import traceback

            debug_logger.add("REORDER", f"[DOM_SYNC] Error: {e}")
            debug_logger.add("REORDER", f"[DOM_SYNC] Traceback: {traceback.format_exc()}")

    def _on_variable_order_state_change(self, change):
        """Update Python-side order when hidden state widget value changes from JS."""
        try:
            if change.get("name") != "value":
                return
            raw = change.get("new", "")
            if not raw:
                return
            parsed = json.loads(raw)
            if isinstance(parsed, list) and len(parsed) > 0:
                self.variable_order_list = [str(v) for v in parsed]
                debug_logger.add(
                    "REORDER",
                    f"[STATE] variable_order_list updated from hidden widget: {self.variable_order_list}",
                )
        except Exception as e:
            debug_logger.add("REORDER", f"[STATE] Failed to parse hidden reorder state: {e}")

    def get_variable_order(self):
        """Get current variable order from variable_order_list"""
        try:
            debug_logger.add("PLOT", "[GET_ORDER] get_variable_order() called")
            debug_logger.add(
                "PLOT",
                f"[GET_ORDER] hasattr(self, 'variable_order_list'): {hasattr(self, 'variable_order_list')}",
            )

            # Prefer hidden widget state if available (robust fallback when custom Comm is unavailable)
            if self.variable_order_state is not None and self.variable_order_state.value:
                try:
                    parsed_state = json.loads(self.variable_order_state.value)
                    if isinstance(parsed_state, list) and len(parsed_state) > 0:
                        self.variable_order_list = [str(v) for v in parsed_state]
                        debug_logger.add(
                            "PLOT",
                            f"[GET_ORDER] Refreshed from hidden widget state: {self.variable_order_list}",
                        )
                except Exception as state_err:
                    debug_logger.add(
                        "PLOT", f"[GET_ORDER] Could not parse hidden widget state: {state_err}"
                    )

            if hasattr(self, "variable_order_list"):
                result = self.variable_order_list
                debug_logger.add(
                    "PLOT", f"[GET_ORDER] variable_order_list exists, length: {len(result)}"
                )
                debug_logger.add("PLOT", f"[GET_ORDER] variable_order_list contents: {result}")
            else:
                result = []
                debug_logger.add(
                    "PLOT", "[GET_ORDER] variable_order_list does not exist, returning empty list"
                )

            return result
        except Exception as e:
            debug_logger.add("PLOT", f"[GET_ORDER] Error: {e}")
            import traceback

            debug_logger.add("PLOT", f"[GET_ORDER] Traceback: {traceback.format_exc()}")
            return self.variable_order_list if hasattr(self, "variable_order_list") else []

    def _on_variable_disabled_state_change(self, change):
        """Update Python-side disabled list when hidden state widget changes from JS."""
        try:
            if change.get("name") != "value":
                return
            raw = change.get("new", "")
            if not raw:
                return
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                self.variable_disabled_list = [str(v) for v in parsed]
                debug_logger.add(
                    "REORDER",
                    f"[DISABLED] variable_disabled_list updated: {self.variable_disabled_list}",
                )
        except Exception as e:
            debug_logger.add("REORDER", f"[DISABLED] Failed to parse disabled state: {e}")

    def get_disabled_variables(self):
        """Get list of currently disabled (excluded) variable identifiers."""
        try:
            if self.variable_disabled_state is not None and self.variable_disabled_state.value:
                try:
                    parsed = json.loads(self.variable_disabled_state.value)
                    if isinstance(parsed, list):
                        self.variable_disabled_list = [str(v) for v in parsed]
                except Exception:
                    pass
            return (
                list(self.variable_disabled_list) if hasattr(self, "variable_disabled_list") else []
            )
        except Exception:
            return []

    def get_plot_selections(self):
        """Get current plot selections"""
        selections = []
        for group in self.plot_type_groups:
            plot_type = group.children[0].value
            option1 = group.children[1].value
            option2 = group.children[2].value
            selections.append((plot_type, option1, option2))
        return selections

    def set_plot_callback(self, callback):
        """Set callback for plot button"""
        self.plot_button.on_click(callback)

    def set_reorder_update_callback(self, callback):
        """Set callback for when reorder changes (called by move buttons)"""
        self.reorder_update_callback = callback

    def get_separate_scan_dir(self):
        """Get whether to separate scan directions"""
        return self.separate_scan_dir_checkbox.value

    def get_widget(self):
        """Get the main plot widget"""
        return widgets.VBox(
            [
                widgets.HTML("<h3>Select Plots</h3>"),
                widgets.HTML(
                    "<p>Using the dropdowns below, select the plots you want to create.</p>"
                ),
                widgets.HBox([self.controls, self.groups_container]),
                self.variable_reorder_section,  # Full width below the controls
            ]
        )


class JVCurveAnalysisUI:
    """UI for detailed JV curve analysis with independent filtering."""

    def __init__(self):
        self.filter_rows = []
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
        self._create_widgets()
        self._setup_observers()

    def _create_widgets(self):
        self.mode_dropdown = widgets.Dropdown(
            options=[
                ("Best device per condition", "best_per_condition"),
                ("All filtered JV curves", "all_filtered"),
            ],
            value="best_per_condition",
            description="Plot mode:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="320px"),
        )

        self.scale_dropdown = widgets.Dropdown(
            options=[("Linear", "linear"), ("Logarithmic ln(|J|)", "log_e")],
            value="linear",
            description="Current axis:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="320px"),
        )

        self.exclude_conditions_select = widgets.SelectMultiple(
            options=[],
            value=(),
            description="Exclude conditions:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="360px", height="140px"),
        )

        self.pixel_select = widgets.SelectMultiple(
            options=[],
            value=(),
            description="Pixels:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px", height="140px"),
        )

        self.cycle_select = widgets.SelectMultiple(
            options=[],
            value=(),
            description="Cycles:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="240px", height="140px"),
        )

        self.add_filter_button = WidgetFactory.create_button("Add Filter", "primary")
        self.remove_filter_button = WidgetFactory.create_button("Remove Filter", "danger")
        self.plot_button = WidgetFactory.create_button("Plot JV Curves", "success")

        self.numeric_filter_rows = widgets.VBox()
        self._add_filter_row(None)

        self.status_output = WidgetFactory.create_output(scrollable=False, border=True)
        self.plotted_content = WidgetFactory.create_output(scrollable=False, border=True)

        mode_box = widgets.VBox(
            [widgets.HTML("<b>Plot Settings</b>"), self.mode_dropdown, self.scale_dropdown]
        )

        category_box = widgets.VBox(
            [
                widgets.HTML("<b>Condition Filter</b>"),
                widgets.HTML(
                    "<p style='margin:0 0 8px 0; color:#666;'>Select conditions to exclude from this analysis tab only.</p>"
                ),
                self.exclude_conditions_select,
            ]
        )

        pixel_cycle_box = widgets.VBox(
            [
                widgets.HTML("<b>Pixel / Cycle Filters</b>"),
                widgets.HTML(
                    "<p style='margin:0 0 8px 0; color:#666;'>If nothing is selected, all pixels/cycles are included.</p>"
                ),
                widgets.HBox([self.pixel_select, self.cycle_select]),
            ]
        )

        numeric_box = widgets.VBox(
            [
                widgets.HTML("<b>Numeric Filters</b>"),
                widgets.HTML(
                    "<p style='margin:0 0 8px 0; color:#666;'>Works like Select Filters, but independently for this tab.</p>"
                ),
                widgets.HBox([self.add_filter_button, self.remove_filter_button]),
                self.numeric_filter_rows,
            ]
        )

        controls_section = widgets.VBox(
            [
                widgets.HBox([mode_box, category_box]),
                pixel_cycle_box,
                numeric_box,
                widgets.HBox([self.plot_button]),
            ],
            layout=widgets.Layout(border="1px solid #ddd", padding="12px", margin="8px 0"),
        )

        self.layout = widgets.VBox(
            [
                widgets.HTML("<h3>JV Curve Analysis</h3>"),
                widgets.HTML(
                    "<p>Analyze JV curves with independent filters (not tied to Select Filters).</p>"
                ),
                controls_section,
                self.status_output,
                widgets.HTML("<h4>Generated JV Curve Analysis Plot</h4>"),
                self.plotted_content,
            ]
        )

    def _setup_observers(self):
        self.add_filter_button.on_click(self._add_filter_row)
        self.remove_filter_button.on_click(self._remove_filter_row)

    def _create_numeric_filter_row(self):
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
        return widgets.HBox([column_dropdown, operator_dropdown, value_input])

    def _add_filter_row(self, _):
        self.filter_rows.append(self._create_numeric_filter_row())
        self.numeric_filter_rows.children = tuple(self.filter_rows)

    def _remove_filter_row(self, _):
        if len(self.filter_rows) > 1:
            self.filter_rows.pop()
            self.numeric_filter_rows.children = tuple(self.filter_rows)

    def set_data(self, data):
        """Update condition/pixel/cycle options from loaded JV data."""
        if not data or "jvc" not in data or data["jvc"].empty:
            self.exclude_conditions_select.options = []
            self.exclude_conditions_select.value = ()
            self.pixel_select.options = []
            self.pixel_select.value = ()
            self.cycle_select.options = []
            self.cycle_select.value = ()
            return

        df = data["jvc"]

        if "condition" in df.columns:
            conditions = sorted([str(v) for v in df["condition"].dropna().unique().tolist()])
        else:
            conditions = sorted([str(v) for v in df["sample"].dropna().unique().tolist()])
        self.exclude_conditions_select.options = conditions
        self.exclude_conditions_select.value = tuple(
            v for v in self.exclude_conditions_select.value if v in conditions
        )

        if "px_number" in df.columns:
            pixels = sorted([str(v) for v in df["px_number"].dropna().unique().tolist()])
        else:
            pixels = []
        self.pixel_select.options = pixels
        self.pixel_select.value = tuple(v for v in self.pixel_select.value if v in pixels)

        if "cycle_number" in df.columns and df["cycle_number"].notna().any():
            cycles = sorted([int(v) for v in df["cycle_number"].dropna().unique().tolist()])
            cycle_options = [(f"Cycle {c}", c) for c in cycles]
        else:
            cycle_options = []
        self.cycle_select.options = cycle_options
        valid_cycle_values = {v for _, v in cycle_options}
        self.cycle_select.value = tuple(
            v for v in self.cycle_select.value if v in valid_cycle_values
        )

    def get_plot_mode(self):
        return self.mode_dropdown.value

    def use_log_current(self):
        return self.scale_dropdown.value == "log_e"

    def get_excluded_conditions(self):
        return list(self.exclude_conditions_select.value)

    def get_selected_pixels(self):
        return [str(v) for v in self.pixel_select.value]

    def get_selected_cycles(self):
        return [int(v) for v in self.cycle_select.value]

    def get_numeric_filters(self):
        filters = []
        for group in self.filter_rows:
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

    def set_plot_callback(self, callback):
        self.plot_button.on_click(callback)

    def get_widget(self):
        return self.layout


class SaveUI:
    """Handles save functionality UI"""

    def __init__(self):
        self._create_widgets()

    def _create_widgets(self):
        """Create save widgets"""
        self.save_plots_button = WidgetFactory.create_button("Save All Plots", "primary")
        self.save_data_button = WidgetFactory.create_button("Save Data", "info")
        self.save_all_button = WidgetFactory.create_button("Save Data & Plots", "success")
        self.download_output = WidgetFactory.create_output()

    def trigger_download(self, content, filename, content_type="text/json"):
        """Trigger file download"""
        content_b64 = base64.b64encode(
            content if isinstance(content, bytes) else content.encode()
        ).decode()
        data_url = f"data:{content_type};charset=utf-8;base64,{content_b64}"
        js_code = f"""
            var a = document.createElement('a');
            a.setAttribute('download', '{filename}');
            a.setAttribute('href', '{data_url}');
            a.click()
        """
        with self.download_output:
            clear_output()
            display(HTML(f"<script>{js_code}</script>"))

    def create_plots_zip(self, figures, names):
        """Create zip file with plots"""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for fig, name in zip(figures, names):
                try:
                    html_str = fig.to_html(include_plotlyjs="cdn")
                    zip_file.writestr(name, html_str)

                    try:
                        import plotly.io as pio

                        img_bytes = pio.to_image(fig, format="png")
                        zip_file.writestr(name.replace(".html", ".png"), img_bytes)
                    except:
                        pass
                except Exception as e:
                    print(f"Error saving {name}: {e}")

        zip_buffer.seek(0)
        return zip_buffer.getvalue()

    def set_save_callbacks(self, plots_callback, data_callback, all_callback):
        """Set callbacks for save buttons"""
        self.save_plots_button.on_click(plots_callback)
        self.save_data_button.on_click(data_callback)
        self.save_all_button.on_click(all_callback)

    def get_widget(self):
        """Get the main save widget"""
        return widgets.VBox(
            [
                widgets.HTML("<h3>Save Plots and Data</h3>"),
                widgets.HBox([self.save_plots_button, self.save_data_button, self.save_all_button]),
                self.download_output,
            ]
        )


class ColorSchemeSelector:
    """Color scheme selector with preview"""

    def __init__(self):
        self.color_schemes = {
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
            "Default (old)": [
                "rgba(93, 164, 214, 0.7)",
                "rgba(255, 144, 14, 0.7)",
                "rgba(44, 160, 101, 0.7)",
                "rgba(255, 65, 54, 0.7)",
                "rgba(207, 114, 255, 0.7)",
                "rgba(127, 96, 0, 0.7)",
                "rgba(255, 140, 184, 0.7)",
                "rgba(79, 90, 117, 0.7)",
            ],
        }

        self.selected_scheme = "Viridis"
        self.num_colors = 8  # Default number of colors
        self._create_widgets()

    def _create_widgets(self):
        """Create color scheme selector widgets"""
        self.color_dropdown = widgets.Dropdown(
            options=list(self.color_schemes.keys()),
            value=self.selected_scheme,
            description="Color Scheme:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px"),
        )

        self.sampling_dropdown = widgets.Dropdown(
            options=["sequential", "even"],
            value="sequential",
            description="Sampling:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px"),
        )

        # Slider to select number of colors
        self.num_colors_slider = widgets.IntSlider(
            value=8,
            min=2,
            max=20,
            step=1,
            description="# Colors:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px"),
        )

        self.preview_output = widgets.Output(
            layout=widgets.Layout(width="400px", height="60px", border="1px solid #ccc")
        )

        self.color_dropdown.observe(self._on_color_change, names="value")
        self.sampling_dropdown.observe(self._on_sampling_change, names="value")
        self.num_colors_slider.observe(self._on_num_colors_change, names="value")

        self._update_preview()

        self.widget = widgets.VBox(
            [
                widgets.HBox([self.color_dropdown, self.sampling_dropdown]),
                self.num_colors_slider,
                self.preview_output,
            ]
        )

    def _on_sampling_change(self, change):
        self._update_preview()

    def _on_color_change(self, change):
        self.selected_scheme = change["new"]
        self._update_preview()

    def _on_num_colors_change(self, change):
        """Handle number of colors change"""
        self.num_colors = change["new"]
        self._update_preview()

    def _update_preview(self):
        with self.preview_output:
            clear_output(wait=True)

            colors = self.get_colors(
                num_colors=self.num_colors, sampling=self.sampling_dropdown.value
            )

            if self.sampling_dropdown.value == "even":
                sampling_text = "Even Sampling"
            else:
                sampling_text = "Continuous Gradient"

            html_preview = '<div style="display: flex; flex-direction: column; padding: 5px;">'
            html_preview += f'<span style="margin-bottom: 5px; font-weight: bold;">{self.selected_scheme} ({sampling_text}): {len(colors)} colors</span>'
            html_preview += '<div style="display: flex; flex-wrap: wrap;">'

            for color in colors:
                html_preview += f'<span style="background-color: {color}; width: 30px; height: 30px; display: inline-block; margin: 2px; border: 1px solid #333; border-radius: 3px;"></span>'

            html_preview += "</div></div>"

            display(HTML(html_preview))

    def _interpolate_color(self, hex_color1, hex_color2, factor):
        """
        Interpolate between two colors (supports both hex and rgba formats)
        factor: 0.0 = color1, 1.0 = color2
        """

        # Convert hex to RGB
        def hex_to_rgb(color):
            """Convert color from hex or rgba format to RGB tuple"""
            if isinstance(color, str):
                # Handle rgba(r, g, b, a) format
                if color.startswith("rgba"):
                    # Extract RGBA values: rgba(93, 164, 214, 0.7)
                    import re

                    match = re.match(
                        r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", color
                    )
                    if match:
                        r, g, b, a = match.groups()
                        return (int(r) / 255.0, int(g) / 255.0, int(b) / 255.0)

                # Handle hex format: #RRGGBB
                color = color.lstrip("#")
                if len(color) >= 6:
                    return tuple(int(color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))

            # Fallback: return neutral color if parsing fails
            return (0.5, 0.5, 0.5)

        # Convert RGB to hex
        def rgb_to_hex(r, g, b):
            return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))

        rgb1 = hex_to_rgb(hex_color1)
        rgb2 = hex_to_rgb(hex_color2)

        # Linear interpolation
        r = rgb1[0] + (rgb2[0] - rgb1[0]) * factor
        g = rgb1[1] + (rgb2[1] - rgb1[1]) * factor
        b = rgb1[2] + (rgb2[2] - rgb1[2]) * factor

        return rgb_to_hex(r, g, b)

    def _ensure_hex_format(self, color):
        """
        Convert color to hex format if it's in rgba format

        Args:
            color: Color string (hex or rgba format)

        Returns:
            Color in hex format (#RRGGBB)
        """
        if isinstance(color, str):
            # Already hex format
            if color.startswith("#"):
                return color

            # Convert rgba format to hex
            if color.startswith("rgba"):
                import re

                match = re.match(
                    r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", color
                )
                if match:
                    r, g, b, a = match.groups()
                    return "#{:02x}{:02x}{:02x}".format(int(r), int(g), int(b))

        # Fallback: return gray if conversion fails
        return "#808080"

    def _generate_continuous_colors(self, num_colors):
        """
        Generate smooth color gradient from continuous palette

        Args:
            num_colors: Number of colors to generate

        Returns:
            List of hex colors evenly distributed across the palette
        """
        # Get base palette for the selected scheme
        base_palette = self.color_schemes[self.selected_scheme]

        if num_colors <= len(base_palette):
            # If requested colors <= available colors, just select evenly
            step = (len(base_palette) - 1) / (num_colors - 1) if num_colors > 1 else 0
            selected_colors = [base_palette[int(i * step)] for i in range(num_colors)]
            return [self._ensure_hex_format(color) for color in selected_colors]
        else:
            # If requested colors > available colors, interpolate between palette colors
            colors = []

            for i in range(num_colors):
                # Position in the palette (0.0 to 1.0)
                position = i / (num_colors - 1) if num_colors > 1 else 0

                # Map position to base palette
                palette_index = position * (len(base_palette) - 1)
                lower_index = int(palette_index)
                upper_index = min(lower_index + 1, len(base_palette) - 1)

                # Interpolation factor between the two neighboring palette colors
                factor = palette_index - lower_index

                # Get the two colors from palette
                color1 = base_palette[lower_index]
                color2 = base_palette[upper_index]

                # Interpolate between them
                if factor == 0 or lower_index == upper_index:
                    interpolated = self._ensure_hex_format(color1)
                else:
                    interpolated = self._interpolate_color(color1, color2, factor)

                colors.append(interpolated)

            return colors

    def get_colors(self, num_colors=None, sampling="sequential"):
        """Get colors from selected scheme

        Args:
            num_colors: Number of colors to generate (if None, uses slider value)
            sampling: 'sequential' (continuous gradient) or 'even' (pick evenly from palette)

        Returns:
            List of hex colors
        """
        if num_colors is None:
            num_colors = self.num_colors

        colors = self.color_schemes[self.selected_scheme]

        if sampling == "even" and len(colors) > num_colors:
            if num_colors == 1:
                return [colors[len(colors) // 2]]

            indices = []
            for i in range(num_colors):
                index = int(round(i * (len(colors) - 1) / (num_colors - 1)))
                indices.append(index)

            return [colors[i] for i in indices]
        else:
            # Use continuous color generation for all other cases
            return self._generate_continuous_colors(num_colors)

    def set_num_colors(self, num_colors):
        """
        Set the number of colors to generate

        Args:
            num_colors: Number of colors (will be clamped to 2-20)
        """
        num_colors = max(2, min(20, num_colors))  # Clamp to valid range
        self.num_colors_slider.value = num_colors
        # Preview will update automatically via the observer

    def get_widget(self):
        """Get the color scheme selector widget"""
        return widgets.VBox(
            [
                widgets.HTML("<h4>Color Scheme Selection</h4>"),
                widgets.HTML(
                    "<p style='font-size: 12px; color: #666;'>Select a palette and adjust the number of colors. Colors will be generated dynamically.</p>"
                ),
                self.widget,
            ]
        )


class InfoUI:
    """What's New and Manual UI component"""

    def __init__(self):
        self._create_widgets()

    def _create_widgets(self):
        """Create info widgets"""
        self.whats_new_button = widgets.Button(
            description="🎉 What's New",
            button_style="info",
            layout=widgets.Layout(width="140px", margin="0 5px 0 0"),
            tooltip="See the latest features and improvements",
        )

        self.manual_button = widgets.Button(
            description="📖 Manual",
            button_style="success",
            layout=widgets.Layout(width="120px", margin="0 5px 0 0"),
            tooltip="User manual and guide",
        )

        self.content_output = widgets.Output(
            layout=widgets.Layout(
                display="none",
                border="1px solid #ddd",
                border_radius="6px",
                padding="0px",
                margin="10px 0",
                max_height="500px",
                overflow_y="auto",
                background_color="white",
                width="100%",
            )
        )

        self.current_content = None

        self.whats_new_button.on_click(self._show_whats_new)
        self.manual_button.on_click(self._show_manual)

        self.widget = widgets.VBox(
            [widgets.HBox([self.whats_new_button, self.manual_button]), self.content_output]
        )

    def _show_whats_new(self, b):
        """Show what's new content"""
        if self.current_content == "whats_new" and self.content_output.layout.display == "block":
            self.content_output.layout.display = "none"
            self.whats_new_button.description = "🎉 What's New"
            self.whats_new_button.button_style = "info"
            self.current_content = None
        else:
            self.content_output.layout.display = "block"
            self.whats_new_button.description = "🔽 Hide What's New"
            self.whats_new_button.button_style = "warning"
            self.manual_button.description = "📖 Manual"
            self.manual_button.button_style = "success"
            self.current_content = "whats_new"

            with self.content_output:
                clear_output(wait=True)
                display(HTML("<p>What's new content would go here.</p>"))

    def _show_manual(self, b):
        """Show manual content"""
        if self.current_content == "manual" and self.content_output.layout.display == "block":
            self.content_output.layout.display = "none"
            self.manual_button.description = "📖 Manual"
            self.manual_button.button_style = "success"
            self.current_content = None
        else:
            self.content_output.layout.display = "block"
            self.manual_button.description = "🔽 Hide Manual"
            self.manual_button.button_style = "warning"
            self.whats_new_button.description = "🎉 What's New"
            self.whats_new_button.button_style = "info"
            self.current_content = "manual"

            with self.content_output:
                clear_output(wait=True)
                display(HTML("<p>Manual content would go here.</p>"))

    def get_widget(self):
        """Get the info widget"""
        return self.widget
