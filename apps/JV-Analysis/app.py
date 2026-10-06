"""
Simplified Application Controller
Main orchestrator for the JV Analysis Dashboard with cleaner organization.
"""

__author__ = "Stolen by Joshua"
__institution__ = "HZb -> KIT"
__created__ = "September 2025"

import base64
import io
import json
import os
import time
import zipfile
from datetime import datetime
from typing import Any, cast

import ipywidgets as widgets
import openpyxl
import pandas as pd
import plotly.graph_objects as go
import requests
from data_manager import DataManager
from diagnostic_helper import debug_logger
from font_size_ui import FontSizeUI

# Import the new organized modules
from gui_components import AuthenticationUI, ColorSchemeSelector, FilterUI, InfoUI, PlotUI, SaveUI
from IPython.display import HTML, Javascript, Markdown, clear_output, display
from jv_curve_analysis_ui_NEW import EnhancedJVCurveAnalysisUI
from openpyxl.utils.dataframe import dataframe_to_rows
from plot_manager import PlotManager, plotting_string_action
from resizable_plot_utility import ResizablePlotManager
from utils import save_combined_excel_data, save_full_data_frame

from perotf_utils.api_calls import get_all_measurements_except_JV, get_ids_in_batch
from perotf_utils.batch_selection import create_batch_selection
from perotf_utils.config import API_ENDPOINT, GUI_ENDPOINT, URL_BASE
from perotf_utils.error_handler import ErrorHandler

# ── PptxGenJS library loader ──────────────────────────────────────────────────
# The library is downloaded ONCE from the CDN by the Python server and cached
# locally.  On every PPTX button-click it is injected inline into the page so
# the user's browser never needs to reach any CDN.
_PPTXGENJS_CDN = "https://cdn.jsdelivr.net/npm/pptxgenjs@4.0.1/dist/pptxgen.bundle.js"
_PPTXGENJS_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pptxgen_cache.js")

# Simple module-level cache to avoid assigning attributes to function objects
_pptxgenjs_cache: dict = {}


def _load_pptxgenjs():
    """Return PptxGenJS bundle as a string, downloading and caching on first use."""
    # Memory cache
    mem = _pptxgenjs_cache.get("content")
    if mem:
        return mem
    # Disk: user-placed file takes priority, then our own cache
    for path in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "pptxgen.bundled.js"),
        _PPTXGENJS_CACHE,
    ]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    _pptxgenjs_cache["content"] = fh.read()
                return _pptxgenjs_cache.get("content")
            except Exception:
                pass
    # Server-side download (browser is never involved)
    try:
        resp = requests.get(_PPTXGENJS_CDN, timeout=30)
        resp.raise_for_status()
        content = resp.text
        try:
            with open(_PPTXGENJS_CACHE, "w", encoding="utf-8") as fh:
                fh.write(content)
        except Exception:
            pass
        _pptxgenjs_cache["content"] = content
        return content
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────


class SimpleAuthManager:
    """Simplified authentication manager"""

    def __init__(self, base_url, api_endpoint):
        self.base_url = base_url
        self.api_endpoint = api_endpoint
        self.url = f"{base_url}{api_endpoint}"
        self.current_token = None
        self.current_user_info = None
        self.status_callback = None
        self.api_client = self  # Compatibility

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _update_status(self, message, color=None):
        if self.status_callback:
            self.status_callback(message, color)

    def authenticate_with_credentials(self, username, password):
        if not username or not password:
            raise ValueError("Username and Password are required.")

        auth_dict = dict(username=username, password=password)
        token_url = f"{self.url}/auth/token"

        response = requests.get(token_url, params=auth_dict, timeout=10)
        response.raise_for_status()

        token_data = response.json()
        if "access_token" not in token_data:
            raise ValueError("Access token not found in response.")

        self.current_token = token_data["access_token"]
        return self.current_token

    def authenticate_with_token(self, token=None):
        if token is None:
            token = os.environ.get("NOMAD_CLIENT_ACCESS_TOKEN")
            if not token:
                raise ValueError("Token not found in environment variable.")

        self.current_token = token
        return self.current_token

    def verify_token(self):
        if not self.current_token:
            raise ValueError("No token available for verification.")

        verify_url = f"{self.url}/users/me"
        headers = {"Authorization": f"Bearer {self.current_token}"}

        verify_response = requests.get(verify_url, headers=headers, timeout=10)
        verify_response.raise_for_status()

        self.current_user_info = verify_response.json()
        return self.current_user_info

    def is_authenticated(self):
        return self.current_token is not None and self.current_user_info is not None

    def clear_authentication(self):
        self.current_token = None
        self.current_user_info = None

    def get_user_display_name(self):
        if not self.current_user_info:
            return "Unknown User"
        return self.current_user_info.get(
            "name", self.current_user_info.get("username", "Unknown User")
        )


