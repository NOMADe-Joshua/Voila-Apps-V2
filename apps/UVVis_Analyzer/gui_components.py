"""
UVVis GUI Components Module
Contains UI components for the UVVis Analysis Dashboard.
"""

__author__ = "Joshua Damm"
__institution__ = "KIT"
__created__ = "December 2025"

import ipywidgets as widgets

# Reuse the authentication and save UI from the app's generic widgets
from common_widgets import AuthenticationUI, SaveUI
from IPython.display import HTML, clear_output, display


class UVVisAuthenticationUI(AuthenticationUI):
    """Reuse JV authentication UI"""

    pass


class UVVisBatchSelector:
    """Batch selection UI for UVVis - Simplified structure like JV-Analysis"""

    def __init__(self, callback):
        self.callback = callback
        self.filter_callback = None
        self.all_batches = []  # Store all batches for filtering
        self._create_widgets()

    def _create_widgets(self):
        # Batch selector (like JV-Analysis)
        self.batch_selector = widgets.SelectMultiple(
            options=[], description="Batches", layout=widgets.Layout(width="400px", height="300px")
        )

        # Search field (like JV-Analysis)
        self.search_field = widgets.Text(
            description="Search Batch", layout=widgets.Layout(width="400px")
        )

        # Buttons
        self.load_button = widgets.Button(description="Load Data", button_style="primary")

        self.filter_button = widgets.Button(
            description="🔍 Filter UVVis Batches",
            button_style="info",
            layout=widgets.Layout(margin="5px 0 0 0"),
        )

        # Wire up callbacks - as methods, not local functions
        self.search_field.observe(self._on_search_enter, names="value")
        self.load_button.on_click(lambda b: self.callback(self.batch_selector))
        self.filter_button.on_click(
            lambda b: self.filter_callback() if self.filter_callback else None
        )

        # Assemble widget (like JV-Analysis: search, selector, buttons)
        self.widget = widgets.VBox(
            [self.search_field, self.batch_selector, self.load_button, self.filter_button]
        )

    def _on_search_enter(self, change):
        """Handle search field changes - filter batch options"""
        search_term = self.search_field.value.strip().lower()
        filtered_options = []

        for d in self.all_batches:
            # Handle both tuple and string formats
            batch_str = d[0] if isinstance(d, tuple) else d
            if search_term in batch_str.lower():
                filtered_options.append(d)

        self.batch_selector.options = filtered_options

    def set_options(self, options):
        """Set available batch options"""
        self.all_batches = list(options)
        self.batch_selector.options = options

    def set_filter_callback(self, callback):
        """Set callback for UVVis batch filtering"""
        self.filter_callback = callback

    def get_widget(self):
        return self.widget


