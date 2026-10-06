"""
Application controller for EQE curve analysis (Voila/Jupyter).
"""

import base64
import io
import json
import os
from datetime import datetime

import ipywidgets as widgets
import numpy as np
import pandas as pd
import requests
from batch_selection import create_batch_selection
from data_manager import DataManagerEQE
from diagnostic_helper import add_diagnostic_button_to_app, diagnose_eqe_loading
from font_size_ui import FontSizeUI
from gui_components import AuthenticationUI, ColorSchemeSelector, SaveUI
from IPython.display import HTML, Javascript, clear_output, display
from plot_manager import create_eqe_figure
from resizable_plot_utility import ResizablePlotManager

from perotf_utils.config import API_ENDPOINT, URL_BASE


class SimpleAuthManager:
    """Authentication wrapper compatible with existing JV UI components."""

    def __init__(self, base_url, api_endpoint):
        self.base_url = base_url
        self.api_endpoint = api_endpoint
        self.url = f"{base_url}{api_endpoint}"
        self.current_token = None
        self.current_user_info = None
        self.status_callback = None
        self.api_client = self  # Compatibility with JV-style components

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _update_status(self, message, color=None):
        if self.status_callback:
            self.status_callback(message, color=color)

    def authenticate_with_credentials(self, username, password):
        if not username or not password:
            raise ValueError("Username and password are required")
        token_url = f"{self.url}/auth/token"
        auth_dict = dict(username=username, password=password)

        # NOMAD instances can differ: some accept GET, some require POST.
        response = requests.get(token_url, params=auth_dict, timeout=15)
        if response.status_code == 405:
            response = requests.post(token_url, data=auth_dict, timeout=15)
        response.raise_for_status()
        token_data = response.json()
        token = token_data.get("access_token")
        if not token:
            raise RuntimeError("No access token returned by API")
        self.current_token = token
        return token

    def authenticate_with_token(self, token=None):
        if token is None:
            # Keep JV-compatible key first, then fall back to common alternatives.
            token = (
                os.environ.get("NOMAD_CLIENT_ACCESS_TOKEN")
                or os.environ.get("NOMAD_ACCESS_TOKEN")
                or os.environ.get("ACCESS_TOKEN")
            )
        if not token:
            raise ValueError("No token provided")
        self.current_token = token
        return token

    def verify_token(self):
        if not self.current_token:
            raise RuntimeError("No token set")
        verify_url = f"{self.url}/users/me"
        headers = {"Authorization": f"Bearer {self.current_token}"}
        verify_response = requests.get(verify_url, headers=headers, timeout=15)
        verify_response.raise_for_status()
        self.current_user_info = verify_response.json()
        return self.current_user_info

    def is_authenticated(self):
        return self.current_token is not None and self.current_user_info is not None

    def clear_authentication(self):
        self.current_token = None
        self.current_user_info = None