class JVAnalysisApp:
    """Simplified main application controller"""

    def __init__(self):
        # Initialize core components
        self.auth_manager = SimpleAuthManager(URL_BASE, API_ENDPOINT)
        self.data_manager = DataManager(self.auth_manager)

        # Application state
        self.is_conditions = False
        self.global_plot_data = {"figs": [], "names": [], "workbook": None}
        self.selected_batch_ids = []

        # Initialize UI components
        self._init_ui_components()
        self._create_tabs()
        self._setup_callbacks()
        self._auto_authenticate()

    def _init_ui_components(self):
        """Initialize UI components with proper data manager integration"""
        self.auth_ui = AuthenticationUI(self.auth_manager)
        self.filter_ui = FilterUI()
        self.plot_ui = PlotUI()
        self.jv_curve_analysis_ui = EnhancedJVCurveAnalysisUI()
        self.save_ui = SaveUI()
        self.color_selector = ColorSchemeSelector()
        self.font_size_ui = FontSizeUI(callback=self._on_font_size_change)  # ADD this line
        self.info_ui = InfoUI()  # ADD this line

        # Give FilterUI access to DataManager for preview functionality
        # Use a typed cast to Any so static analyzers (Pylance) won't flag unknown attributes
        fi = cast(Any, self.filter_ui)
        try:
            if hasattr(fi, "set_data_manager"):
                try:
                    fi.set_data_manager(self.data_manager)
                except Exception:
                    pass
        except Exception:
            # defensive: ignore any attribute/introspection errors
            pass
        # Assign data_manager attribute on the cast object (silences static type checks)
        try:
            fi.data_manager = self.data_manager
        except Exception:
            pass

        # Tab-specific widgets
        self.batch_selection_container = widgets.Output()
        self.load_status_output = widgets.Output(
            layout=widgets.Layout(
                border="1px solid #eee", padding="10px", margin="10px 0 0 0", min_height="100px"
            )
        )

        # Variables tab widgets
        self.default_variables = widgets.Dropdown(
            options=["all", "Batch name", "Variation"],
            value="Variation",
            description="Defaults:",
            style={"description_width": "initial"},
        )

        self.dynamic_content = widgets.Output()
        self.results_content = widgets.Output(
            layout={"width": "400px", "height": "500px", "overflow": "scroll"}
        )
        self.read_output = widgets.Output()
        self.download_content = widgets.Output()
        self.show_other_measurements = widgets.Output()

        self.download_button = widgets.Button(
            description="Download JV",
            button_style="info",
            layout=widgets.Layout(min_width="150px"),
            disabled=True,
        )

        self.download_curves_button = widgets.Button(
            description="Download Curves",
            button_style="info",
            layout=widgets.Layout(min_width="150px"),
            disabled=True,
        )

        # Download tab widgets
        self.download_zip_button = widgets.Button(
            description="Create Download ZIP",
            button_style="success",
            icon="download",
            layout=widgets.Layout(min_width="220px"),
            disabled=True,
        )
        self.download_zip_output = widgets.Output(
            layout=widgets.Layout(border="1px solid #eee", padding="10px", margin="10px 0 0 0")
        )

        self.download_pptx_button = widgets.Button(
            description="Download Summary PPTX",
            button_style="warning",
            icon="file-powerpoint-o",
            layout=widgets.Layout(min_width="220px"),
            disabled=True,
        )
        self.download_pptx_output = widgets.Output(
            layout=widgets.Layout(border="1px solid #eee", padding="10px", margin="10px 0 0 0")
        )

        self.download_theresa_button = widgets.Button(
            description="Theresa Style Download",
            button_style="primary",
            icon="download",
            layout=widgets.Layout(min_width="220px"),
            disabled=True,
        )
        self.download_theresa_output = widgets.Output(
            layout=widgets.Layout(border="1px solid #eee", padding="10px", margin="10px 0 0 0")
        )

    def _create_tabs(self):
        """Create tab system"""
        self.select_upload_tab = widgets.VBox(
            [
                self.auth_ui.get_widget(),
                widgets.HTML("<h3>Select Upload</h3>"),
                widgets.HTML("<p><i>Select one or multiple batches</i></p>"),
                self.batch_selection_container,
                self.load_status_output,
            ]
        )

        self.add_variables_tab = widgets.VBox(
            [widgets.HTML("<h3>Add Variable Names</h3>"), self.dynamic_content]
        )

        # Create plot tab with color selector and font size controls
        plot_tab_content = widgets.VBox(
            [
                self.plot_ui.get_widget(),
                widgets.HTML("<hr style='margin: 20px 0;'>"),  # Separator
                self.color_selector.get_widget(),
                widgets.HTML("<hr style='margin: 20px 0;'>"),  # Separator
                self.font_size_ui.get_widget(),  # ADD font size UI
                widgets.HTML("<hr style='margin: 20px 0;'>"),  # Another separator
                widgets.HTML("<h3>Generated Plots</h3>"),
                self.plot_ui.plotted_content,  # Now plots appear after color selection
            ]
        )

        self.tabs = widgets.Tab()

        self.jv_curve_analysis_tab = self.jv_curve_analysis_ui.get_widget()

        self.download_tab = widgets.VBox(
            [
                widgets.HTML("<h3>Download</h3>"),
                widgets.HTML(
                    "<p>Create one ZIP containing live plots as SVG/PNG plus a variation summary table.</p>"
                ),
                widgets.HBox(
                    [
                        self.download_zip_button,
                        self.download_pptx_button,
                        self.download_theresa_button,
                    ]
                ),
                self.download_zip_output,
                self.download_pptx_output,
                self.download_theresa_output,
            ]
        )

        # Create debug dashboard tab

        self.tabs.children = [
            self.select_upload_tab,
            self.add_variables_tab,
            self.filter_ui.get_widget(),
            plot_tab_content,
            self.jv_curve_analysis_tab,
            self.download_tab,
        ]

        tab_labels = [
            "Select Upload",
            "Add Variable Names",
            "Select Filters",
            "Select Plots",
            "JV Curve Analysis",
            "Download",
        ]
        for i, title in enumerate(tab_labels):
            self.tabs.set_title(i, title)

    def _create_debug_dashboard(self):
        """Create a dashboard for viewing debug logs"""
        refresh_button = widgets.Button(
            description="🔄 Refresh Logs", button_style="info", layout=widgets.Layout(width="150px")
        )

        clear_button = widgets.Button(
            description="🗑️ Clear Logs", button_style="warning", layout=widgets.Layout(width="150px")
        )

        self.debug_output = widgets.HTML()

        def on_refresh_click(b):
            self.debug_output.value = debug_logger.get_html()

        def on_clear_click(b):
            debug_logger.clear()
            self.debug_output.value = "<p style='color: #999;'>Logs cleared</p>"

        refresh_button.on_click(on_refresh_click)
        clear_button.on_click(on_clear_click)

        # Initialize with current logs
        self.debug_output.value = debug_logger.get_html()

        return widgets.VBox(
            [
                widgets.HTML("<h3>🔧 Variable Reordering & Plot Debug Logs</h3>"),
                widgets.HTML(
                    "<p>Monitor the variable reordering process and plot generation here:</p>"
                ),
                widgets.HBox([refresh_button, clear_button]),
                widgets.HTML("<hr style='margin: 15px 0;'>"),
                self.debug_output,
            ],
            layout=widgets.Layout(border="1px solid #ddd", padding="15px", margin="0"),
        )

    def _update_debug_display(self):
        """Refresh debug output if the debug dashboard exists."""
        if hasattr(self, "debug_output"):
            self.debug_output.value = debug_logger.get_html()

    def _setup_callbacks(self):
        """Setup all callbacks"""
        self.auth_ui.set_success_callback(self._on_auth_success)
        self.filter_ui.set_apply_callback(self._on_apply_filters)
        self.plot_ui.set_plot_callback(self._on_create_plots)
        self.jv_curve_analysis_ui.set_plot_callback(self._on_create_curve_analysis_plot)
        self.plot_ui.set_reorder_update_callback(self._on_variable_order_changed)
        self.default_variables.observe(self._on_change_default_variables, names=["value"])
        self.download_button.on_click(self._download_jv_data)
        self.download_curves_button.on_click(self._download_curves_data)
        self.download_zip_button.on_click(self._on_download_zip_clicked)
        self.download_pptx_button.on_click(self._on_download_pptx_clicked)
        self.download_theresa_button.on_click(self._on_theresa_download_clicked)

    def _on_variable_order_changed(self):
        """Handle when variable order is changed - update debug and regenerate plots"""
        current_order = self.plot_ui.get_variable_order()
        debug_logger.add("PLOT", f"[REORDER CALLBACK] Current variable order: {current_order}")
        self._update_debug_display()
        # Regenerate plots with new variable order
        debug_logger.add("PLOT", "[REORDER CALLBACK] Regenerating plots with new order")
        self._on_create_plots(None)

    def _auto_authenticate(self):
        """Auto-authenticate based on environment"""
        is_hub_environment = bool(os.environ.get("JUPYTERHUB_USER"))

        if is_hub_environment:
            self.auth_ui.auth_method_selector.value = "Token (from ENV)"
            self.auth_ui.local_auth_box.layout.display = "none"
        else:
            self.auth_ui.auth_method_selector.value = "Username/Password"
            self.auth_ui.local_auth_box.layout.display = "flex"

        self.auth_ui._on_auth_button_clicked(None)

    def _on_auth_success(self):
        """Handle successful authentication"""
        self.tabs.selected_index = 0
        self._init_batch_selection()

    def _init_batch_selection(self):
        """Initialize batch selection after authentication"""
        with self.batch_selection_container:
            clear_output(wait=True)

            if not self.auth_manager.is_authenticated():
                print("Please authenticate first before loading batch data.")
                return

            try:
                url = self.auth_manager.url
                token = self.auth_manager.current_token
                # print("📊 Initializing batch selection...")
                batch_selection_widget = create_batch_selection(
                    url, token, self._load_data_from_selection
                )
                display(batch_selection_widget)
            except requests.exceptions.RequestException as e:
                # Network/server error - show detailed message
                ErrorHandler.log_error(
                    "Initializing batch selection - Server Error",
                    e,
                    self.batch_selection_container,
                    show_traceback=True,
                )
            except Exception as e:
                # Other errors
                ErrorHandler.log_error(
                    "Initializing batch selection",
                    e,
                    self.batch_selection_container,
                    show_traceback=True,
                )

    def _load_data_from_selection(self, batch_selector):
        """Load data from batch selection with user feedback"""
        batch_ids = list(batch_selector.value) if batch_selector.value else []
        self.selected_batch_ids = batch_ids

        success = self.data_manager.load_batch_data(batch_ids, self.load_status_output)

        if success:
            data = self.data_manager.get_data()

            # CRITICAL: Show cycle information in LOAD STATUS OUTPUT
            with self.load_status_output:
                print(f"\n{'=' * 60}")
                print("📊 CYCLE DETECTION RESULTS:")
                print(f"{'=' * 60}")

                if self.data_manager.has_cycle_data:
                    print("✅ Cycle data FOUND!")
                    print(
                        f"   • Sample-pixel combinations with cycles: {len(self.data_manager.cycle_info)}"
                    )

                    # Show statistics
                    if "cycle_number" in data["jvc"].columns:
                        cycle_df = data["jvc"][data["jvc"]["cycle_number"].notna()]
                        if not cycle_df.empty:
                            num_cycles = cycle_df["cycle_number"].nunique()
                            total_with_cycles = len(cycle_df)
                            print(f"   • Total measurements with cycle info: {total_with_cycles}")
                            print(
                                f"   • Unique cycle numbers found: {sorted(cycle_df['cycle_number'].unique().tolist())}"
                            )

                            # Show examples
                            print("\n   Example measurements:")
                            for _, row in cycle_df.head(3).iterrows():
                                print(
                                    f"      - {row['sample']} / {row['px_number']} / Cycle {int(row['cycle_number'])} / PCE: {row['PCE(%)']:.2f}%"
                                )
                else:
                    print("ℹ️  NO cycle data detected in this dataset")
                    print("   • This is normal for datasets without cycle measurements")
                    print("   • Cycle filter will be hidden in Filter tab")

                print(f"{'=' * 60}\n")

            # Set data for FilterUI
            self.filter_ui.set_sample_data(data)
            self.jv_curve_analysis_ui.set_data(data)

            # Show general data summary
            with self.load_status_output:
                print("\n📈 Data Loading Summary:")
                print(f"   Total records loaded: {len(data['jvc'])}")
                print(f"   Unique samples: {data['jvc']['sample'].nunique()}")
                print(f"   Unique cells: {data['jvc'].groupby('sample')['cell'].nunique().sum()}")
                print(f"   Batches: {data['jvc']['batch'].nunique()}")
                print("\n✅ Data ready for variable assignment and filtering!")

            with self.download_zip_output:
                clear_output(wait=True)
                display(
                    widgets.HTML(
                        "<p><i>Load and plot data first, then use this tab to export everything as one ZIP.</i></p>"
                    )
                )

            self._enable_tab(1)
            self.tabs.selected_index = 1
            self._make_variables_menu()

    def _make_variables_menu(self):
        """Create variables menu using DataManager's summary"""
        unique_vals = self.data_manager.get_unique_values()
        data = self.data_manager.get_data()

        variables_markdown = f"""
# Add variable names
There are {len(unique_vals)} variations found.
If you tested specific variables or conditions for each sample, please write them down below.
"""

        results_markdown = self.data_manager.generate_summary_statistics(data["jvc"])

        with self.dynamic_content:
            clear_output(wait=True)
            display(Markdown(variables_markdown))
            display(self.default_variables)

            widgets_table, text_widgets_dict = self._create_widgets_table(unique_vals)
            retrieve_button = widgets.Button(
                description="Confirm variables",
                button_style="success",
                layout=widgets.Layout(min_width="150px"),
            )
            retrieve_button.on_click(lambda b: self._on_retrieve_clicked(text_widgets_dict))

            information_group = widgets.HBox([widgets_table, self.results_content])
            display(information_group)
            button_group = widgets.HBox([retrieve_button, self.read_output])
            display(button_group)

        # Show download buttons
        with self.download_content:
            clear_output(wait=True)
            self.download_button.disabled = True
            self.download_curves_button.disabled = True
            download_box = widgets.HBox([self.download_button, self.download_curves_button])
            display(download_box)
            display(
                widgets.HTML(
                    "<p><i>Download buttons will be enabled after confirming variables.</i></p>"
                )
            )

        with self.results_content:
            clear_output()
            display(Markdown(results_markdown))

        with self.read_output:
            clear_output()
            print("⚠️ Variables not loaded")

    def _create_widgets_table(self, elements_list):
        """Create widgets table for variable input"""
        rows = []
        text_widgets = {}

        for item in elements_list:
            item_split = item.split("&")
            batch, variable = "", item
            if len(item_split) >= 2:
                batch, variable = item_split[0], "&".join(item_split[1:])

            default_value = ""
            if self.default_variables.value == "Batch name":
                default_value = batch if batch else "_".join(item.split("_")[:-1])
            elif self.default_variables.value == "Variation":
                default_value = variable

            label = widgets.Label(value=variable)
            text_input = widgets.Text(value=default_value, placeholder="Variable e.g. 1000 rpm")
            row = widgets.HBox([label, text_input])
            rows.append(row)
            text_widgets[item] = text_input

        return widgets.VBox(rows), text_widgets

    def _on_retrieve_clicked(self, text_widgets_dict):
        """Handle variable retrieval and condition assignment"""
        self.is_conditions = True

        # Ensure conditions_dict always exists to satisfy static analysis
        conditions_dict = {}

        # Create conditions_dict from the text widget values
        data = self.data_manager.get_data()
        if data and "jvc" in data:
            conditions_dict = {}

            # For each unique identifier, get the user's input for the condition
            for identifier in data["jvc"]["identifier"].unique():
                if identifier in text_widgets_dict:
                    # Use the user's input from the text widget
                    user_condition = text_widgets_dict[identifier].value.strip()
                    if user_condition:
                        conditions_dict[identifier] = user_condition
                    else:
                        # Fallback to variation from identifier if user didn't enter anything
                        if identifier and "&" in str(identifier):
                            variation = str(identifier).split("&", 1)[1]
                            conditions_dict[identifier] = variation
                        else:
                            conditions_dict[identifier] = "Unknown"
                else:
                    # Fallback for identifiers not in text_widgets_dict
                    if identifier and "&" in str(identifier):
                        variation = str(identifier).split("&", 1)[1]
                        conditions_dict[identifier] = variation
                    else:
                        conditions_dict[identifier] = "Unknown"

        # Apply the conditions
        success = self.data_manager.apply_conditions(conditions_dict)

        if success:
            # Update FilterUI with the new condition data
            updated_data = self.data_manager.get_data()
            self.filter_ui.set_sample_data(updated_data)
            self.jv_curve_analysis_ui.set_data(updated_data)

            with self.read_output:
                clear_output()
                print("✅ Variables loaded successfully")

            with self.download_content:
                clear_output(wait=True)
                display(widgets.HTML("<h3>Download Data</h3>"))
                self.download_button.disabled = False
                self.download_curves_button.disabled = False
                download_box = widgets.HBox([self.download_button, self.download_curves_button])
                display(download_box)
                display(widgets.HTML("<p><i>✅ Download buttons are now enabled!</i></p>"))

            self._show_measurements_table()
            self._enable_tab(2)
            self.tabs.selected_index = 2
        else:
            with self.read_output:
                clear_output()
                print("❌ Error loading variables")

    def _on_change_default_variables(self, change):
        """Handle default variables change"""
        self._make_variables_menu()

    def _on_font_size_change(self, axis_size, title_size, legend_size, jv_line_width=None):
        """Handle font size changes"""
        # This callback is triggered when font sizes are adjusted in the UI
        # The actual font and JV curve line settings are applied during plot creation
        # via plotting_string_action.
        pass

    def _download_jv_data(self, e=None):
        """Download JV data as CSV"""
        jvc_data, _ = self.data_manager.get_export_data()
        if jvc_data is not None:
            jvc_csv = jvc_data.to_csv(index=False)
            self.save_ui.trigger_download(jvc_csv, "export_jvc.csv", "text/plain")
        else:
            print("No JV data available for download")

    def _download_curves_data(self, e=None):
        """Download curves data as CSV"""
        _, curves_data = self.data_manager.get_export_data()
        if curves_data is not None:
            curves_csv = curves_data.to_csv(index=False)
            self.save_ui.trigger_download(curves_csv, "export_curves.csv", "text/plain")
        else:
            print("No curves data available for download")

    def _show_measurements_table(self):
        """Show other measurements table"""
        try:
            data = self.data_manager.get_data()
            if not data or "jvc" not in data:
                return

            with self.show_other_measurements:
                clear_output(wait=True)
                print("Loading measurements data...")

                batch_ids_value = list(data["jvc"]["batch"].unique())
                if not batch_ids_value:
                    print("No batch IDs found in loaded data.")
                    return

                url = self.auth_manager.url
                token = self.auth_manager.current_token

                try:
                    # Import necessary functions
                    from perotf_utils.api_calls import (
                        get_all_measurements_except_JV,
                        get_ids_in_batch,
                    )

                    sample_ids = get_ids_in_batch(url, token, batch_ids_value)
                    measurements_data = get_all_measurements_except_JV(url, token, sample_ids)

                    import pandas as pd

                    df = pd.DataFrame()

                    def make_clickable(r):
                        base_url = self.auth_manager.base_url
                        if "SEM" in r[1]["entry_type"]:
                            return f'<a href="{base_url}{GUI_ENDPOINT}/entry/id/{r[1]["entry_id"]}/data/data/images:0/image_preview/preview" rel="noopener noreferrer" target="_blank">{r[1]["entry_type"].split("_")[-1]}</a>'
                        return f'<a href="{base_url}{GUI_ENDPOINT}/entry/id/{r[1]["entry_id"]}/data/data" rel="noopener noreferrer" target="_blank">{r[1]["entry_type"].split("_")[-1]}</a>'

                    for key, value in measurements_data.items():
                        if value:
                            df[key] = pd.Series([make_clickable(r) for r in value])

                    if df.empty:
                        print("No additional measurements found.")
                    else:
                        display(widgets.HTML("<h3>Additional Measurements</h3>"))
                        display(widgets.HTML(df.to_html(escape=False)))

                except AssertionError:
                    print("No additional measurements found for the selected batches.")
                except Exception as api_error:
                    print(f"Could not load additional measurements: {api_error}")

        except Exception as e:
            ErrorHandler.log_error("displaying measurements", e, self.show_other_measurements)

    def _count_unique_conditions(self, filtered_df):
        """Count unique conditions in filtered data for color palette adjustment

        Args:
            filtered_df: Filtered DataFrame

        Returns:
            Number of unique conditions (clamped to 2-20)
        """
        if filtered_df is None or filtered_df.empty:
            return 8  # Default fallback

        # Count unique conditions (the main grouping variable)
        if "condition" in filtered_df.columns:
            num_conditions = filtered_df["condition"].nunique()
        elif "sample" in filtered_df.columns:
            # Fallback to samples if conditions not assigned
            num_conditions = filtered_df["sample"].nunique()
        else:
            num_conditions = 8  # Default

        # Clamp to reasonable bounds (min 2, max 20)
        num_conditions = max(2, min(20, num_conditions))

        return num_conditions

    def _on_apply_filters(self, b):
        """Handle filter application using sample-based filtering with cycle support"""
        data = self.data_manager.get_data()
        if not data or "jvc" not in data:
            with self.filter_ui.main_output:
                print("No data loaded. Please load data first.")
            return

        # Get filter values
        selected_items = self.filter_ui.get_selected_items()
        filter_values = self.filter_ui.get_filter_values()
        direction_value = self.filter_ui.get_direction_value()
        cycle_settings = self.filter_ui.get_cycle_filter_settings()  # CHANGED

        with self.filter_ui.main_output:
            clear_output(wait=True)

            print(f"{'=' * 70}")
            print("🔧 FILTER APPLICATION")
            print(f"{'=' * 70}")
            print(f"Direction filter: {direction_value}")
            print(f"Cycle filter mode: {cycle_settings.get('mode', 'disabled')}")  # CHANGED
            if cycle_settings.get("mode") == "specific":
                print(f"   Selected cycles: {cycle_settings.get('cycles', [])}")
            print(f"Sample selection active: {selected_items is not None}")
            print(f"Numeric filters: {len(filter_values)}")
            print(f"{'=' * 70}\n")

            try:
                working_data = data["jvc"].copy()
                original_count = len(working_data) if working_data is not None else 0

                # STEP 1: Apply cycle filter based on mode
                if cycle_settings["mode"] == "best_only" and self.data_manager.has_cycle_data:
                    print("🔄 Step 1: Applying best-cycle-per-pixel filter...")
                    working_data = self.data_manager.apply_best_cycle_filter(
                        working_data, verbose=True
                    )
                    after_cycle_count = len(working_data) if working_data is not None else 0
                    print(f"   Result: {original_count} → {after_cycle_count} records")
                    print()

                elif cycle_settings["mode"] == "specific" and self.data_manager.has_cycle_data:
                    print(
                        f"🔄 Step 1: Filtering for specific cycles: {cycle_settings['cycles']}..."
                    )
                    working_data = self.data_manager.apply_specific_cycle_filter(
                        working_data, cycle_settings["cycles"], verbose=True
                    )
                    after_cycle_count = len(working_data) if working_data is not None else 0
                    print(f"   Result: {original_count} → {after_cycle_count} records")
                    print()

                else:
                    if cycle_settings["mode"] != "disabled" and cycle_settings["mode"] != "all":
                        print("ℹ️  Cycle filter set but no cycle data available - skipping")
                        print()
                    after_cycle_count = original_count

                # STEP 2: Apply standard filters
                print("🔍 Step 2: Applying standard filters...")

                # Temporarily replace data
                original_jvc = data["jvc"]
                data["jvc"] = working_data

                filtered_df, omitted_df, filter_params = self.data_manager.apply_filters(
                    filter_values, direction_value, selected_items, verbose=True
                )

                # Restore
                data["jvc"] = original_jvc

                # STEP 3: Show summary
                final_count = len(filtered_df) if filtered_df is not None else 0

                print(f"\n{'=' * 70}")
                print("📊 FILTERING SUMMARY:")
                print(f"{'=' * 70}")
                print(f"Original dataset:        {original_count:>6} records")

                if (
                    cycle_settings["mode"] in ["best_only", "specific"]
                    and self.data_manager.has_cycle_data
                ):
                    cycle_removed = original_count - after_cycle_count
                    print(
                        f"After cycle filter:      {after_cycle_count:>6} records ({cycle_removed} removed)"
                    )

                print(f"After all filters:       {final_count:>6} records")
                print(f"Retention rate:          {(final_count / original_count) * 100:>5.1f}%")
                print(f"{'=' * 70}")

                if final_count > 0:
                    print("\n✅ Filtering complete! Proceed to plotting tab.")

                    # Auto-adjust color count based on number of conditions
                    num_conditions = self._count_unique_conditions(filtered_df)
                    if num_conditions > 0:
                        self.color_selector.set_num_colors(num_conditions)
                        print(
                            f"🎨 Auto-adjusted color palette: {num_conditions} colors for {num_conditions} unique conditions"
                        )

                    # Update variable reorder widget with available variations
                    if filtered_df is not None and not filtered_df.empty:
                        debug_logger.add(
                            "PLOT", f"filtered_df columns: {list(filtered_df.columns)}"
                        )
                        debug_logger.add("PLOT", f"filtered_df shape: {filtered_df.shape}")

                        if "identifier" in filtered_df.columns:
                            # Preserve the original upload order (same as "Add Variable Names" page)
                            original_order = list(self.data_manager.get_unique_values())
                            present_ids = set(filtered_df["identifier"].unique())
                            available_vars = [v for v in original_order if v in present_ids]
                            # Safety: add any identifiers present in filtered data but missing from unique_vals
                            for v in filtered_df["identifier"].unique():
                                if v not in present_ids or v not in set(available_vars):
                                    available_vars.append(v)
                            debug_logger.add(
                                "PLOT",
                                f"Using 'identifier' column (upload order preserved), found {len(available_vars)} unique values",
                            )
                        elif "condition" in filtered_df.columns:
                            available_vars = list(filtered_df["condition"].unique())
                            debug_logger.add(
                                "PLOT",
                                f"Using 'condition' column, found {len(available_vars)} unique values",
                            )
                        elif "sample" in filtered_df.columns:
                            available_vars = list(filtered_df["sample"].unique())
                            debug_logger.add(
                                "PLOT",
                                f"Using 'sample' column, found {len(available_vars)} unique values",
                            )
                        else:
                            available_vars = []
                            debug_logger.add("PLOT", "No suitable column found for reordering!")

                        debug_logger.add("PLOT", f"available_vars: {available_vars}")

                        if len(available_vars) > 0:
                            self.plot_ui.update_variable_reorder(available_vars)
                            print(
                                f"📊 Variable reordering enabled: {len(available_vars)} variations available"
                            )
                            self._update_debug_display()

                    # Enable and navigate to the Select Plots tab
                    self._enable_tab(3)
                    self.download_theresa_button.disabled = False
                    try:
                        # Select the plots tab (index 3)
                        self.tabs.selected_index = 3
                    except Exception:
                        pass

                    # Trigger plot creation automatically (simulate clicking 'Plot Selection')
                    try:
                        # Call the same handler used by the Plot button; safe to pass None
                        self._on_create_plots(None)
                    except Exception as e:
                        print(f"⚠️ Auto-plot failed: {e}")
                else:
                    print("\n⚠️  No data remains after filtering. Please adjust filters.")

            except Exception as e:
                print("\n❌ Error during filtering:")
                import traceback

                traceback.print_exc()

    def _on_create_plots(self, b):
        """Handle plot creation"""
        data = self.data_manager.get_data()
        if not data or "filtered" not in data:
            with self.plot_ui.plotted_content:
                print("Please apply filters first in the 'Select Filters' tab.")
            return

        filtered_data = data.get("filtered")
        if filtered_data is None or filtered_data.empty:
            with self.plot_ui.plotted_content:
                print("No data remains after filtering. Please adjust your filters.")
            return

        plot_selections = self.plot_ui.get_plot_selections()

        sampling_method = self.color_selector.sampling_dropdown.value
        selected_colors = self.color_selector.get_colors(
            num_colors=self.color_selector.num_colors, sampling=sampling_method
        )

        # Show processing message immediately
        with self.plot_ui.plotted_content:
            clear_output(wait=True)
            display(
                widgets.HTML("""
            <div style="text-align: center; padding: 40px; background-color: #f8f9fa; border-radius: 8px; border: 2px solid #007bff;">
                <div style="font-size: 24px; margin-bottom: 15px;">🔄</div>
                <h3 style="color: #007bff; margin-bottom: 10px;">Creating Plots...</h3>
                <p style="color: #6c757d;">Please be patient while we generate your visualizations.</p>
            </div>
            """)
            )

        try:
            # First, sync the variable order from the DOM (if user dragged and dropped)
            debug_logger.add("PLOT", "=== SYNCING VARIABLE ORDER FROM DOM ===")
            self.plot_ui.sync_variable_order_from_dom()

            # Give it a moment for the Comm to process (JavaScript is async)
            time.sleep(0.2)

            # Get variable order for sorting
            variable_order = self.plot_ui.get_variable_order()
            debug_logger.add("PLOT", "=== PLOT GENERATION START ===")
            debug_logger.add("PLOT", f"Variable order from UI: {variable_order}")
            debug_logger.add(
                "PLOT", f"Variable order is empty: {not variable_order or len(variable_order) == 0}"
            )

            # Create workbook for Excel export with proper analysis sheets
            wb = openpyxl.Workbook()
            if wb.active is not None:
                wb.remove(wb.active)  # Remove default sheet

            # Add main data sheet first
            main_sheet = wb.create_sheet(title="All_data")
            for r in dataframe_to_rows(filtered_data, index=True, header=True):
                main_sheet.append(r)

            # CRITICAL FIX: Prepare data structures for plotting
            # Extract filtered data components
            filtered_jv = data.get("filtered")
            complete_jv = data.get("jvc")
            filtered_curves = data.get(
                "filtered_curves", data.get("curves")
            )  # Use filtered curves or fall back to all curves

            debug_logger.add(
                "PLOT",
                f"filtered_jv shape: {filtered_jv.shape if filtered_jv is not None else 'None'}",
            )
            debug_logger.add(
                "PLOT",
                f"filtered_jv columns: {filtered_jv.columns.tolist() if filtered_jv is not None else 'None'}",
            )

            # Apply variable ordering to filtered_jv if order is specified
            if variable_order and len(variable_order) > 0 and filtered_jv is not None:
                debug_logger.add("PLOT", "[ORDER] ✓ Proceeding with variable order application")
                debug_logger.add(
                    "PLOT", f"[ORDER] Applying variable order to {len(filtered_jv)} rows"
                )
                # Determine which column contains the variation info
                if "identifier" in filtered_jv.columns:
                    order_col = "identifier"
                elif "condition" in filtered_jv.columns:
                    order_col = "condition"
                elif "sample" in filtered_jv.columns:
                    order_col = "sample"
                else:
                    order_col = None

                debug_logger.add("PLOT", f"[ORDER] Using column '{order_col}' for ordering")
                if order_col is not None:
                    unique_before = filtered_jv[order_col].unique().tolist()
                    debug_logger.add(
                        "PLOT", f"[ORDER] Unique values BEFORE ordering: {unique_before}"
                    )
                    debug_logger.add("PLOT", f"[ORDER] Requested order: {variable_order}")

                    # Check if all requested categories exist in data
                    missing_categories = [cat for cat in variable_order if cat not in unique_before]
                    extra_categories = [cat for cat in unique_before if cat not in variable_order]
                    if missing_categories:
                        debug_logger.add(
                            "PLOT",
                            f"[ORDER] WARNING: Missing categories in data: {missing_categories}",
                        )
                    if extra_categories:
                        debug_logger.add(
                            "PLOT",
                            f"[ORDER] WARNING: Extra categories in data (not in order): {extra_categories}",
                        )

                    # Convert to categorical with specified order, then sort
                    debug_logger.add("PLOT", "[ORDER] Converting to categorical...")
                    filtered_jv[order_col] = pd.Categorical(
                        filtered_jv[order_col], categories=variable_order, ordered=True
                    )
                    debug_logger.add("PLOT", f"[ORDER] Sorting by {order_col}...")
                    filtered_jv = filtered_jv.sort_values(order_col)
                    unique_after = filtered_jv[order_col].unique().tolist()
                    debug_logger.add(
                        "PLOT", f"[ORDER] Unique values AFTER ordering: {unique_after}"
                    )
                else:
                    debug_logger.add("PLOT", "[ORDER] ✗ Could not determine order_col")
            else:
                debug_logger.add("PLOT", "[ORDER] ✗ SKIPPED variable order application")
                debug_logger.add(
                    "PLOT",
                    f"[ORDER]   - variable_order provided: {variable_order is not None and len(variable_order) > 0}",
                )
                debug_logger.add("PLOT", f"[ORDER]   - variable_order value: {variable_order}")
                debug_logger.add(
                    "PLOT", f"[ORDER]   - filtered_jv is not None: {filtered_jv is not None}"
                )

            # Update debug display after ordering logic
            self._update_debug_display()

            # Exclude disabled variations (unchecked in the reorder widget)
            disabled_vars = self.plot_ui.get_disabled_variables()
            if disabled_vars:
                disabled_set = set(disabled_vars)
                debug_logger.add(
                    "PLOT",
                    f"[DISABLED] Excluding {len(disabled_set)} disabled variations: {sorted(disabled_set)}",
                )
                if filtered_jv is not None and "identifier" in filtered_jv.columns:
                    disabled_sample_ids = set()
                    if "sample_id" in filtered_jv.columns:
                        disabled_sample_ids = set(
                            filtered_jv.loc[
                                filtered_jv["identifier"].isin(disabled_set), "sample_id"
                            ]
                        )
                    filtered_jv = filtered_jv[~filtered_jv["identifier"].isin(disabled_set)].copy()
                    debug_logger.add(
                        "PLOT", f"[DISABLED] filtered_jv rows after exclusion: {len(filtered_jv)}"
                    )
                    if (
                        filtered_curves is not None
                        and not filtered_curves.empty
                        and disabled_sample_ids
                        and "sample_id" in filtered_curves.columns
                    ):
                        filtered_curves = filtered_curves[
                            ~filtered_curves["sample_id"].isin(disabled_sample_ids)
                        ].copy()
                if variable_order:
                    variable_order = [v for v in variable_order if v not in disabled_set]
                    debug_logger.add(
                        "PLOT", f"[DISABLED] variable_order after exclusion: {variable_order}"
                    )

            # Prepare support data tuple
            omitted_jv = data.get("junk", pd.DataFrame())
            filter_parameters = self.data_manager.get_filter_parameters()
            path = os.getcwd()
            samples = (
                self.data_manager.unique_vals if hasattr(self.data_manager, "unique_vals") else []
            )

            # Package data for plotting function
            jv_data = (filtered_jv, complete_jv, filtered_curves)
            support_data = (omitted_jv, filter_parameters, self.is_conditions, path, samples)

            # GET scan direction separation setting
            separate_scan_dir = self.plot_ui.get_separate_scan_dir()

            # Get font size settings
            font_size_settings = self.font_size_ui.get_font_sizes()

            # Derive condition order from the already-sorted filtered_jv so that
            # boxplot color assignments (by position in data) and JV curve color
            # assignments stay in sync.
            condition_order = None
            if filtered_jv is not None and "condition" in filtered_jv.columns:
                condition_order = list(filtered_jv["condition"].unique())
                debug_logger.add(
                    "PLOT", f"[COLOR] condition_order for JV curves: {condition_order}"
                )

            # Create plots using the plot manager
            figs, names = plotting_string_action(
                plot_selections,
                jv_data,
                support_data,
                is_voila=True,
                color_scheme=selected_colors,
                separate_scan_dir=separate_scan_dir,
                condition_order=condition_order,
                **font_size_settings,  # Pass font size parameters
            )

            # CRITICAL FIX: Initialize lists and generate titles/subtitles
            titles = []
            subtitles = []

            # Match each figure with its plot selection
            selection_idx = 0  # Track which plot selection we're processing

            for i, fig in enumerate(figs):
                # Find corresponding plot selection (skip combination plots that generate multiple figures)
                if selection_idx < len(plot_selections):
                    plot_type, option1, option2 = plot_selections[selection_idx]

                    if plot_type == "Boxplot":
                        # Generate title and subtitle for boxplot
                        # Hysteresis always merges Forward/Reverse into one value, so the split note doesn't apply
                        direction_note = (
                            " (Separated by Scan Direction)"
                            if (separate_scan_dir and option1 != "Hysteresis")
                            else ""
                        )
                        datatype = "data"

                        # CRITICAL FIX: Handle 'all' option where option1='all' and option2 contains the x-axis variable
                        if option1 == "all":
                            # Combined grid boxplot: all 4 parameters in one grid
                            grouping_display = option2.replace("by ", "") if option2 else "Unknown"
                            title = f"Combined Boxplots (PCE, FF, Jsc, Voc) by {grouping_display}{direction_note}"
                            title += " (filtered out)" if datatype == "junk" else " (filtered data)"

                            filtered_df = data.get("filtered")
                            num_measurements = len(filtered_df) if filtered_df is not None else 0

                            # Handle different grouping columns
                            grouping_col = grouping_display
                            if grouping_col == "Variable":
                                grouping_col = "condition"
                            elif grouping_col == "Scan Direction":
                                grouping_col = "direction"

                            num_categories = (
                                filtered_df[grouping_col].nunique()
                                if filtered_df is not None and grouping_col in filtered_df.columns
                                else 0
                            )
                            subtitle = f"Data from {num_measurements} measurements across {num_categories} categories"
                        else:
                            # Regular single-parameter boxplot
                            grouping_display = option2.replace("by ", "") if option2 else "Unknown"
                            title = f"Boxplot of {option1} by {grouping_display}{direction_note}"
                            title += " (filtered out)" if datatype == "junk" else " (filtered data)"

                            filtered_df = data.get("filtered")
                            num_measurements = len(filtered_df) if filtered_df is not None else 0

                            # Handle different grouping columns
                            grouping_col = grouping_display
                            if grouping_col == "Variable":
                                grouping_col = "condition"
                            elif grouping_col == "Scan Direction":
                                grouping_col = "direction"

                            num_categories = (
                                filtered_df[grouping_col].nunique()
                                if filtered_df is not None and grouping_col in filtered_df.columns
                                else 0
                            )
                            subtitle = f"Data from {num_measurements} measurements across {num_categories} categories"

                        titles.append(title)
                        subtitles.append(subtitle)
                        selection_idx += 1

                    elif plot_type == "JV Curve":
                        # JV Curves use title from figure or generate from option
                        if option1 == "Best device per condition":
                            title = "JV Curves - Best Measurement per Condition"
                        elif option1 == "Best device only":
                            filtered_df = data.get("filtered")
                            if filtered_df is not None and not filtered_df.empty:
                                best_idx = filtered_df["PCE(%)"].idxmax()
                                best_sample = filtered_df.loc[best_idx]["sample"]
                                best_cell = filtered_df.loc[best_idx]["cell"]
                                title = (
                                    f"JV Curves - Best Device ({best_sample} [Cell {best_cell}])"
                                )
                            else:
                                title = f"JV Curves - {option1}"
                        else:
                            title = f"JV Curves - {option1}"

                        titles.append(title)
                        subtitles.append(None)

                        # Check if this is a multi-figure plot (separated by cell/substrate)
                        if "Separated" not in option1:
                            selection_idx += 1
                        else:
                            # Multi-figure plots: only increment after all figures are processed
                            # Check if next figure is still part of this selection
                            if i + 1 >= len(figs) or selection_idx + 1 >= len(plot_selections):
                                selection_idx += 1

                    else:
                        # Unknown plot type - use filename
                        titles.append(names[i] if i < len(names) else f"Plot {i + 1}")
                        subtitles.append(None)
                        selection_idx += 1
                else:
                    # No more plot selections - use filename
                    titles.append(names[i] if i < len(names) else f"Plot {i + 1}")
                    subtitles.append(None)

            # Store plot data
            self.global_plot_data["figs"] = figs
            self.global_plot_data["names"] = names
            self.global_plot_data["workbook"] = wb
            self.global_plot_data["titles"] = titles
            self.global_plot_data["subtitles"] = subtitles
            self.download_zip_button.disabled = len(figs) == 0
            self.download_pptx_button.disabled = len(figs) == 0

            with self.download_zip_output:
                clear_output(wait=True)
                if figs:
                    display(
                        widgets.HTML(
                            "<p><b>Ready:</b> ZIP export can now capture the currently displayed plots (including moved legends) and a summary table.</p>"
                        )
                    )
                else:
                    display(
                        widgets.HTML(
                            "<p><i>No plots available yet. Create plots in 'Select Plots' first.</i></p>"
                        )
                    )

            # Display plots
            with self.plot_ui.plotted_content:
                clear_output(wait=True)
                ResizablePlotManager.display_plots_resizable(
                    figs,
                    names,
                    titles=titles,
                    subtitles=subtitles,
                    container_widget=self.plot_ui.plotted_content,
                )

        except Exception as e:
            with self.plot_ui.plotted_content:
                clear_output(wait=True)
                display(
                    widgets.HTML(f"""
                <div style="text-align: center; padding: 40px; background-color: #f8d7da; border-radius: 8px;">
                    <div style="font-size: 24px; margin-bottom: 15px;">❌</div>
                    <h3 style="color: #dc3545;">Plot Creation Failed</h3>
                    <p>Error: {str(e)}</p>
                </div>
                """)
                )
            ErrorHandler.handle_plot_error(e, self.plot_ui.plotted_content)

    def _apply_curve_analysis_filters(self, jvc_df):
        """Apply numeric filters for curve analysis (separate from sample selection)."""
        if jvc_df is None or jvc_df.empty:
            return pd.DataFrame()

        filtered_df = jvc_df.copy()

        # Apply condition exclusion
        excluded_conditions = set(self.jv_curve_analysis_ui.get_excluded_conditions())
        if excluded_conditions and "condition" in filtered_df.columns:
            filtered_df = filtered_df[
                ~filtered_df["condition"].astype(str).isin(excluded_conditions)
            ]

        # Apply numeric filters FIRST (before sample selection)
        operators = {
            ">": lambda series, val: series > val,
            ">=": lambda series, val: series >= val,
            "<": lambda series, val: series < val,
            "<=": lambda series, val: series <= val,
            "==": lambda series, val: series == val,
            "!=": lambda series, val: series != val,
        }

        for column, op, raw_value in self.jv_curve_analysis_ui.get_numeric_filters():
            if column not in filtered_df.columns or op not in operators:
                continue

            threshold = float(raw_value)
            numeric_series = pd.to_numeric(filtered_df[column], errors="coerce")
            mask = operators[op](numeric_series, threshold)
            filtered_df = filtered_df[mask.fillna(False)]

        return filtered_df

    def _on_create_curve_analysis_plot(self, b):
        """Create enhanced JV Curve Analysis plot with all new features."""
        data = self.data_manager.get_data()
        if not data or "jvc" not in data or data["jvc"] is None or data["jvc"].empty:
            with self.jv_curve_analysis_ui.status_output:
                clear_output(wait=True)
                print("No data loaded. Please load a batch first.")
            with self.jv_curve_analysis_ui.plotted_content:
                clear_output(wait=True)
                print("No data available for JV curve analysis.")
            return

        with self.jv_curve_analysis_ui.plotted_content:
            clear_output(wait=True)
            display(
                widgets.HTML("""
            <div style="text-align: center; padding: 24px; background-color: #f8f9fa; border-radius: 8px; border: 1px solid #ddd;">
                <h4 style="margin: 0; color: #007bff;">Generating JV Curve Analysis Plot...</h4>
            </div>
            """)
            )

        try:
            source_jv = data["jvc"]

            # Apply numeric filters and condition exclusion
            filtered_jv = self._apply_curve_analysis_filters(source_jv)

            with self.jv_curve_analysis_ui.status_output:
                clear_output(wait=True)
                print("JV Curve Analysis Filter Summary")
                print(f"Original records: {len(source_jv)}")
                print(f"After numeric + condition filters: {len(filtered_jv)}")

                excluded_conditions = self.jv_curve_analysis_ui.get_excluded_conditions()
                numeric_filters = self.jv_curve_analysis_ui.get_numeric_filters()
                sample_filters = self.jv_curve_analysis_ui.get_sample_specific_filters()

                print(f"Excluded conditions: {len(excluded_conditions)}")
                print(f"Numeric filters: {len(numeric_filters)}")
                if sample_filters:
                    samples_with_filters = [
                        s
                        for s in sample_filters
                        if sample_filters[s]["pixels"] or sample_filters[s]["cycles"]
                    ]
                    print(
                        f"Samples with specific pixel/cycle selection: {len(samples_with_filters)}"
                    )

            if filtered_jv.empty:
                with self.jv_curve_analysis_ui.plotted_content:
                    clear_output(wait=True)
                    print("No JV records remain after filters. Please relax your filters.")
                return

            if "curves" not in data or data["curves"] is None or data["curves"].empty:
                with self.jv_curve_analysis_ui.plotted_content:
                    clear_output(wait=True)
                    print("No JV curve data available.")
                return

            filtered_curves = self.data_manager._create_matching_curves_from_filtered_jv(
                filtered_jv
            )

            # Get color scheme from UI
            color_scheme_name = self.jv_curve_analysis_ui.get_color_scheme()
            color_list = self._get_plotly_colors(color_scheme_name, num_colors=12)

            # Get font sizes
            font_size_settings = self.font_size_ui.get_font_sizes()

            # Create plot manager and set parameters
            plot_manager = PlotManager()
            plot_manager.set_output_path(os.getcwd())
            plot_manager.set_font_sizes(
                axis_size=font_size_settings.get("font_size_axis"),
                title_size=font_size_settings.get("font_size_title"),
                legend_size=font_size_settings.get("font_size_legend"),
            )
            plot_manager.set_jv_line_width(font_size_settings.get("jv_line_width"))

            # Get plot configuration from UI
            plot_mode = self.jv_curve_analysis_ui.get_plot_mode()
            use_log_current = self.jv_curve_analysis_ui.use_log_current()
            plot_style = self.jv_curve_analysis_ui.get_plot_style()
            legend_config = self.jv_curve_analysis_ui.get_legend_config()
            use_plot_filter = self.jv_curve_analysis_ui.use_plot_filter()
            sample_filters = self.jv_curve_analysis_ui.get_sample_specific_filters()

            # Create the enhanced plot
            fig, fig_name = plot_manager.create_enhanced_jv_curve_plot(
                filtered_jv,
                filtered_curves,
                mode=plot_mode,
                log_current=use_log_current,
                colors=color_list,
                plot_style=plot_style,
                sample_filters=sample_filters,
                legend_config=legend_config,
                use_plot_filter=use_plot_filter,
            )

            title = "JV Curve Analysis - Best device per condition"
            if plot_mode == "all_curves_unfiltered":
                title = "JV Curve Analysis - All JV Curves (unfiltered)"
            if use_log_current:
                title += " (ln|J|)"

            subtitle = f"{len(filtered_jv)} JV measurements shown"

            with self.jv_curve_analysis_ui.plotted_content:
                clear_output(wait=True)
                ResizablePlotManager.display_plots_resizable(
                    [fig],
                    [fig_name],
                    titles=[title],
                    subtitles=[subtitle],
                    container_widget=self.jv_curve_analysis_ui.plotted_content,
                    jv_legend_table=True,
                )

        except Exception as e:
            with self.jv_curve_analysis_ui.plotted_content:
                clear_output(wait=True)
                display(
                    widgets.HTML(f"""
                <div style="text-align: center; padding: 24px; background-color: #f8d7da; border-radius: 8px;">
                    <h4 style="margin: 0; color: #dc3545;">JV Curve Analysis failed</h4>
                    <p style="margin: 8px 0 0 0;">{str(e)}</p>
                </div>
                """)
                )
            ErrorHandler.handle_plot_error(e, self.jv_curve_analysis_ui.plotted_content)

    def _get_plotly_colors(self, color_scheme, num_colors=12):
        """Get Plotly colors from a scheme name."""
        import plotly.express as px

        color_schemes = {
            "viridis": px.colors.sequential.Viridis,
            "plasma": px.colors.sequential.Plasma,
            "inferno": px.colors.sequential.Inferno,
            "magma": px.colors.sequential.Magma,
            "blues": px.colors.sequential.Blues,
            "reds": px.colors.sequential.Reds,
            "greens": px.colors.sequential.Greens,
            "plotly": px.colors.qualitative.Plotly,
            "set1": px.colors.qualitative.Set1,
            "set2": px.colors.qualitative.Set2,
        }

        colors = color_schemes.get(color_scheme.lower(), px.colors.sequential.Viridis)

        # Sample evenly if we need more colors than available
        if num_colors <= len(colors):
            return colors[:num_colors]
        else:
            indices = [int(i * len(colors) / num_colors) for i in range(num_colors)]
            return [colors[i] for i in indices]

    def _sanitize_filename(self, value):
        """Return a filesystem-safe filename stem."""
        if value is None:
            return "file"
        safe = str(value)
        for ch in '<>:"/\\|?*':
            safe = safe.replace(ch, "_")
        safe = safe.strip().strip(".")
        return safe or "file"

    def _build_variation_summary_df(self):
        """Create summary table with best and median PCE per upload and variation."""
        data = self.data_manager.get_data() or {}

        # Prefer filtered data if available; otherwise use full JV data.
        source_df = data.get("filtered")
        if source_df is None or source_df.empty:
            source_df = data.get("jvc")

        if source_df is None or source_df.empty:
            return pd.DataFrame()

        df = source_df.copy()

        if "PCE(%)" not in df.columns:
            return pd.DataFrame()

        # Ensure numeric PCE and drop invalid rows.
        df["PCE(%)"] = pd.to_numeric(df["PCE(%)"], errors="coerce")
        df = df.dropna(subset=["PCE(%)"])
        if df.empty:
            return pd.DataFrame()

        # Upload name shown in Select Upload is the batch id.
        upload_col = "batch" if "batch" in df.columns else "display_batch"
        if upload_col not in df.columns:
            df[upload_col] = "unknown_upload"

        # Variation column (condition is the user-assigned variation).
        variation_col = "condition" if "condition" in df.columns else "identifier"
        if variation_col not in df.columns:
            variation_col = upload_col

        # Pixel column for reporting source of PCE.
        pixel_col = "px_number" if "px_number" in df.columns else "cell"
        if pixel_col not in df.columns:
            df[pixel_col] = "n/a"

        results = []
        grouped = df.groupby([upload_col, variation_col], dropna=False)

        for (upload_name, variation_name), group in grouped:
            if group.empty:
                continue

            best_idx = group["PCE(%)"].idxmax()
            best_row = group.loc[best_idx]

            median_target = group["PCE(%)"].median()
            median_row = (
                group.assign(_delta=(group["PCE(%)"] - median_target).abs())
                .sort_values(by=["_delta", "PCE(%)"], ascending=[True, False])
                .iloc[0]
            )

            results.append(
                {
                    "Variation": str(variation_name),
                    "N measurements": int(len(group)),
                    "Best PCE (%)": round(float(best_row["PCE(%)"]), 2),
                    "Best Sample": str(best_row.get("sample", "n/a")),
                    "Best Pixel": str(best_row.get(pixel_col, "n/a")),
                    "Best Direction": str(best_row.get("direction", "n/a")),
                    "Median PCE (%)": round(float(median_row["PCE(%)"]), 2),
                    "Median Sample": str(median_row.get("sample", "n/a")),
                    "Median Pixel": str(median_row.get(pixel_col, "n/a")),
                    "Median Direction": str(median_row.get("direction", "n/a")),
                }
            )

        summary_df = pd.DataFrame(results)
        if summary_df.empty:
            return summary_df

        return summary_df.reset_index(drop=True)

    def _render_summary_table_image_bytes(self, summary_df, image_format="png"):
        """Render summary DataFrame as an image/PDF table and return bytes."""
        if summary_df is None or summary_df.empty:
            return None

        try:
            import matplotlib.pyplot as plt
        except Exception:
            return None

        display_df = summary_df.copy()
        display_df = display_df.fillna("")

        # Compute variable column widths from content length and emphasize sample columns.
        col_weights = []
        for col in display_df.columns:
            header_len = len(str(col))
            content_len = display_df[col].astype(str).map(len).max() if not display_df.empty else 0
            weight = max(header_len, content_len, 8)
            if col in ("Best Sample", "Median Sample"):
                weight = int(weight * 1.7)
            col_weights.append(weight)

        total_weight = sum(col_weights) if col_weights else 1
        col_widths = [(w / total_weight) * 0.98 for w in col_weights]

        # Dynamic figure size to keep the table readable for different row counts.
        fig_width = 20
        fig_height = max(4, min(0.45 * (len(display_df) + 2), 30))

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
        table.set_fontsize(8)
        table.scale(1, 1.25)

        # Header styling improves readability in exported assets.
        for (row, col), cell in table.get_celld().items():
            if row == 0:
                cell.set_facecolor("#e9ecef")
                cell.set_text_props(weight="bold")

        ax.set_title(
            "JV Variation Summary (Best and Median PCE)", fontsize=12, fontweight="bold", pad=12
        )

        buffer = io.BytesIO()
        fig.tight_layout()
        if image_format == "pdf":
            fig.savefig(buffer, format="pdf", bbox_inches="tight")
        else:
            fig.savefig(buffer, format="png", dpi=250, bbox_inches="tight")
        plt.close(fig)
        buffer.seek(0)
        return buffer.getvalue()

    def _on_download_pptx_clicked(self, b=None):
        """
        Capture live plot images from the browser (same mechanism as the ZIP
        download) and assemble a PPTX via PptxGenJS injected inline from the
        server-cached bundle -- the browser makes NO CDN request.
        """
        names = self.global_plot_data.get("names", [])
        figs = self.global_plot_data.get("figs", [])

        # Indices of the two target plots inside the rendered figure list.
        jv_idx = next((i for i, n in enumerate(names) if "JV_best_per_condition" in str(n)), None)
        box_idx = next((i for i, n in enumerate(names) if "Boxplot_Combined" in str(n)), None)

        # ── Kaleido fallback for plots not present in this session ────────────
        def _kaleido_b64(fig):
            if fig is None:
                return ""
            try:
                import plotly.io as pio

                png = pio.to_image(fig, format="png", width=1400, height=860, scale=2)
                return base64.b64encode(png).decode("ascii")
            except Exception:
                return ""

        jv_fb = ""
        box_fb = ""

        if jv_idx is None or box_idx is None:
            data = self.data_manager.get_data() or {}
            filtered_jv = data.get("filtered")
            filtered_curves = data.get("filtered_curves", data.get("curves"))

            if filtered_jv is not None and not filtered_jv.empty:
                sampling = self.color_selector.sampling_dropdown.value
                n_cond = (
                    max(1, filtered_jv["condition"].nunique())
                    if "condition" in filtered_jv.columns
                    else 1
                )
                colors = self.color_selector.get_colors(num_colors=n_cond, sampling=sampling)
                pm = PlotManager()

                if jv_idx is None:
                    try:
                        fig, _ = pm.create_jv_best_per_condition_plot(
                            filtered_jv, filtered_curves, colors=colors
                        )
                        jv_fb = _kaleido_b64(pm.apply_jv_line_width_to_figure(fig))
                    except Exception:
                        pass

                if box_idx is None:
                    var_x = "condition" if "condition" in filtered_jv.columns else "sample"
                    omitted_jv = data.get("junk", pd.DataFrame())
                    try:
                        fig, _ = pm.create_combined_boxplot_grid(
                            filtered_jv,
                            var_x,
                            [omitted_jv, self.data_manager.get_filter_parameters()],
                            "data",
                            colors=colors,
                        )
                        box_fb = _kaleido_b64(fig)
                    except Exception:
                        pass

        batch_str = ", ".join(str(b) for b in (self.selected_batch_ids or [])) or "-"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"JV_Summary_{timestamp}.pptx"

        jv_fb_id = "jv-pptx-fb-jv"
        box_fb_id = "jv-pptx-fb-box"

        payload_json = json.dumps(
            {
                "jv_idx": jv_idx if jv_idx is not None else -1,
                "box_idx": box_idx if box_idx is not None else -1,
                "batch_str": batch_str,
                "filename": filename,
            }
        )

        # ── Load PptxGenJS -- server downloads once + caches; browser offline ─
        pptxgen_js = _load_pptxgenjs()
        if pptxgen_js is None:
            with self.download_pptx_output:
                clear_output(wait=True)
                display(
                    HTML(
                        '<div style="color:#b00020;padding:6px 0;font-size:13px;">'
                        "Could not load PptxGenJS (CDN unreachable, no local cache).<br>"
                        "Download <b>pptxgen.bundled.js</b> from "
                        "https://cdn.jsdelivr.net/npm/pptxgenjs@3.12.0/dist/pptxgen.bundled.js "
                        "and place it in the JV-Analysis folder on the server, then retry."
                        "</div>"
                    )
                )
            return

        js_code = f"""
(async function() {{
    const payload  = {payload_json};
    const jvFbId   = '{jv_fb_id}';
    const boxFbId  = '{box_fb_id}';
    const statusEl = document.getElementById('jv-pptx-status');
    function setStatus(msg, isError) {{
        if (!statusEl) return;
        statusEl.style.color = isError ? '#b00020' : '#1f2937';
        statusEl.textContent = msg;
    }}

    async function capturePlot(idx) {{
        if (idx < 0) return null;
        const divs = Array.from(document.querySelectorAll('.js-plotly-plot'));
        if (idx >= divs.length) return null;
        const gd = divs[idx];
        try {{
            try {{ Plotly.Plots.resize(gd); }} catch(_) {{}}
            const rect = gd.getBoundingClientRect();
            const w    = rect.width  > 10 ? rect.width  : 900;
            const h    = rect.height > 10 ? rect.height : 550;
            const uri  = await Plotly.toImage(gd, {{ format: 'png', width: w, height: h, scale: 6 }});
            const pfx  = 'data:image/png;base64,';
            return uri.startsWith(pfx) ? uri.slice(pfx.length) : null;
        }} catch (e) {{
            console.warn('capturePlot failed for index', idx, e);
            return null;
        }}
    }}

    function getAspect(b64) {{
        return new Promise(resolve => {{
            const img    = new Image();
            img.onload   = () => resolve(img.width / img.height);
            img.onerror  = () => resolve(900 / 550);
            img.src      = 'data:image/png;base64,' + b64;
        }});
    }}

    try {{
        const fbJv  = document.getElementById(jvFbId)?.value  || '';
        const fbBox = document.getElementById(boxFbId)?.value || '';

        setStatus('Capturing plot images from browser...');
        const jvB64  = (await capturePlot(payload.jv_idx))  || fbJv;
        const boxB64 = (await capturePlot(payload.box_idx)) || fbBox;

        const IMG_H = 3.45;
        const jvW   = +(  (jvB64  ? await getAspect(jvB64)  : 900 / 550) * IMG_H).toFixed(3);
        const boxW  = +((boxB64   ? await getAspect(boxB64) : 900 / 550) * IMG_H).toFixed(3);

        setStatus('Building PowerPoint slide...');

        const NAVY   = '1F3964';
        const TEAL   = '1B6B5E';
        const TMID   = 'D5EAE6';
        const TLIGHT = 'EBF4F2';
        const GRAY   = '333333';
        const WHITE  = 'FFFFFF';

        const pres = new PptxGenJS();
        pres.defineLayout({{ name: 'WIDE', width: 13.333, height: 7.5 }});
        pres.layout = 'WIDE';
        const slide = pres.addSlide();

        slide.addText('Process name', {{
            x: 0.28, y: 0.10, w: 12.77, h: 0.70,
            fontSize: 28, bold: true, color: NAVY, fontFace: 'Calibri'
        }});
        slide.addText('Stack:  ...', {{
            x: 0.28, y: 0.83, w: 12.77, h: 0.40,
            fontSize: 14, color: GRAY, fontFace: 'Calibri'
        }});

        if (jvB64)  slide.addImage({{ data: 'data:image/png;base64,' + jvB64,
                                      x: 0.28, y: 1.32, w: jvW,  h: IMG_H }});
        if (boxB64) slide.addImage({{ data: 'data:image/png;base64,' + boxB64,
                                      x: 6.80, y: 1.32, w: boxW, h: IMG_H }});

        function hdrCell(txt) {{
            return {{ text: txt, options: {{ fill: {{ color: TEAL }}, color: WHITE,
                     bold: true, align: 'center', valign: 'middle' }} }};
        }}
        function dataCell(txt, fill) {{
            return {{ text: txt, options: {{ fill: {{ color: fill }}, color: GRAY,
                     align: 'center', valign: 'middle' }} }};
        }}
        const rows = [
            [hdrCell(''), hdrCell('Baseline'), hdrCell('Current batch')],
            [dataCell('V_OC', TMID),   dataCell('', TMID),   dataCell('', TMID)  ],
            [dataCell('J_SC', TLIGHT), dataCell('', TLIGHT), dataCell('', TLIGHT)],
            [dataCell('FF',   TMID),   dataCell('', TMID),   dataCell('', TMID)  ],
            [dataCell('PCE',  TLIGHT), dataCell('', TLIGHT), dataCell('', TLIGHT)],
        ];
        slide.addTable(rows, {{
            x: 0.28, y: 4.95, w: 6.0, h: 2.0,
            colW: [1.2, 2.4, 2.4],
            fontSize: 12, fontFace: 'Calibri',
            border: {{ type: 'none' }}
        }});
        slide.addText('Speculations:', {{
            x: 6.80, y: 4.95, w: 6.25, h: 2.0,
            fontSize: 16, color: TEAL, fontFace: 'Calibri', valign: 'top'
        }});
        slide.addText('Batch ID:   ' + payload.batch_str, {{
            x: 0.28, y: 7.20, w: 12.77, h: 0.28,
            fontSize: 11, bold: true, color: GRAY, fontFace: 'Calibri'
        }});

        setStatus('Saving...');
        const blob = await pres.write('blob');
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href     = url;
        a.download = payload.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        setStatus('Downloaded: ' + payload.filename);

    }} catch (err) {{
        setStatus('Error: ' + (err.message || String(err)), true);
        console.error('PPTX generation failed:', err);
    }}
}})();
"""

        with self.download_pptx_output:
            clear_output(wait=True)
            # HTML first so the status div + fallback textareas are in the DOM
            display(
                HTML(
                    f'<div id="jv-pptx-status" style="padding:6px 0; font-size:13px; color:#1f2937;">'
                    f"Capturing plots and generating PowerPoint...</div>"
                    f'<textarea id="{jv_fb_id}"  style="display:none;">{jv_fb}</textarea>'
                    f'<textarea id="{box_fb_id}" style="display:none;">{box_fb}</textarea>'
                )
            )
            # Inject library + generation code as a single script so PptxGenJS
            # is synchronously available when the async IIFE starts.
            display(Javascript(pptxgen_js + "\n" + js_code))

    def _on_theresa_download_clicked(self, b=None):
        """Download all individual JV curves (Forward + Reverse) as HTML plots in a ZIP."""
        import numpy as np
        import plotly.io as pio
        from plotly.subplots import make_subplots

        with self.download_theresa_output:
            clear_output(wait=True)
            print("⏳ Building individual JV curve plots...")

        data = self.data_manager.get_data()
        all_jv = data.get("jvc", pd.DataFrame())
        if all_jv.empty:
            with self.download_theresa_output:
                clear_output(wait=True)
                print("❌ No JV data available. Please load a batch first.")
            return

        filtered_jv = data.get("filtered", pd.DataFrame())
        # Always use the full original curves so rejected-data groups have matching curves too
        curves_df = data.get("curves", pd.DataFrame())
        if curves_df is None or curves_df.empty:
            curves_df = data.get("filtered_curves", pd.DataFrame())

        if curves_df.empty:
            with self.download_theresa_output:
                clear_output(wait=True)
                print("❌ No curve data available.")
            return

        # Build a lookup of REJECTED group keys — those get the _filtered suffix
        junk_jv = data.get("junk", pd.DataFrame())
        key_cols_check = [
            c for c in ["sample", "px_number", "cycle_number"] if c in junk_jv.columns
        ]
        junk_keys: set = set()
        if not junk_jv.empty and key_cols_check:
            for _, jrow in junk_jv.drop_duplicates(subset=key_cols_check).iterrows():
                junk_keys.add(tuple(None if pd.isna(jrow[c]) else jrow[c] for c in key_cols_check))

        # Use light measurements only
        if "ilum" in all_jv.columns:
            light_jv = all_jv[all_jv["ilum"] != "Dark"].copy()
        else:
            light_jv = all_jv.copy()

        group_cols = [c for c in ["sample", "px_number", "cycle_number"] if c in light_jv.columns]

        zip_buf = io.BytesIO()
        plot_count = 0

        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for group_key, group_df in light_jv.groupby(group_cols, dropna=False):
                if not isinstance(group_key, tuple):
                    group_key = (group_key,)
                key_dict = dict(zip(group_cols, group_key))

                sample_val = key_dict.get("sample", "unknown")
                px_val = key_dict.get("px_number", None)
                cycle_val = key_dict.get("cycle_number", None)

                sample_clean = (
                    str(sample_val).split("/")[-1].split(".")[0] if sample_val else "unknown"
                )
                px_str = (
                    str(px_val)
                    if (px_val is not None and str(px_val).lower() not in ("nan", "none", ""))
                    else "px"
                )
                if cycle_val is not None and str(cycle_val).lower() not in ("nan", "none", ""):
                    try:
                        cycle_str = f"cycle{int(float(cycle_val))}"
                    except Exception:
                        cycle_str = "cycle"
                else:
                    cycle_str = "cycle"

                norm_key = tuple(
                    None if pd.isna(key_dict.get(c)) else key_dict.get(c) for c in key_cols_check
                )
                filtered_suffix = "_filtered" if norm_key in junk_keys else ""
                filename_base = f"{sample_clean}_{px_str}_{cycle_str}{filtered_suffix}"

                if "direction" in group_df.columns:
                    rev_df = group_df[group_df["direction"] == "Reverse"]
                    fwd_df = group_df[group_df["direction"] == "Forward"]
                else:
                    rev_df = group_df
                    fwd_df = pd.DataFrame()

                fig = self._build_theresa_jv_plot(
                    fwd_df,
                    rev_df,
                    curves_df,
                    sample_label=sample_clean,
                    px_str=px_str,
                    cycle_str=cycle_str,
                )

                if fig is None:
                    continue

                html_content = fig.to_html(include_plotlyjs="cdn", full_html=True)
                zf.writestr(f"{filename_base}.html", html_content)
                plot_count += 1

        if plot_count == 0:
            with self.download_theresa_output:
                clear_output(wait=True)
                print("❌ No plots could be created. Ensure curve data is loaded.")
            return

        zip_buf.seek(0)
        zip_b64 = base64.b64encode(zip_buf.read()).decode("utf-8")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"Theresa_JV_{timestamp}.zip"

        js_code = f"""
(function() {{
    var b64 = "{zip_b64}";
    var byteStr = atob(b64);
    var buf = new Uint8Array(byteStr.length);
    for (var i = 0; i < byteStr.length; i++) buf[i] = byteStr.charCodeAt(i);
    var blob = new Blob([buf], {{type: 'application/zip'}});
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = '{zip_name}';
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
}})();
"""
        with self.download_theresa_output:
            clear_output(wait=True)
            print(f"✅ Created {plot_count} plots. Download starting...")
            display(Javascript(js_code))

    def _build_theresa_jv_plot(
        self,
        fwd_df,
        rev_df,
        curves_df,
        batch_name="",
        sample_label="",
        px_str="px",
        cycle_str="cycle",
    ):
        """Build one JV plot (Theresa style): Reverse=blue dots, Forward=red crosses, with performance table."""
        import numpy as np
        from plotly.subplots import make_subplots

        def _extract_iv(jv_row_df, curves):
            """Return (voltage, current) arrays for the best-PCE row in jv_row_df."""
            if jv_row_df.empty or curves.empty:
                return None, None
            row = (
                jv_row_df.sort_values("PCE(%)").iloc[-1]
                if "PCE(%)" in jv_row_df.columns
                else jv_row_df.iloc[0]
            )
            mask = pd.Series([True] * len(curves), index=curves.index)
            for col in ["sample", "direction"]:
                if col in curves.columns and col in row.index and pd.notna(row[col]):
                    mask &= curves[col] == row[col]
            for col in ["cell", "px_number"]:
                if col in curves.columns and col in row.index:
                    if pd.notna(row[col]):
                        mask &= curves[col] == row[col]
                    else:
                        mask &= curves[col].isna()
            if "cycle_number" in curves.columns and "cycle_number" in row.index:
                if pd.notna(row["cycle_number"]):
                    mask &= curves["cycle_number"] == row["cycle_number"]
                else:
                    mask &= curves["cycle_number"].isna()
            matched = curves[mask]
            v_rows = matched[matched["variable"] == "Voltage (V)"]
            j_rows = matched[matched["variable"] == "Current Density(mA/cm2)"]
            if v_rows.empty or j_rows.empty:
                return None, None
            numeric_cols = sorted([c for c in v_rows.columns if isinstance(c, int)])
            if not numeric_cols:
                return None, None
            v = v_rows.iloc[0][numeric_cols].values.astype(float)
            j = j_rows.iloc[0][numeric_cols].values.astype(float)
            valid = ~(np.isnan(v) | np.isnan(j))
            v, j = v[valid], j[valid]
            return (v, j) if len(v) > 0 else (None, None)

        def _get_params(df):
            if df.empty:
                return dict(pce=float("nan"), ff=float("nan"), jsc=float("nan"), voc=float("nan"))
            row = df.sort_values("PCE(%)").iloc[-1] if "PCE(%)" in df.columns else df.iloc[0]

            def _v(col):
                return row[col] if col in row.index else float("nan")

            return {
                "pce": _v("PCE(%)"),
                "ff": _v("FF(%)"),
                "jsc": _v("Jsc(mA/cm2)"),
                "voc": _v("Voc(V)"),
            }

        def _fmt(val, dec=2):
            try:
                f = float(val)
                return "N/A" if f != f else f"{f:.{dec}f}"
            except Exception:
                return "N/A"

        rev_v, rev_j = _extract_iv(rev_df, curves_df)
        fwd_v, fwd_j = _extract_iv(fwd_df, curves_df)

        if rev_v is None and fwd_v is None:
            return None

        rev_p = _get_params(rev_df)
        fwd_p = _get_params(fwd_df)

        rev_jsc_abs = abs(float(rev_p["jsc"])) if pd.notna(rev_p["jsc"]) else float("nan")
        fwd_jsc_abs = abs(float(fwd_p["jsc"])) if pd.notna(fwd_p["jsc"]) else float("nan")

        fig = make_subplots(
            rows=1,
            cols=2,
            column_widths=[0.68, 0.32],
            specs=[[{"type": "scatter"}, {"type": "table"}]],
            horizontal_spacing=0.04,
        )

        if rev_v is not None:
            fig.add_trace(
                go.Scatter(
                    x=rev_v,
                    y=rev_j,
                    mode="lines+markers",
                    marker=dict(symbol="circle", size=5, color="#1f77b4"),
                    line=dict(color="#1f77b4", width=2),
                    name="Reverse",
                    showlegend=True,
                ),
                row=1,
                col=1,
            )

        if fwd_v is not None:
            fig.add_trace(
                go.Scatter(
                    x=fwd_v,
                    y=fwd_j,
                    mode="lines+markers",
                    marker=dict(symbol="x", size=7, color="red"),
                    line=dict(color="red", width=2),
                    name="Forward",
                    showlegend=True,
                ),
                row=1,
                col=1,
            )

        try:
            rev_pce_f, fwd_pce_f = float(rev_p["pce"]), float(fwd_p["pce"])
            if pd.notna(rev_p["pce"]) and pd.notna(fwd_p["pce"]) and rev_pce_f != 0:
                hysteresis_str = _fmt((rev_pce_f - fwd_pce_f) / rev_pce_f, 3)
            else:
                hysteresis_str = "N/A"
        except Exception:
            hysteresis_str = "N/A"

        fig.add_trace(
            go.Table(
                header=dict(
                    values=["", "PCE (%)", "FF (%)", "Jsc (mA/cm²)", "Voc (V)"],
                    fill_color="#1f3964",
                    font=dict(color="white", size=11),
                    align="center",
                    height=28,
                ),
                cells=dict(
                    values=[
                        ["Reverse", "Forward", "Hysterese"],
                        [_fmt(rev_p["pce"]), _fmt(fwd_p["pce"]), hysteresis_str],
                        [_fmt(rev_p["ff"]), _fmt(fwd_p["ff"]), ""],
                        [_fmt(rev_jsc_abs), _fmt(fwd_jsc_abs), ""],
                        [_fmt(rev_p["voc"], 3), _fmt(fwd_p["voc"], 3), ""],
                    ],
                    fill_color=[["#d5eae6", "#ebf4f2", "#f0f0f0"]],
                    font=dict(size=11),
                    align="center",
                    height=26,
                ),
            ),
            row=1,
            col=2,
        )

        title_parts = [p for p in [sample_label, px_str, cycle_str] if p]
        title_text = " | ".join(title_parts)

        fig.add_shape(
            type="line",
            x0=-0.2,
            y0=0,
            x1=2.0,
            y1=0,
            line=dict(color="gray", width=1.5),
            row=1,
            col=1,
        )
        fig.add_shape(
            type="line", x0=0, y0=-30, x1=0, y1=30, line=dict(color="gray", width=1.5), row=1, col=1
        )

        fig.update_layout(
            title=dict(text=title_text, font=dict(size=13), x=0.0, xanchor="left"),
            template="plotly_white",
            width=1100,
            height=520,
            legend=dict(
                x=0.02,
                y=0.04,
                xanchor="left",
                yanchor="bottom",
                bgcolor="rgba(255,255,255,0.85)",
                bordercolor="black",
                borderwidth=1,
                font=dict(size=11),
            ),
            margin=dict(l=65, r=15, t=65, b=60),
        )
        fig.update_xaxes(
            title_text="Voltage [V]",
            showgrid=True,
            gridwidth=1,
            gridcolor="lightgray",
            row=1,
            col=1,
        )
        fig.update_yaxes(
            title_text="Current Density [mA/cm²]",
            showgrid=True,
            gridwidth=1,
            gridcolor="lightgray",
            row=1,
            col=1,
        )
        return fig

    def _build_download_table_assets(self):
        """Build summary table assets to include in the combined download ZIP."""
        summary_df = self._build_variation_summary_df()
        if summary_df.empty:
            return []

        assets = []

        csv_bytes = summary_df.to_csv(index=False).encode("utf-8")
        assets.append({"path": "table/jv_variation_summary.csv", "bytes": csv_bytes})

        png_bytes = self._render_summary_table_image_bytes(summary_df, image_format="png")
        if png_bytes:
            assets.append({"path": "table/jv_variation_summary.png", "bytes": png_bytes})

        pdf_bytes = self._render_summary_table_image_bytes(summary_df, image_format="pdf")
        if pdf_bytes:
            assets.append({"path": "table/jv_variation_summary.pdf", "bytes": pdf_bytes})

        # ADD: Generate detailed pixel-level export
        try:
            from utils import generate_detailed_export_excel

            # Get filtered and omitted data from data_manager
            filtered_data = self.data_manager.get_filtered_data()
            omitted_data = self.data_manager.get_omitted_data()

            # Export detailed data
            export_df = self.data_manager.export_detailed_pixel_data(
                filtered_data=filtered_data, omitted_data=omitted_data, verbose=False
            )

            if not export_df.empty:
                # Use the same variation order as the "Reorder Variables for
                # Boxplots" widget, so the xlsx export and the app's own plots
                # list variations in the same order.
                try:
                    variable_order = self.plot_ui.get_variable_order()
                except Exception:
                    variable_order = None

                # Generate Excel workbook
                detail_wb = generate_detailed_export_excel(
                    export_df, filtered_info=None, variable_order=variable_order
                )

                # Convert to bytes
                detail_bytes_io = io.BytesIO()
                detail_wb.save(detail_bytes_io)
                detail_bytes = detail_bytes_io.getvalue()

                assets.append({"path": "table/jv_detailed_pixel_data.xlsx", "bytes": detail_bytes})
        except Exception as e:
            print(f"Warning: Could not generate detailed export: {e}")
            import traceback

            traceback.print_exc()

        return assets

    def _on_download_zip_clicked(self, b=None):
        """Create a single ZIP with live SVG/PNG plots plus summary table files."""
        if not self.global_plot_data.get("figs"):
            with self.download_zip_output:
                clear_output(wait=True)
                print("No plots available. Create plots in 'Select Plots' first.")
            return

        plot_names = self.global_plot_data.get("names", [])
        if not plot_names:
            plot_names = [
                f"plot_{idx + 1}.html" for idx in range(len(self.global_plot_data.get("figs", [])))
            ]

        table_assets = self._build_download_table_assets()

        js_table_assets = []
        asset_blob_fields = []
        for idx, asset in enumerate(table_assets):
            asset_id = f"jv-table-asset-{idx}"
            asset_b64 = base64.b64encode(asset["bytes"]).decode("ascii")
            js_table_assets.append({"path": asset["path"], "field_id": asset_id})
            # Keep large base64 payload out of executable JS to avoid parser limits.
            asset_blob_fields.append(
                f"<textarea id='{asset_id}' style='display:none;'>{asset_b64}</textarea>"
            )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"JV_Download_{timestamp}.zip"

        payload = {"zip_name": zip_name, "plot_names": plot_names, "table_assets": js_table_assets}
        payload_json = json.dumps(payload)

        js_code = rf"""
        (async function() {{
            const payload = {payload_json};
            const statusEl = document.getElementById('jv-download-status');
            const progressEl = document.getElementById('jv-download-progress');
            const progressTextEl = document.getElementById('jv-download-progress-text');

            function setStatus(text, isError) {{
                if (!statusEl) return;
                statusEl.style.color = isError ? '#b00020' : '#1f2937';
                statusEl.textContent = text;
            }}

            function setProgress(current, total) {{
                if (!progressEl || !progressTextEl) return;
                const safeTotal = Math.max(1, total || 1);
                const safeCurrent = Math.max(0, Math.min(current || 0, safeTotal));
                progressEl.max = safeTotal;
                progressEl.value = safeCurrent;
                const pct = Math.round((safeCurrent / safeTotal) * 100);
                progressTextEl.textContent = `${{safeCurrent}}/${{safeTotal}} (${{pct}}%)`;
            }}

            function sanitizeName(name) {{
                return String(name || 'plot').replace(/[<>:\\"/\\\\|?*]/g, '_').replace(/\.+$/g, '').trim() || 'plot';
            }}

            function getBaseName(name, idx) {{
                const fallback = `plot_${{idx + 1}}`;
                if (!name) return fallback;
                const safe = sanitizeName(name);
                return safe.replace(/\\.[a-zA-Z0-9]+$/g, '') || fallback;
            }}

            async function ensureJsZip() {{
                if (window.JSZip) return;
                await new Promise((resolve, reject) => {{
                    const script = document.createElement('script');
                    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js';
                    script.onload = resolve;
                    script.onerror = () => reject(new Error('Could not load JSZip (network/CSP).'));
                    document.head.appendChild(script);
                }});
            }}

            function triggerBlobDownload(blob, filename) {{
                const canUseObjectUrl =
                    typeof window !== 'undefined' &&
                    window.URL &&
                    typeof window.URL.createObjectURL === 'function';

                if (canUseObjectUrl) {{
                    const objectUrl = window.URL.createObjectURL(blob);
                    const link = document.createElement('a');
                    link.href = objectUrl;
                    link.download = filename;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    setTimeout(function() {{
                        try {{
                            window.URL.revokeObjectURL(objectUrl);
                        }} catch (e) {{
                            console.warn('revokeObjectURL warning:', e);
                        }}
                    }}, 1000);
                    return Promise.resolve();
                }}

                // Fallback for restricted environments where createObjectURL is unavailable.
                return new Promise((resolve, reject) => {{
                    try {{
                        const reader = new FileReader();
                        reader.onloadend = function() {{
                            try {{
                                const link = document.createElement('a');
                                link.href = reader.result;
                                link.download = filename;
                                document.body.appendChild(link);
                                link.click();
                                document.body.removeChild(link);
                                resolve();
                            }} catch (err) {{
                                reject(err);
                            }}
                        }};
                        reader.onerror = function() {{
                            reject(new Error('FileReader fallback failed.'));
                        }};
                        reader.readAsDataURL(blob);
                    }} catch (err) {{
                        reject(err);
                    }}
                }});
            }}

            function getImageDimensions(gd) {{
                if (!gd) return {{ width: 1200, height: 800 }};
                const fl = gd._fullLayout || {{}};
                const layoutWidth = Number(fl.width) || 0;
                const layoutHeight = Number(fl.height) || 0;
                const domWidth = Number(gd.clientWidth || gd.offsetWidth || 0);
                const domHeight = Number(gd.clientHeight || gd.offsetHeight || 0);
                const width = Math.max(layoutWidth, domWidth, 1200);
                const height = Math.max(layoutHeight, domHeight, 800);
                return {{ width, height }};
            }}

            async function toImageWithRetry(gd, opts, retries) {{
                let lastErr = null;
                for (let attempt = 1; attempt <= retries; attempt++) {{
                    try {{
                        return await Plotly.toImage(gd, opts);
                    }} catch (err) {{
                        lastErr = err;
                        await new Promise(resolve => setTimeout(resolve, 120 * attempt));
                    }}
                }}
                throw lastErr || new Error('toImage failed');
            }}

            try {{
                setStatus('Preparing ZIP export...', false);
                setProgress(0, 1);
                await ensureJsZip();

                const plotDivs = Array.from(document.querySelectorAll('div.js-plotly-plot[id^="plot_"]'));
                if (!plotDivs.length) {{
                    throw new Error('No rendered plots found. Please create plots first.');
                }}

                const zip = new JSZip();
                const svgFolder = zip.folder('svg');
                const pngFolder = zip.folder('png');
                const warnings = [];

                setProgress(0, plotDivs.length);

                for (let i = 0; i < plotDivs.length; i++) {{
                    const gd = plotDivs[i];
                    const baseName = getBaseName(payload.plot_names[i], i);

                    setStatus(`Capturing plot ${{i + 1}} / ${{plotDivs.length}} ...`, false);

                    try {{
                        if (!gd || !gd.data) {{
                            throw new Error('Plot container is not ready.');
                        }}

                        try {{
                            Plotly.Plots.resize(gd);
                        }} catch (resizeErr) {{
                            console.warn('Resize warning:', resizeErr);
                        }}

                        const dims = getImageDimensions(gd);

                        const svgUri = await toImageWithRetry(gd, {{
                            format: 'svg',
                            width: dims.width,
                            height: dims.height
                        }}, 3);

                        const svgBase64Prefix = 'data:image/svg+xml;base64,';
                        const svgPlainPrefix = 'data:image/svg+xml,';
                        let svgText = '';
                        if (svgUri.startsWith(svgBase64Prefix)) {{
                            svgText = atob(svgUri.slice(svgBase64Prefix.length));
                        }} else if (svgUri.startsWith(svgPlainPrefix)) {{
                            svgText = decodeURIComponent(svgUri.slice(svgPlainPrefix.length));
                        }} else {{
                            throw new Error('Unexpected SVG data URI format.');
                        }}
                        svgFolder.file(baseName + '.svg', svgText);

                        const pngUri = await toImageWithRetry(gd, {{
                            format: 'png',
                            width: dims.width,
                            height: dims.height,
                            scale: 6
                        }}, 3);

                        const pngPrefix = 'data:image/png;base64,';
                        if (!pngUri.startsWith(pngPrefix)) {{
                            throw new Error('Unexpected PNG data URI format.');
                        }}
                        pngFolder.file(baseName + '.png', pngUri.slice(pngPrefix.length), {{ base64: true }});
                    }} catch (plotErr) {{
                        warnings.push(`Plot ${{i + 1}} (${{baseName}}): ${{plotErr.message || plotErr}}`);
                        console.error('Plot export error:', plotErr);
                    }}

                    setProgress(i + 1, plotDivs.length);
                }}

                if (Array.isArray(payload.table_assets)) {{
                    for (const asset of payload.table_assets) {{
                        if (!asset || !asset.path || !asset.field_id) continue;
                        const field = document.getElementById(asset.field_id);
                        const b64 = field ? (field.value || '').replace(/\\s+/g, '') : '';
                        if (b64) {{
                            zip.file(asset.path, b64, {{ base64: true }});
                        }}
                    }}
                }}

                const exportedCount = plotDivs.length - warnings.length;
                if (exportedCount <= 0) {{
                    throw new Error('No plots could be exported. Check browser console for details.');
                }}

                if (warnings.length) {{
                    zip.file('table/export_warnings.txt', warnings.join('\\n'));
                }}

                setStatus('Generating ZIP file...', false);
                const blob = await zip.generateAsync({{ type: 'blob' }});
                await triggerBlobDownload(blob, payload.zip_name);

                if (warnings.length) {{
                    setStatus(`Download started: ${{payload.zip_name}} (${{exportedCount}} plots exported, ${{warnings.length}} skipped)`, false);
                }} else {{
                    setStatus(`Download started: ${{payload.zip_name}}`, false);
                }}
            }} catch (err) {{
                console.error(err);
                setStatus('Export failed: ' + (err && err.message ? err.message : err), true);
            }}
        }})();
        """

        # Voila often blocks auto-executed output JS. Use an explicit click action.
        # Keep onclick tiny and store the JS payload in a hidden textarea.
        js_code_text = js_code.replace("</textarea>", "<\\/textarea>")
        onclick_code = (
            "(function(){"
            "try{"
            "var src=document.getElementById('jv-export-js');"
            "if(!src){throw new Error('Export source not found.');}"
            "(0,eval)(src.value);"
            "}catch(e){"
            "console.error(e);"
            "var el=document.getElementById('jv-download-status');"
            "if(el){el.style.color='#b00020';el.textContent='Export failed: '+(e&&e.message?e.message:e);}"
            "}"
            "})();"
        )

        with self.download_zip_output:
            clear_output(wait=True)
            display(
                HTML(f"""
                <div id='jv-download-status' style='font-weight: 600; margin-bottom: 8px;'>Ready to start export.</div>
                <div style='display: flex; align-items: center; gap: 10px; margin-bottom: 10px;'>
                    <progress id='jv-download-progress' value='0' max='1' style='width: 280px; height: 14px;'></progress>
                    <span id='jv-download-progress-text' style='font-size: 12px; color: #4b5563;'>0/1 (0%)</span>
                </div>
                <textarea id='jv-export-js' style='display:none;'>{js_code_text}</textarea>
                {"".join(asset_blob_fields)}
                <button onclick="{onclick_code}"
                        style='background:#198754;color:white;border:none;border-radius:6px;padding:8px 14px;cursor:pointer;'>
                    Start ZIP Export
                </button>
            """)
            )

    def _create_matching_curves_from_filtered_jv(self, filtered_jv_data, original_curves_data):
        """Create curves data that exactly matches filtered JV data using sample_id"""

        if filtered_jv_data.empty:
            return pd.DataFrame()

        def _norm_text(value):
            if pd.isna(value):
                return None
            return str(value)

        def _norm_cycle(value):
            if pd.isna(value):
                return None
            try:
                return int(value)
            except Exception:
                return None

        filtered_combinations = set()
        for _, row in filtered_jv_data.iterrows():
            sample_key = row.get("sample_id", row.get("sample", None))
            combination = (
                _norm_text(sample_key),
                _norm_text(row.get("cell", None)),
                _norm_text(row.get("direction", None)),
                _norm_text(row.get("ilum", None)),
                _norm_text(row.get("px_number", None)),
                _norm_cycle(row.get("cycle_number", None)),
            )
            filtered_combinations.add(combination)

        # Filter curves data to match exactly
        def should_include_curve(curve_row):
            if "sample_id" not in curve_row:
                return False
            combination = (
                _norm_text(curve_row.get("sample_id", curve_row.get("sample", None))),
                _norm_text(curve_row.get("cell", None)),
                _norm_text(curve_row.get("direction", None)),
                _norm_text(curve_row.get("ilum", None)),
                _norm_text(curve_row.get("px_number", None)),
                _norm_cycle(curve_row.get("cycle_number", None)),
            )
            return combination in filtered_combinations

        matching_curves = original_curves_data[
            original_curves_data.apply(should_include_curve, axis=1)
        ].copy()

        return matching_curves

    def _create_filtered_curves_data(self, filtered_jv_data, original_curves_data):
        """Create curves data that matches filtered JV data with debugging"""

        # Get sample-cell combinations from filtered JV data
        filtered_combinations = set()
        for _, row in filtered_jv_data.iterrows():
            filtered_combinations.add((row["sample"], row["cell"]))

        # Try exact matching first
        def should_include_curve(row):
            return (row["sample"], row["cell"]) in filtered_combinations

        filtered_curves = original_curves_data[
            original_curves_data.apply(should_include_curve, axis=1)
        ].copy()

        print(f"DEBUG: Exact matching found {len(filtered_curves)} curve records")

        # If exact matching fails, try alternative sample name matching
        if len(filtered_curves) == 0:
            print("DEBUG: Trying alternative sample name matching...")

            # Extract clean sample names from both datasets for comparison
            jv_clean_samples = set()
            for _, row in filtered_jv_data.iterrows():
                # Extract the core sample name (like C-11)
                clean_name = row["sample"].split("_")[-1] if "_" in row["sample"] else row["sample"]
                jv_clean_samples.add((clean_name, row["cell"]))

            def should_include_curve_alt(row):
                curve_clean = (
                    row["sample"].split("_")[-1] if "_" in row["sample"] else row["sample"]
                )
                return (curve_clean, row["cell"]) in jv_clean_samples

            filtered_curves = original_curves_data[
                original_curves_data.apply(should_include_curve_alt, axis=1)
            ].copy()

            print(f"DEBUG: Alternative matching found {len(filtered_curves)} curve records")

        # Always return a DataFrame, even if empty
        if filtered_curves is None or len(filtered_curves) == 0:
            print("DEBUG: No matching curves found, returning empty DataFrame")
            return original_curves_data.iloc[
                0:0
            ].copy()  # Return empty DataFrame with same structure

        return filtered_curves

    def _on_save_plots(self, b):
        """Handle plots saving"""
        if not self.global_plot_data.get("figs"):
            with self.save_ui.download_output:
                print("No plots have been created yet.")
            return

        try:
            zip_content = self.save_ui.create_plots_zip(
                self.global_plot_data["figs"], self.global_plot_data["names"]
            )

            b64 = base64.b64encode(zip_content).decode()
            js_code = f"""
            var link = document.createElement('a');
            link.href = 'data:application/zip;base64,{b64}';
            link.download = 'plots.zip';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            """

            with self.save_ui.download_output:
                display(
                    widgets.HTML(
                        f'<button onclick="{js_code}">Click to download all plots</button>'
                    )
                )
                print(
                    "Download initiated. If the download doesn't start automatically, click the button above."
                )

        except Exception as e:
            ErrorHandler.log_error("saving plots", e, self.save_ui.download_output)

    def _on_save_data(self, b):
        """Handle data saving"""
        if not self.global_plot_data.get("workbook"):
            with self.save_ui.download_output:
                print("No data has been processed yet.")
            return

        try:
            excel_buffer = io.BytesIO()
            self.global_plot_data["workbook"].save(excel_buffer)
            excel_buffer.seek(0)

            b64 = base64.b64encode(excel_buffer.getvalue()).decode()
            js_code = f"""
            var link = document.createElement('a');
            link.href = 'data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}';
            link.download = 'collected_data.xlsx';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            """

            with self.save_ui.download_output:
                display(
                    widgets.HTML(f'<button onclick="{js_code}">Click to download data</button>')
                )
                print(
                    "Download initiated. If the download doesn't start automatically, click the button above."
                )

        except Exception as e:
            ErrorHandler.log_error("saving data", e, self.save_ui.download_output)

    def _on_save_all(self, b):
        """Handle saving all files"""
        if not self.global_plot_data.get("figs") or not self.global_plot_data.get("workbook"):
            with self.save_ui.download_output:
                print("No plots or data have been created yet.")
            return

        try:
            # Create combined zip
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                # Add plots
                for fig, name in zip(self.global_plot_data["figs"], self.global_plot_data["names"]):
                    try:
                        html_str = fig.to_html(include_plotlyjs="cdn")
                        zip_file.writestr(name, html_str)
                    except Exception as e:
                        print(f"Error saving {name}: {e}")

                # Add Excel file
                excel_buffer = io.BytesIO()
                self.global_plot_data["workbook"].save(excel_buffer)
                excel_buffer.seek(0)
                zip_file.writestr("collected_data.xlsx", excel_buffer.getvalue())

            zip_buffer.seek(0)
            b64 = base64.b64encode(zip_buffer.getvalue()).decode()
            js_code = f"""
            var link = document.createElement('a');
            link.href = 'data:application/zip;base64,{b64}';
            link.download = 'results.zip';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            """

            with self.save_ui.download_output:
                display(
                    widgets.HTML(
                        f'<button onclick="{js_code}">Click to download all files</button>'
                    )
                )
                print(
                    "Download initiated. If the download doesn't start automatically, click the button above."
                )

        except Exception as e:
            ErrorHandler.log_error("saving all files", e, self.save_ui.download_output)

    def _enable_tab(self, tab_index):
        """Enable a specific tab (placeholder for future styling)"""
        pass

    def get_dashboard(self):
        """Get the main dashboard widget"""
        app_layout = widgets.Layout(max_width="1200px", margin="0 auto", padding="15px")

        # Create header with title and info buttons
        header = widgets.HBox(
            [
                widgets.HTML("<h1 style='margin: 0; flex-grow: 1;'>JV Analysis Dashboard</h1>"),
                self.info_ui.get_widget(),
            ],
            layout=widgets.Layout(
                justify_content="space-between", align_items="flex-start", margin="0 0 20px 0"
            ),
        )

        return widgets.VBox(
            [
                header,  # Header with What's New and Manual buttons
                self.tabs,
            ],
            layout=app_layout,
        )

    def get_current_color_scheme(self):
        """Get currently selected color scheme"""
        if hasattr(self, "color_selector"):
            return self.color_selector.get_colors()
        else:
            # Default colors if no selector
            return [
                "rgba(93, 164, 214, 0.7)",
                "rgba(255, 144, 14, 0.7)",
                "rgba(44, 160, 101, 0.7)",
                "rgba(255, 65, 54, 0.7)",
                "rgba(207, 114, 255, 0.7)",
                "rgba(127, 96, 0, 0.7)",
                "rgba(255, 140, 184, 0.7)",
                "rgba(79, 90, 117, 0.7)",
            ]