class UVVisPlotUI:
    """Plot selection UI for UVVis"""

    def __init__(self):
        self._create_widgets()

    def _create_widgets(self):
        """Create widgets"""
        # Change plot mode to checkboxes for multi-selection
        self.plot_mode_checks = widgets.VBox(
            [
                widgets.HTML("<b>Plot Types:</b>"),
                widgets.Checkbox(value=True, description="Spectra (custom R/T/A)"),
                widgets.Checkbox(value=False, description="🔬 Bandgap Analysis (Derivative)"),
                widgets.Checkbox(value=False, description="📊 Tauc Plot (Direct Bandgap)"),
            ]
        )

        self.layout_radio = widgets.RadioButtons(
            options=["Overlay", "Grid", "Separate"],
            value="Overlay",
            description="Layout:",
            style={"description_width": "initial"},
            layout=widgets.Layout(margin="0 0 5px 0"),
        )

        self.channel_checks = widgets.VBox(
            [
                widgets.HTML("<b>Channels to plot:</b>"),
                widgets.Checkbox(value=False, description="Reflection"),
                widgets.Checkbox(value=False, description="Transmission"),
                widgets.Checkbox(value=True, description="Absorption"),
            ],
            layout=widgets.Layout(margin="0 0 10px 0"),
        )

        self.x_axis_radio = widgets.RadioButtons(
            options=["Photon Energy (eV)", "Wavelength (nm)"],
            value="Photon Energy (eV)",
            description="X-Axis:",
            style={"description_width": "initial"},
            layout=widgets.Layout(display="none"),
        )
        self.thickness_input = widgets.FloatText(
            value=550,
            description="Thickness (nm):",
            style={"description_width": "initial"},
            layout=widgets.Layout(display="none", width="200px"),
        )

        # NEW: Bandgap fitting controls
        self.bandgap_controls = widgets.VBox(
            [
                widgets.HTML("<b>Bandgap Analysis Options:</b>"),
                widgets.Checkbox(
                    value=True,
                    description="🔍 Auto-fit peaks (Gaussian)",
                    tooltip="Automatically find and fit Gaussian peaks in derivative",
                ),
                widgets.Checkbox(
                    value=True,
                    description="📊 Show bandgaps in legend",
                    tooltip="Display fitted bandgap values in plot legend",
                ),
                widgets.Checkbox(
                    value=True,
                    description="📋 Show bandgap table",
                    tooltip="Display table with all fitted bandgaps below plot",
                ),
                widgets.Text(
                    value="",
                    description="Manual peaks (eV):",
                    placeholder="e.g. 1.55, 2.1, 2.8",
                    style={"description_width": "initial"},
                    tooltip="Comma-separated list of manual peak positions in eV",
                    layout=widgets.Layout(width="350px"),
                ),
            ],
            layout=widgets.Layout(display="none", margin="10px 0"),
        )

        self.plot_button = widgets.Button(
            description="Create Plots", button_style="success", layout=widgets.Layout(width="150px")
        )

        self.plotted_content = widgets.Output()

        # Setup observer for plot mode changes
        for cb in self.plot_mode_checks.children[1:]:
            cb.observe(self._on_plot_mode_change, names="value")

        self.widget = widgets.VBox(
            [
                widgets.HTML("<h3>Plot Settings</h3>"),
                self.plot_mode_checks,
                self.layout_radio,
                self.channel_checks,
                self.x_axis_radio,
                self.bandgap_controls,
                self.thickness_input,
                self.plot_button,
                widgets.HTML("<hr>"),
                widgets.HTML("<h3>Generated Plots</h3>"),
                self.plotted_content,
            ]
        )

    def _on_plot_mode_change(self, change):
        # Show/hide controls based on spectra checkbox
        spectra_checked = self.plot_mode_checks.children[1].value
        bandgap_checked = self.plot_mode_checks.children[2].value
        tauc_checked = self.plot_mode_checks.children[3].value

        self.layout_radio.layout.display = "flex" if spectra_checked else "none"
        self.channel_checks.layout.display = "flex" if spectra_checked else "none"
        self.x_axis_radio.layout.display = "flex" if bandgap_checked else "none"
        self.bandgap_controls.layout.display = "flex" if bandgap_checked else "none"
        self.thickness_input.layout.display = "flex" if tauc_checked else "none"

    def get_selected_plot_modes(self):
        checks = self.plot_mode_checks.children
        return [
            ("spectra_custom", checks[1].value),
            ("bandgap_derivative", checks[2].value),
            ("tauc_plot", checks[3].value),
        ]

    def get_layout_mode(self):
        return self.layout_radio.value.lower()

    def get_selected_channels(self):
        checks = self.channel_checks.children
        return [
            ("reflection", checks[1].value),
            ("transmission", checks[2].value),
            ("absorption", checks[3].value),
        ]

    def get_x_axis_mode(self):
        return "energy" if "Energy" in self.x_axis_radio.value else "wavelength"

    def get_thickness(self):
        return self.thickness_input.value

    def get_bandgap_options(self):
        """Get bandgap fitting options"""
        controls = self.bandgap_controls.children
        manual_peaks_str = controls[4].value.strip()
        manual_peaks = []

        if manual_peaks_str:
            try:
                manual_peaks = [float(x.strip()) for x in manual_peaks_str.split(",") if x.strip()]
            except ValueError:
                print("⚠️ Warning: Could not parse manual peaks. Format: 1.55, 2.1, 2.8")

        return {
            "auto_fit": controls[1].value,
            "show_in_legend": controls[2].value,
            "show_table": controls[3].value,
            "manual_peaks": manual_peaks,
        }

    def set_plot_callback(self, callback):
        self.plot_button.on_click(callback)

    def get_widget(self):
        return self.widget


class UVVisSaveUI(SaveUI):
    """Reuse JV save UI"""

    pass