class EQEAnalysisApp:
    """Main controller for EQE curve analysis dashboard."""

    def __init__(self):
        self.auth_manager = SimpleAuthManager(URL_BASE, API_ENDPOINT)
        self.data_manager = DataManagerEQE(self.auth_manager)

        self.global_plot_data = {"figs": [], "names": []}
        self.selected_batch_ids = []

        self._init_ui_components()
        self._create_tabs()
        self._setup_callbacks()
        self._auto_authenticate()

    def _init_ui_components(self):
        self.auth_ui = AuthenticationUI(self.auth_manager)
        self.save_ui = SaveUI()
        self.color_selector = ColorSchemeSelector()
        self.font_size_ui = FontSizeUI(callback=self._on_font_size_change)

        self.batch_selection_container = widgets.Output()
        self.load_status_output = widgets.Output(
            layout=widgets.Layout(
                border="1px solid #eee", padding="10px", margin="10px 0 0 0", min_height="100px"
            )
        )

        self.dynamic_content = widgets.Output()
        self.results_content = widgets.Output(
            layout={"width": "420px", "height": "500px", "overflow": "scroll"}
        )
        self.read_output = widgets.Output()
        self.diagnostic_panel = add_diagnostic_button_to_app(self)

        self.filter_output = widgets.Output(
            layout=widgets.Layout(border="1px solid #eee", padding="10px", margin="10px 0 0 0")
        )
        self.plot_output = widgets.Output(
            layout=widgets.Layout(border="1px solid #eee", padding="10px", margin="10px 0 0 0")
        )

        self.sample_name_rows = widgets.VBox([])

        self.filter_rows_box = widgets.VBox([])
        self.add_filter_button = widgets.Button(
            description="Add Filter", button_style="", icon="plus"
        )
        self.remove_filter_button = widgets.Button(
            description="Remove Filter", button_style="", icon="minus"
        )
        self.apply_filters_button = widgets.Button(
            description="Apply Filters", button_style="primary"
        )

        self.wavelength_min = widgets.BoundedFloatText(
            value=0.0, min=0.0, max=4000.0, step=1.0, description="WL min:"
        )
        self.wavelength_max = widgets.BoundedFloatText(
            value=4000.0, min=0.0, max=4000.0, step=1.0, description="WL max:"
        )

        # --- Cycle filter ---
        self.cycle_mode_toggle = widgets.ToggleButtons(
            options=[
                ("Best EQE per sample", "best"),
                ("All cycles", "all"),
                ("Manual selection", "manual"),
            ],
            value="best",
            description="Cycle filter:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="auto"),
        )
        self.cycle_manual_select = widgets.SelectMultiple(
            options=[],
            description="Cycles:",
            style={"description_width": "initial"},
            layout=widgets.Layout(display="none", width="300px"),
        )
        self.cycle_filter_box = widgets.VBox(
            [
                widgets.HTML(
                    "<b>Cycle filter</b> <small>(only shown when multiple cycles are present)</small>"
                ),
                self.cycle_mode_toggle,
                self.cycle_manual_select,
            ],
            layout=widgets.Layout(
                display="none", border="1px solid #ccc", padding="8px", margin="6px 0"
            ),
        )

        self.group_curves_checkbox = widgets.Checkbox(
            value=True, description="Group curves with same name"
        )
        self.separate_cycle_checkbox = widgets.Checkbox(
            value=True,
            description="Separate by pixel/cycle",
            tooltip="When enabled, cycle repeats are plotted as separate groups.",
        )
        self.stats_mode_toggle = widgets.ToggleButtons(
            options=[
                ("Median + IQR", "median_iqr"),
                ("Mean + Std", "mean_std"),
                ("Best EQE curve", "best"),
            ],
            value="best",
            description="Group style:",
            style={"description_width": "initial"},
        )
        self.x_axis_toggle = widgets.ToggleButtons(
            options=[("Wavelength", "wavelength"), ("Photon energy", "photon_energy")],
            value="wavelength",
            description="X Axis:",
            style={"description_width": "initial"},
        )

        # Legend annotation checkboxes
        self.LEGEND_ANNOTATIONS = [
            ("bandgap_eqe", "Eg", "eV", 1.0),
            ("integrated_jsc", "Jsc", "mA/cm²", 1.0),
            ("integrated_j0rad", "J0rad", "mA/cm²", 0.1),
            ("voc_rad", "Vocrad", "V", 1.0),
            ("urbach_energy", "UE", "meV", 1000.0),
            ("light_bias", "LB", "", 1.0),
        ]
        self.legend_annotation_checkboxes = {
            col: widgets.Checkbox(
                value=col in ("bandgap_eqe", "integrated_jsc"),
                description=abbr,
                indent=False,
                tooltip=col,
                layout=widgets.Layout(width="80px"),
            )
            for col, abbr, unit, factor in self.LEGEND_ANNOTATIONS
        }
        self.show_pixel_checkbox = widgets.Checkbox(
            value=False,
            description="px",
            indent=False,
            layout=widgets.Layout(width="60px"),
            tooltip="Pixelnummer in Legende anzeigen",
        )
        self.show_cycle_checkbox = widgets.Checkbox(
            value=False,
            description="Cycle",
            indent=False,
            layout=widgets.Layout(width="80px"),
            tooltip="Cycle-Nummer in Legende anzeigen",
        )
        self.show_eg_vline_checkbox = widgets.Checkbox(
            value=False,
            description="Eg in Plot",
            indent=False,
            tooltip="Gestrichelte vertikale Linie bei Eg (Bandlücke) einzeichnen",
            layout=widgets.Layout(width="120px"),
        )
        self.show_jsc_cumulative_checkbox = widgets.Checkbox(
            value=False,
            description="Jsc in Plot",
            indent=False,
            tooltip="Kumulativen Jsc als gepunktete Kurve auf rechter Y-Achse einzeichnen",
            layout=widgets.Layout(width="120px"),
        )
        self.plot_button = widgets.Button(
            description="Plot EQE Curves", button_style="success", icon="line-chart"
        )

        self.download_data_button = widgets.Button(
            description="Download Data JSON", button_style="info"
        )
        self.download_zip_button = widgets.Button(
            description="Download ZIP  (SVG + PNG + Table)",
            button_style="success",
            layout=widgets.Layout(width="auto"),
        )
        self.download_zip_output = widgets.Output()

        self.font_settings = {
            "font_size_axis": 12,
            "font_size_legend": 10,
            "jv_line_width": 2.0,
            "vline_width": 1.5,
            "jsc_line_width": 1.5,
        }

    def _create_tabs(self):
        self.tabs = widgets.Tab()

        batch_tab = widgets.VBox(
            [
                widgets.HTML("<h3>Select Upload</h3>"),
                widgets.HTML("<p><i>Select one or multiple batches</i></p>"),
                self.batch_selection_container,
                self.load_status_output,
                self.diagnostic_panel,
            ]
        )
        variables_tab = widgets.VBox(
            [
                widgets.HTML(
                    "<h3>Add Variable Names</h3><p>Use JV-style naming to group EQE curves.</p>"
                ),
                self.dynamic_content,
                self.read_output,
            ]
        )

        filters_tab = widgets.VBox(
            [
                widgets.HTML(
                    "<h3>Select Filters</h3><p>Numeric filters are applied on EQE measurement parameters.</p>"
                ),
                widgets.HBox(
                    [self.add_filter_button, self.remove_filter_button, self.apply_filters_button]
                ),
                self.filter_rows_box,
                self.cycle_filter_box,
                widgets.HBox([self.wavelength_min, self.wavelength_max]),
                self.filter_output,
            ]
        )

        plots_tab = widgets.VBox(
            [
                widgets.HTML(
                    "<h3>EQE Curve Plot</h3><p>Initially only EQE curves are enabled (no boxplots/histograms).</p>"
                ),
                self.color_selector.get_widget(),
                self.font_size_ui.get_widget(),
                self.group_curves_checkbox,
                self.separate_cycle_checkbox,
                self.stats_mode_toggle,
                self.x_axis_toggle,
                widgets.HTML("<b>Werte in Legende anzeigen:</b>"),
                widgets.HBox(
                    list(self.legend_annotation_checkboxes.values())
                    + [self.show_pixel_checkbox, self.show_cycle_checkbox]
                ),
                widgets.HBox([self.show_eg_vline_checkbox, self.show_jsc_cumulative_checkbox]),
                self.plot_button,
                self.plot_output,
            ]
        )

        download_tab = widgets.VBox(
            [
                widgets.HTML("<h3>Download</h3>"),
                widgets.HBox([self.download_data_button, self.download_zip_button]),
                self.download_zip_output,
            ]
        )

        self.tabs.children = [batch_tab, variables_tab, filters_tab, plots_tab, download_tab]
        self.tabs.set_title(0, "Select Upload")
        self.tabs.set_title(1, "Add Variable Names")
        self.tabs.set_title(2, "Select Filters")
        self.tabs.set_title(3, "Select Plots")
        self.tabs.set_title(4, "Download")

    def _setup_callbacks(self):
        self.auth_ui.set_success_callback(self._on_auth_success)
        self.add_filter_button.on_click(self._on_add_filter_row)
        self.remove_filter_button.on_click(self._on_remove_filter_row)
        self.apply_filters_button.on_click(self._on_apply_filters)
        self.plot_button.on_click(self._on_create_plots)
        self.download_data_button.on_click(self._download_filtered_data)
        self.download_zip_button.on_click(self._on_download_zip_clicked)
        self.cycle_mode_toggle.observe(self._on_cycle_mode_change, names="value")

    def _on_cycle_mode_change(self, change):
        if change["new"] == "manual":
            self.cycle_manual_select.layout.display = "flex"
        else:
            self.cycle_manual_select.layout.display = "none"

    def _update_wavelength_range_from_data(self):
        """Set WL min/max widgets to the actual min/max wavelengths in the loaded data."""
        data = self.data_manager.get_data()
        curves = data.get("curves", pd.DataFrame())
        if curves.empty or "wavelength_array" not in curves.columns:
            return
        wl = pd.to_numeric(curves["wavelength_array"], errors="coerce").dropna()
        if wl.empty:
            return
        wl_min = float(np.floor(wl.min()))
        wl_max = float(np.ceil(wl.max()))
        self.wavelength_min.value = wl_min
        self.wavelength_max.value = wl_max

    def _update_cycle_filter_widget(self):
        """Show/hide cycle filter based on whether multiple cycles exist in loaded data."""
        data = self.data_manager.get_data()
        params = data.get("params", pd.DataFrame())
        if params.empty or "cycle" not in params.columns:
            self.cycle_filter_box.layout.display = "none"
            return
        cycle_vals = sorted(int(c) for c in params["cycle"].dropna().unique())
        if len(cycle_vals) <= 1:
            self.cycle_filter_box.layout.display = "none"
            return
        self.cycle_manual_select.options = [str(c) for c in cycle_vals]
        self.cycle_filter_box.layout.display = "flex"

    def _auto_authenticate(self):
        """Auto-authenticate based on environment like JV app."""
        is_hub_environment = bool(os.environ.get("JUPYTERHUB_USER"))

        if is_hub_environment:
            self.auth_ui.auth_method_selector.value = "Token (from ENV)"
            self.auth_ui.local_auth_box.layout.display = "none"
        else:
            self.auth_ui.auth_method_selector.value = "Username/Password"
            self.auth_ui.local_auth_box.layout.display = "flex"

        self.auth_ui._on_auth_button_clicked(None)

    def _on_auth_success(self):
        self.tabs.selected_index = 0
        self.auth_ui.close_settings()
        self._init_batch_selection()

    def _init_batch_selection(self):
        with self.batch_selection_container:
            clear_output(wait=True)
            selector_widget = create_batch_selection(
                self.auth_manager.url,
                self.auth_manager.current_token,
                self._load_data_from_selection,
            )
            display(selector_widget)

    def _load_data_from_selection(self, batch_selector):
        batch_ids = list(batch_selector.value)
        self.selected_batch_ids = batch_ids
        with self.load_status_output:
            clear_output(wait=True)
            if not batch_ids:
                print("Please select at least one batch.")
                return

            print(f"Loading EQE data for {len(batch_ids)} batches ...")
            try:
                self.data_manager.load_batch_data(batch_ids, output_widget=self.load_status_output)
            except Exception as exc:
                print(f"Loading failed: {exc}")
                diagnose_eqe_loading(self.data_manager)
                return

            if not self.data_manager.has_data():
                print("No EQE data found for selected batches.")
                diagnose_eqe_loading(self.data_manager)
                return

            print("Data loaded.")

        self._update_cycle_filter_widget()
        self._update_wavelength_range_from_data()
        self._make_variables_menu()
        self.tabs.selected_index = 1

    def _make_variables_menu(self):
        data = self.data_manager.get_data()
        props = data.get("properties", pd.DataFrame())
        if props.empty:
            return

        rows = []
        self._sample_name_widgets = {}
        for sample_id in props.index:
            include_box = widgets.Checkbox(
                value=bool(props.loc[sample_id, "include"]), indent=False
            )
            name_input = widgets.Text(
                value=str(props.loc[sample_id, "name"]), layout=widgets.Layout(width="280px")
            )
            rows.append(
                widgets.HBox(
                    [
                        widgets.Label(str(sample_id), layout=widgets.Layout(width="260px")),
                        include_box,
                        name_input,
                    ]
                )
            )
            self._sample_name_widgets[sample_id] = {"include": include_box, "name": name_input}

        confirm_button = widgets.Button(description="Confirm Variables", button_style="primary")

        def _on_confirm(_):
            mapping = {sid: wd["name"].value for sid, wd in self._sample_name_widgets.items()}
            includes = {sid: wd["include"].value for sid, wd in self._sample_name_widgets.items()}
            self.data_manager.apply_sample_mapping(mapping, includes)
            with self.read_output:
                clear_output(wait=True)
                print("Variables loaded")
            self.tabs.selected_index = 2

        confirm_button.on_click(_on_confirm)

        with self.dynamic_content:
            clear_output(wait=True)
            display(widgets.HTML("<p><b>Sample ID</b> | Include | Name in plot</p>"))
            display(widgets.VBox(rows))
            display(confirm_button)

    def _create_filter_row_widget(self):
        dropdown = widgets.Dropdown(
            options=self.data_manager.FILTERABLE_COLUMNS,
            description="Column:",
            layout=widgets.Layout(width="300px"),
            style={"description_width": "initial"},
        )
        op = widgets.Dropdown(
            options=["<", "<=", "==", ">=", ">", "!="],
            value=">=",
            layout=widgets.Layout(width="90px"),
        )
        val = widgets.Text(value="0", placeholder="value", layout=widgets.Layout(width="120px"))
        return widgets.HBox([dropdown, op, val])

    def _on_add_filter_row(self, _=None):
        rows = list(self.filter_rows_box.children)
        rows.append(self._create_filter_row_widget())
        self.filter_rows_box.children = tuple(rows)

    def _on_remove_filter_row(self, _=None):
        rows = list(self.filter_rows_box.children)
        if rows:
            rows.pop()
            self.filter_rows_box.children = tuple(rows)

    def _collect_filter_values(self):
        values = []
        for row in self.filter_rows_box.children:
            col = row.children[0].value
            op = row.children[1].value
            val = row.children[2].value
            if str(val).strip():
                values.append((col, op, str(val).strip()))
        return values

    def _on_apply_filters(self, _=None):
        data = self.data_manager.get_data()
        props = data.get("properties", pd.DataFrame())
        selected_samples = props.index[props["include"]].tolist() if not props.empty else []

        cycle_mode = self.cycle_mode_toggle.value
        selected_cycles = (
            [int(c) for c in self.cycle_manual_select.value]
            if self.cycle_manual_select.value
            else None
        )

        filtered, filtered_curves, reasons = self.data_manager.apply_filters(
            filter_list=self._collect_filter_values(),
            selected_sample_ids=selected_samples,
            wavelength_min=self.wavelength_min.value,
            wavelength_max=self.wavelength_max.value,
            cycle_mode=cycle_mode,
            selected_cycles=selected_cycles,
        )

        with self.filter_output:
            clear_output(wait=True)
            print("Filtering complete")
            print(f"Remaining measurements: {len(filtered)}")
            print(f"Remaining curve points: {len(filtered_curves)}")
            if reasons:
                print("Applied filters:")
                for r in reasons:
                    print(f"- {r}")

        if len(filtered) > 0:
            # Sync color slider to the number of unique plot groups after filtering
            _, tmp_curves = self._build_plot_dataframe()
            tmp_params, _ = self._build_plot_dataframe()
            n_groups = (
                max(1, tmp_params["plot_group"].nunique())
                if not tmp_params.empty and "plot_group" in tmp_params.columns
                else max(1, filtered["sample_id"].nunique())
            )
            self.color_selector.set_num_colors(n_groups)
            self.tabs.selected_index = 3

    def _build_plot_dataframe(self):
        data = self.data_manager.get_data()
        filtered_params = data.get("filtered_params", data.get("params", pd.DataFrame())).copy()
        filtered_curves = data.get("filtered_curves", data.get("curves", pd.DataFrame())).copy()
        props = data.get("properties", pd.DataFrame())

        if filtered_params.empty or filtered_curves.empty:
            return filtered_params, filtered_curves

        if not props.empty:
            name_map = props["name"].to_dict()
        else:
            name_map = {}

        filtered_params["sample_display"] = (
            filtered_params["sample_id"].map(name_map).fillna(filtered_params["sample_id"])
        )

        if self.separate_cycle_checkbox.value:
            pixel_col = (
                filtered_params["pixel"]
                if "pixel" in filtered_params.columns
                else pd.Series(np.nan, index=filtered_params.index)
            )
            cycle_col = (
                filtered_params["cycle"]
                if "cycle" in filtered_params.columns
                else pd.Series(np.nan, index=filtered_params.index)
            )
            parts = [filtered_params["sample_display"].astype(str)]
            if self.show_pixel_checkbox.value:
                parts.append(pixel_col.apply(lambda x: "" if pd.isna(x) else f"px{int(x)}"))
            if self.show_cycle_checkbox.value:
                parts.append(cycle_col.apply(lambda x: "" if pd.isna(x) else f"Cycle {int(x)}"))

            def join_parts(row):
                tokens = [str(row.iloc[0])] + [str(v) for v in row.iloc[1:] if str(v) != ""]
                return ", ".join(tokens)

            filtered_params["plot_group"] = pd.concat(parts, axis=1).apply(join_parts, axis=1)
        else:
            filtered_params["plot_group"] = filtered_params["sample_display"].astype(str)

        return filtered_params, filtered_curves

    def _on_create_plots(self, _=None):
        filtered_params, filtered_curves = self._build_plot_dataframe()
        if filtered_params.empty or filtered_curves.empty:
            with self.plot_output:
                clear_output(wait=True)
                print("No filtered EQE data available. Load data and apply filters first.")
            return

        colors = self.color_selector.get_colors(
            num_colors=max(1, filtered_params["plot_group"].nunique()),
            sampling=self.color_selector.sampling_dropdown.value,
        )

        annotate_cols = [
            (col, abbr, unit, factor)
            for col, abbr, unit, factor in self.LEGEND_ANNOTATIONS
            if self.legend_annotation_checkboxes[col].value
        ]

        fig = create_eqe_figure(
            curves_df=filtered_curves,
            params_df=filtered_params,
            x_mode=self.x_axis_toggle.value,
            group_curves=self.group_curves_checkbox.value,
            stats_mode=self.stats_mode_toggle.value,
            colors=colors,
            font_size_axis=self.font_settings["font_size_axis"],
            font_size_legend=self.font_settings["font_size_legend"],
            line_width=self.font_settings["jv_line_width"],
            annotate_cols=annotate_cols,
            show_eg_vline=self.show_eg_vline_checkbox.value,
            vline_width=self.font_settings.get("vline_width", 1.5),
            show_jsc_cumulative=self.show_jsc_cumulative_checkbox.value,
            jsc_line_width=self.font_settings.get("jsc_line_width", 1.5),
        )

        if fig is None:
            with self.plot_output:
                clear_output(wait=True)
                print("Plot creation failed: no plottable curves after filtering.")
            return

        self.global_plot_data["figs"] = [fig]
        self.global_plot_data["names"] = ["eqe_curves"]

        with self.plot_output:
            clear_output(wait=True)
            ResizablePlotManager.display_plots_resizable(
                [fig], ["eqe_curves"], container_widget=self.plot_output
            )

    def _on_font_size_change(
        self, axis_size, legend_size, jv_line_width=None, vline_width=None, jsc_line_width=None
    ):
        self.font_settings["font_size_axis"] = axis_size
        self.font_settings["font_size_legend"] = legend_size
        if jv_line_width is not None:
            self.font_settings["jv_line_width"] = float(jv_line_width)
        if vline_width is not None:
            self.font_settings["vline_width"] = float(vline_width)
        if jsc_line_width is not None:
            self.font_settings["jsc_line_width"] = float(jsc_line_width)

    def _download_filtered_data(self, _=None):
        data = self.data_manager.get_data()
        filtered_params = data.get("filtered_params", pd.DataFrame())
        filtered_curves = data.get("filtered_curves", pd.DataFrame())

        payload = {
            "filtered_params": json.loads(filtered_params.to_json(orient="records"))
            if not filtered_params.empty
            else [],
            "filtered_curves": json.loads(filtered_curves.head(200000).to_json(orient="records"))
            if not filtered_curves.empty
            else [],
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

        self.save_ui.trigger_download(
            json.dumps(payload),
            filename="eqe_filtered_data.json",
            content_type="application/json",
        )

    # ------------------------------------------------------------------
    # Download ZIP  (live SVG + ~600 dpi PNG + summary table)
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_junction(positions):
        """Return 'SJ', 'Tandem', or 'TJ' based on the set of multijunction positions."""
        pos_set = {str(p).strip().lower() for p in positions if p and str(p).strip()}
        if not pos_set:
            return "SJ"
        if "mid" in pos_set or "middle" in pos_set or len(pos_set) >= 3:
            return "TJ"
        return "Tandem"

    def _build_eqe_summary_df(self):
        """Build a flat summary table of all filtered EQE measurements."""
        filtered_params, _ = self._build_plot_dataframe()
        if filtered_params is None or filtered_params.empty:
            return pd.DataFrame()

        rows = []
        for _, row in filtered_params.iterrows():
            eg = pd.to_numeric(row.get("bandgap_eqe"), errors="coerce")
            jsc = pd.to_numeric(row.get("integrated_jsc"), errors="coerce")
            j0raw = pd.to_numeric(row.get("integrated_j0rad"), errors="coerce")
            vocrad = pd.to_numeric(row.get("voc_rad"), errors="coerce")
            ue_raw = pd.to_numeric(row.get("urbach_energy"), errors="coerce")
            lb = row.get("light_bias", "")
            pos = (
                str(row.get("multijunction_position", "")).strip()
                if "multijunction_position" in filtered_params.columns
                else ""
            )
            rows.append(
                {
                    "Variable Name": str(row.get("plot_group", row.get("sample_id", ""))),
                    "Sample": str(row.get("sample_id", "")),
                    "Pixel": str(row.get("pixel", "")),
                    "Cycle": str(row.get("cycle", "")),
                    "Position": pos,
                    "Eg (eV)": round(float(eg), 3) if pd.notna(eg) else "",
                    "Jsc (mA/cm²)": round(float(jsc), 2) if pd.notna(jsc) else "",
                    "J0rad (mA/cm²)": f"{float(j0raw) * 0.1:.2e}" if pd.notna(j0raw) else "",
                    "Vocrad (V)": round(float(vocrad), 3) if pd.notna(vocrad) else "",
                    "UE (meV)": round(float(ue_raw) * 1000, 1) if pd.notna(ue_raw) else "",
                    "LB": str(lb) if lb else "",
                }
            )
        df = pd.DataFrame(rows)

        # Add Junction Type column computed per device (Variable Name + Sample + Pixel + Cycle)
        if "Position" in df.columns:
            device_jtype = (
                df.groupby(["Variable Name", "Sample", "Pixel", "Cycle"])["Position"]
                .apply(self._classify_junction)
                .rename("Junction Type")
                .reset_index()
            )
            df = df.merge(
                device_jtype, on=["Variable Name", "Sample", "Pixel", "Cycle"], how="left"
            )
            # Drop Position column when all are SJ (no multijunction entries)
            all_sj = (df.get("Junction Type", pd.Series(["SJ"])) == "SJ").all()
            if all_sj and (df["Position"] == "").all():
                df = df.drop(columns=["Position", "Junction Type"])

        return df

    def _render_summary_table_image_bytes(self, summary_df, image_format="png"):
        """Render summary DataFrame as a PNG table and return bytes."""
        if summary_df is None or summary_df.empty:
            return None
        try:
            import matplotlib.pyplot as plt
        except Exception:
            return None

        display_df = summary_df.fillna("").copy()

        col_weights = []
        for col in display_df.columns:
            header_len = len(str(col))
            content_len = display_df[col].astype(str).map(len).max() if not display_df.empty else 0
            col_weights.append(max(header_len, content_len, 6))
        total_weight = sum(col_weights) or 1
        col_widths = [(w / total_weight) * 0.98 for w in col_weights]

        fig_width = 22
        fig_height = max(4, min(0.40 * (len(display_df) + 2), 30))
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        ax.axis("off")

        table = ax.table(
            cellText=display_df.values,
            colLabels=display_df.columns,
            loc="center",
            cellLoc="center",
            colWidths=col_widths,
        )
        table.auto_set_font_size(False)
        table.set_fontsize(7.5)
        table.scale(1, 1.25)
        for (row, col), cell in table.get_celld().items():
            if row == 0:
                cell.set_facecolor("#e9ecef")
                cell.set_text_props(weight="bold")

        ax.set_title("EQE Measurement Summary", fontsize=12, fontweight="bold", pad=12)
        buf = io.BytesIO()
        fig.tight_layout()
        if image_format == "pdf":
            fig.savefig(buf, format="pdf", bbox_inches="tight")
        else:
            fig.savefig(buf, format="png", dpi=250, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    def _build_download_table_assets(self):
        """Return list of {'path', 'bytes'} dicts for inclusion in the ZIP."""
        summary_df = self._build_eqe_summary_df()
        if summary_df.empty:
            return []
        assets = []
        assets.append(
            {
                "path": "table/eqe_summary.csv",
                "bytes": summary_df.to_csv(index=False).encode("utf-8"),
            }
        )
        png_bytes = self._render_summary_table_image_bytes(summary_df, "png")
        if png_bytes:
            assets.append({"path": "table/eqe_summary.png", "bytes": png_bytes})
        return assets

    def _on_download_zip_clicked(self, b=None):
        """Create a single ZIP with live SVG/PNG plots plus EQE summary table."""
        if not self.global_plot_data.get("figs"):
            with self.download_zip_output:
                clear_output(wait=True)
                print("No plots available. Create plots in 'Select Plots' first.")
            return

        plot_names = self.global_plot_data.get("names", []) or ["eqe_plot"]
        table_assets = self._build_download_table_assets()

        js_table_assets = []
        asset_blob_fields = []
        for idx, asset in enumerate(table_assets):
            asset_id = f"eqe-table-asset-{idx}"
            asset_b64 = base64.b64encode(asset["bytes"]).decode("ascii")
            js_table_assets.append({"path": asset["path"], "field_id": asset_id})
            asset_blob_fields.append(
                f"<textarea id='{asset_id}' style='display:none;'>{asset_b64}</textarea>"
            )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"EQE_Download_{timestamp}.zip"

        payload = {"zip_name": zip_name, "plot_names": plot_names, "table_assets": js_table_assets}
        payload_json = json.dumps(payload)

        js_code = f"""
        (async function() {{
            const payload = {payload_json};
            const statusEl   = document.getElementById('eqe-download-status');
            const progressEl = document.getElementById('eqe-download-progress');
            const progressTxtEl = document.getElementById('eqe-download-progress-text');

            function setStatus(text, isError) {{
                if (!statusEl) return;
                statusEl.style.color = isError ? '#b00020' : '#1f2937';
                statusEl.textContent = text;
            }}
            function setProgress(current, total) {{
                if (!progressEl || !progressTxtEl) return;
                const safeTotal = Math.max(1, total || 1);
                const safeCurrent = Math.max(0, Math.min(current || 0, safeTotal));
                progressEl.max   = safeTotal;
                progressEl.value = safeCurrent;
                const pct = Math.round((safeCurrent / safeTotal) * 100);
                progressTxtEl.textContent = safeCurrent + '/' + safeTotal + ' (' + pct + '%)';
            }}
            function sanitizeName(name) {{
                return String(name || 'plot').replace(/[<>:\\"/\\\\|?*]/g, '_').replace(/\\.+$/g, '').trim() || 'plot';
            }}
            function getBaseName(name, idx) {{
                const fallback = 'plot_' + (idx + 1);
                if (!name) return fallback;
                const safe = sanitizeName(name);
                return safe.replace(/\\.[a-zA-Z0-9]+$/g, '') || fallback;
            }}
            async function ensureJsZip() {{
                if (window.JSZip) return;
                await new Promise((resolve, reject) => {{
                    const s = document.createElement('script');
                    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js';
                    s.onload = resolve;
                    s.onerror = () => reject(new Error('Could not load JSZip'));
                    document.head.appendChild(s);
                }});
            }}
            function triggerBlobDownload(blob, filename) {{
                const objectUrl = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = objectUrl; link.download = filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                setTimeout(() => {{ try {{ window.URL.revokeObjectURL(objectUrl); }} catch(e) {{}} }}, 1000);
            }}
            function getImageDimensions(gd) {{
                if (!gd) return {{ width: 1200, height: 800 }};
                const fl = gd._fullLayout || {{}};
                const w  = Math.max(Number(fl.width) || 0, Number(gd.clientWidth || gd.offsetWidth || 0), 1200);
                const h  = Math.max(Number(fl.height) || 0, Number(gd.clientHeight || gd.offsetHeight || 0), 800);
                return {{ width: w, height: h }};
            }}
            async function toImageWithRetry(gd, opts, retries) {{
                let lastErr = null;
                for (let attempt = 1; attempt <= retries; attempt++) {{
                    try {{ return await Plotly.toImage(gd, opts); }}
                    catch (err) {{
                        lastErr = err;
                        await new Promise(r => setTimeout(r, 120 * attempt));
                    }}
                }}
                throw lastErr || new Error('toImage failed');
            }}
            try {{
                setStatus('Preparing ZIP export...', false);
                setProgress(0, 1);
                await ensureJsZip();

                const plotDivs = Array.from(document.querySelectorAll('div.js-plotly-plot[id^="plot_"]'));
                if (!plotDivs.length) throw new Error('No rendered plots found. Please create plots first.');

                const zip = new JSZip();
                const svgFolder = zip.folder('svg');
                const pngFolder = zip.folder('png');
                const warnings  = [];
                setProgress(0, plotDivs.length);

                for (let i = 0; i < plotDivs.length; i++) {{
                    const gd = plotDivs[i];
                    const baseName = getBaseName(payload.plot_names[i], i);
                    setStatus('Capturing plot ' + (i+1) + ' / ' + plotDivs.length + ' ...', false);
                    try {{
                        if (!gd || !gd.data) throw new Error('Plot container is not ready.');
                        try {{ Plotly.Plots.resize(gd); }} catch(e) {{}}
                        const dims = getImageDimensions(gd);

                        const svgUri = await toImageWithRetry(gd, {{ format: 'svg', width: dims.width, height: dims.height }}, 3);
                        const svgBase64Prefix = 'data:image/svg+xml;base64,';
                        const svgPlainPrefix  = 'data:image/svg+xml,';
                        let svgText = '';
                        if (svgUri.startsWith(svgBase64Prefix)) {{
                            svgText = atob(svgUri.slice(svgBase64Prefix.length));
                        }} else if (svgUri.startsWith(svgPlainPrefix)) {{
                            svgText = decodeURIComponent(svgUri.slice(svgPlainPrefix.length));
                        }} else {{ throw new Error('Unexpected SVG data URI format.'); }}
                        svgFolder.file(baseName + '.svg', svgText);

                        const pngUri = await toImageWithRetry(gd, {{ format: 'png', width: dims.width, height: dims.height, scale: 6 }}, 3);
                        const pngPrefix = 'data:image/png;base64,';
                        if (!pngUri.startsWith(pngPrefix)) throw new Error('Unexpected PNG data URI format.');
                        pngFolder.file(baseName + '.png', pngUri.slice(pngPrefix.length), {{ base64: true }});
                    }} catch (plotErr) {{
                        warnings.push('Plot ' + (i+1) + ' (' + baseName + '): ' + (plotErr.message || plotErr));
                        console.error('Plot export error:', plotErr);
                    }}
                    setProgress(i + 1, plotDivs.length);
                }}

                if (Array.isArray(payload.table_assets)) {{
                    for (const asset of payload.table_assets) {{
                        if (!asset || !asset.path || !asset.field_id) continue;
                        const field = document.getElementById(asset.field_id);
                        const b64   = field ? (field.value || '').replace(/\\s+/g, '') : '';
                        if (b64) zip.file(asset.path, b64, {{ base64: true }});
                    }}
                }}

                const exportedCount = plotDivs.length - warnings.length;
                if (exportedCount <= 0) throw new Error('No plots could be exported.');
                if (warnings.length) zip.file('table/export_warnings.txt', warnings.join('\\n'));

                setStatus('Generating ZIP file...', false);
                const blob = await zip.generateAsync({{ type: 'blob' }});
                triggerBlobDownload(blob, payload.zip_name);

                if (warnings.length) {{
                    setStatus('Download started: ' + payload.zip_name + ' (' + exportedCount + ' plots, ' + warnings.length + ' skipped)', false);
                }} else {{
                    setStatus('Download started: ' + payload.zip_name, false);
                }}
            }} catch(err) {{
                console.error(err);
                setStatus('Export failed: ' + (err && err.message ? err.message : err), true);
            }}
        }})();
        """

        js_code_text = js_code.replace("</textarea>", "<\\/textarea>")
        onclick_code = (
            "(function(){{"
            "try{{"
            "var src=document.getElementById('eqe-export-js');"
            "if(!src){{throw new Error('Export source not found.');}}"
            "(0,eval)(src.value);"
            "}}catch(e){{"
            "console.error(e);"
            "var el=document.getElementById('eqe-download-status');"
            "if(el){{el.style.color='#b00020';el.textContent='Export failed: '+(e&&e.message?e.message:e);}}"
            "}}"
            "}})();"
        )

        with self.download_zip_output:
            clear_output(wait=True)
            display(
                HTML(f"""
                <div id='eqe-download-status' style='font-weight:600; margin-bottom:8px;'>Ready to start export.</div>
                <div style='display:flex; align-items:center; gap:10px; margin-bottom:10px;'>
                    <progress id='eqe-download-progress' value='0' max='1' style='width:280px; height:14px;'></progress>
                    <span id='eqe-download-progress-text' style='font-size:12px; color:#4b5563;'>0/1 (0%)</span>
                </div>
                <textarea id='eqe-export-js' style='display:none;'>{js_code_text}</textarea>
                {"".join(asset_blob_fields)}
                <button onclick="{onclick_code}"
                        style='background:#198754;color:white;border:none;border-radius:6px;padding:8px 14px;cursor:pointer;'>
                    Start ZIP Export
                </button>
            """)
            )

    def get_dashboard(self):
        app_layout = widgets.Layout(max_width="1200px", margin="0 auto", padding="15px")
        header = widgets.HBox(
            [widgets.HTML("<h1 style='margin: 0; flex-grow: 1;'>EQE Analysis Dashboard</h1>")],
            layout=widgets.Layout(
                justify_content="space-between",
                align_items="flex-start",
                margin="0 0 20px 0",
            ),
        )
        return widgets.VBox([header, self.auth_ui.get_widget(), self.tabs], layout=app_layout)
