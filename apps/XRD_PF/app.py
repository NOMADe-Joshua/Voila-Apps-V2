"""
XRD Analysis Application Controller
Loads XRD diffractograms from the NOMAD API and provides interactive peak analysis.
"""

import base64
import io
import os
import traceback
import zipfile
from datetime import datetime

import ipywidgets as widgets
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from fitting_engine import FittingEngine
from IPython.display import Javascript, clear_output, display

from perotf_utils.auth_ui import AuthenticationUI
from perotf_utils.batch_selection import create_batch_selection
from perotf_utils.config import API_ENDPOINT, ENTRY_TYPES, URL_BASE

# ── Auth manager ─────────────────────────────────────────────────────────────


class SimpleAuthManager:
    """Auth manager – mirrors the JV-Analysis pattern."""

    def __init__(self, base_url: str, api_endpoint: str):
        self.base_url = base_url
        self.api_endpoint = api_endpoint
        self.url = f"{base_url}{api_endpoint}"
        self.current_token = None
        self.current_user_info = None
        self.api_client = self  # compat shim expected by AuthenticationUI
        self.status_callback = None

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _update_status(self, message, color=None):
        if self.status_callback:
            self.status_callback(message, color)

    def authenticate_with_credentials(self, username: str, password: str) -> str:
        if not username or not password:
            raise ValueError("Username and password are required.")
        resp = requests.get(
            f"{self.url}/auth/token",
            params=dict(username=username, password=password),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if "access_token" not in data:
            raise ValueError("Server did not return an access_token.")
        self.current_token = data["access_token"]
        return self.current_token

    def authenticate_with_token(self, token=None) -> str:
        if token is None:
            token = os.environ.get("NOMAD_CLIENT_ACCESS_TOKEN", "")
        self.current_token = token
        return self.current_token

    def verify_token(self) -> dict:
        if not self.current_token:
            raise ValueError("Not authenticated.")
        resp = requests.get(
            f"{self.url}/users/me",
            headers={"Authorization": f"Bearer {self.current_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        self.current_user_info = resp.json()
        return self.current_user_info

    def is_authenticated(self) -> bool:
        return self.current_token is not None and self.current_user_info is not None

    def clear_authentication(self):
        self.current_token = None
        self.current_user_info = None

    def get_user_display_name(self) -> str:
        if not self.current_user_info:
            return "Unknown"
        return self.current_user_info.get("name", self.current_user_info.get("username", "Unknown"))


# ── XRD array extraction helper ──────────────────────────────────────────────


def _extract_xrd_arrays(archive_data: dict):
    """
    Robustly extract (two_theta, intensity) arrays from a NOMAD archive dict.
    Tries several common field-name patterns used in XRD entries (ENTRY_TYPES["xrd"]).
    Returns (None, None) if nothing recognisable is found.
    """
    _ANGLE_KEYS = [
        "two_theta",
        "two_theta_array",
        "angle",
        "angles",
        "2theta",
        "x_values",
        "q_values",
        "two_theta_values",
    ]
    _INTENSITY_KEYS = [
        "intensity",
        "intensity_array",
        "counts",
        "i_values",
        "intensities",
        "y_values",
        "yobs",
        "count",
    ]

    def _to_1d(val):
        if val is None:
            return None
        try:
            arr = np.asarray(val, dtype=float).ravel()
            return arr if arr.size > 1 else None
        except Exception:
            return None

    def _search(d: dict):
        if not isinstance(d, dict):
            return None, None
        for ak in _ANGLE_KEYS:
            for ik in _INTENSITY_KEYS:
                a = _to_1d(d.get(ak))
                i = _to_1d(d.get(ik))
                if a is not None and i is not None and len(a) == len(i):
                    return a, i
        return None, None

    # 1. Top-level flat fields
    a, i = _search(archive_data)
    if a is not None:
        return a, i

    # 2. Nested under 'data'
    a, i = _search(archive_data.get("data", {}))
    if a is not None:
        return a, i

    # 3. Nested under 'diffractogram' (list or dict)
    diffr = archive_data.get("diffractogram")
    if isinstance(diffr, list) and diffr:
        diffr = diffr[0]
    if isinstance(diffr, dict):
        a, i = _search(diffr)
        if a is not None:
            return a, i

    return None, None


# ── Colour helpers ────────────────────────────────────────────────────────────

_COMPONENT_COLORS = [
    "rgba(44,160,44,0.75)",
    "rgba(214,39,40,0.75)",
    "rgba(148,103,189,0.75)",
    "rgba(140,86,75,0.75)",
    "rgba(227,119,194,0.75)",
    "rgba(127,127,127,0.75)",
    "rgba(188,189,34,0.75)",
    "rgba(23,190,207,0.75)",
]

_COLOR_MAP = {
    "Plotly": px.colors.qualitative.Plotly,
    "Set1": px.colors.qualitative.Set1,
    "Set2": px.colors.qualitative.Set2,
    "Set3": px.colors.qualitative.Set3,
    "Pastel": px.colors.qualitative.Pastel,
    "Dark2": px.colors.qualitative.Dark2,
    "Alphabet": px.colors.qualitative.Alphabet,
    "Viridis": px.colors.sequential.Viridis[::-1],
    "Plasma": px.colors.sequential.Plasma[::-1],
}


# ── Main application ──────────────────────────────────────────────────────────


class XRDAnalysisApp:
    """
    Interactive XRD analysis app for Voilà / JupyterLab.

    Tab 0  Login & Upload   – authenticate and load XRD data from NOMAD
    Tab 1  XRD Patterns     – overlay / compare diffractograms
    Tab 2  Peak Analysis    – detect peaks and fit Gaussian profiles
    Tab 3  Export           – download plot (HTML) or data (ZIP/CSV)
    """

    BASE_URL = URL_BASE
    API_ENDPOINT = API_ENDPOINT
    ITO_REFERENCE_2THETA = 30.562  # default 2θ calibration target (ITO substrate peak)

    # ── init ─────────────────────────────────────────────────────────────────

    def __init__(self):
        self.auth_manager = SimpleAuthManager(self.BASE_URL, self.API_ENDPOINT)
        self.fitting_engine = FittingEngine()

        self.loaded_patterns: dict = {}  # label → {two_theta, intensity, …}
        self.selected_batch_ids: list = []
        self._last_overlay_fig = None
        self._detected_peaks: list = []
        self._peak_label = ""
        self._peak_x = None
        self._peak_y_norm = None
        self._last_fit_result = None  # most recent lmfit ModelResult, used to seed 2θ calibration

        # Batch selection / XRD-availability search state
        self._batch_selector = None  # the inner SelectMultiple from create_batch_selection
        self._all_batch_options = []  # unfiltered batch id list
        self._xrd_search_status = None

        # Pattern selector keeps (display_label, key) tuples; this list holds the plain keys
        self._pattern_option_values: list = []

        self._build_ui()
        self._setup_callbacks()
        self._auto_authenticate()

    # ── widget construction ───────────────────────────────────────────────────

    def _build_ui(self):
        # -- auth (reuse parent component) ------------------------------------
        self.auth_ui = AuthenticationUI(self.auth_manager)

        # -- status / batch loading -------------------------------------------
        self.load_status = widgets.Output(
            layout=widgets.Layout(
                border="1px solid #e0e0e0",
                padding="10px",
                min_height="50px",
                margin="8px 0",
            )
        )
        self.batch_container = widgets.Output()

        # ── Tab 1 : XRD Patterns ─────────────────────────────────────────────
        self.pattern_selector = widgets.SelectMultiple(
            options=[],
            description="Patterns:",
            layout=widgets.Layout(width="420px", height="220px"),
            style={"description_width": "72px"},
        )
        self.select_all_btn = widgets.Button(
            description="Select All",
            layout=widgets.Layout(width="110px"),
        )
        self.deselect_all_btn = widgets.Button(
            description="Deselect All",
            layout=widgets.Layout(width="110px"),
        )

        self.normalize_cb = widgets.Checkbox(
            value=True,
            description="Normalize (0–1)",
            indent=False,
            layout=widgets.Layout(width="170px"),
        )
        self.offset_cb = widgets.Checkbox(
            value=True,
            description="Vertical offset",
            indent=False,
            layout=widgets.Layout(width="160px"),
        )
        self.offset_step = widgets.BoundedFloatText(
            value=0.15,
            min=0.0,
            max=10.0,
            step=0.05,
            description="Step:",
            layout=widgets.Layout(width="140px"),
            style={"description_width": "44px"},
        )
        self.log_scale_cb = widgets.Checkbox(
            value=False,
            description="Log intensity",
            indent=False,
            layout=widgets.Layout(width="150px"),
        )
        self.color_dropdown = widgets.Dropdown(
            options=list(_COLOR_MAP.keys()),
            value="Plotly",
            description="Colors:",
            layout=widgets.Layout(width="220px"),
            style={"description_width": "60px"},
        )
        self.display_name_dropdown = widgets.Dropdown(
            options=["Full name", "Variation", "Sample name"],
            value="Full name",
            description="Legend:",
            layout=widgets.Layout(width="220px"),
            style={"description_width": "60px"},
        )
        self.line_width_input = widgets.BoundedFloatText(
            value=1.5,
            min=0.5,
            max=6.0,
            step=0.5,
            description="Line width:",
            layout=widgets.Layout(width="185px"),
            style={"description_width": "90px"},
        )
        self.plot_btn = widgets.Button(
            description="📊  Plot Selected",
            button_style="success",
            layout=widgets.Layout(width="170px", height="38px"),
        )
        self.plot_output = widgets.Output(
            layout=widgets.Layout(
                border="1px solid #e0e0e0",
                padding="8px",
                margin="8px 0",
            )
        )

        # ── Tab 2 : Peak Analysis ─────────────────────────────────────────────
        self.ref_pattern_dropdown = widgets.Dropdown(
            options=[],
            description="Pattern:",
            layout=widgets.Layout(width="440px"),
            style={"description_width": "72px"},
        )
        self.peak_normalize_cb = widgets.Checkbox(
            value=True,
            description="Normalize (0–1)",
            indent=False,
            layout=widgets.Layout(width="160px"),
        )
        self.prominence_input = widgets.BoundedFloatText(
            value=0.05,
            min=0.001,
            max=1.0,
            step=0.005,
            description="Prominence:",
            layout=widgets.Layout(width="190px"),
            style={"description_width": "100px"},
        )
        self.distance_input = widgets.BoundedIntText(
            value=5,
            min=1,
            max=500,
            description="Distance:",
            layout=widgets.Layout(width="165px"),
            style={"description_width": "80px"},
        )
        self.bg_model_dropdown = widgets.Dropdown(
            options=["None", "Linear", "Polynomial"],
            value="Linear",
            description="Background:",
            layout=widgets.Layout(width="215px"),
            style={"description_width": "90px"},
        )
        self.poly_degree_input = widgets.BoundedIntText(
            value=2,
            min=0,
            max=15,
            description="Degree:",
            layout=widgets.Layout(width="140px", display="none"),
            style={"description_width": "55px"},
        )
        self.detect_btn = widgets.Button(
            description="🔍  Detect Peaks",
            button_style="primary",
            layout=widgets.Layout(width="155px", height="38px"),
        )
        self.fit_btn = widgets.Button(
            description="📈  Fit Peaks",
            button_style="warning",
            layout=widgets.Layout(width="145px", height="38px"),
            disabled=True,
        )
        self.peak_plot_output = widgets.Output(
            layout=widgets.Layout(
                border="1px solid #e0e0e0",
                padding="8px",
                margin="8px 0",
            )
        )
        self.peak_table_output = widgets.Output(
            layout=widgets.Layout(
                border="1px solid #e0e0e0",
                padding="8px",
                margin="8px 0",
                max_height="270px",
                overflow_y="auto",
            )
        )

        # ── 2θ calibration (e.g. align to a known ITO reference peak) ─────────
        self.calib_peak_dropdown = widgets.Dropdown(
            options=[],
            description="Peak:",
            layout=widgets.Layout(width="260px"),
            style={"description_width": "50px"},
        )
        self.calib_target_input = widgets.BoundedFloatText(
            value=0.0,
            min=-180.0,
            max=180.0,
            step=0.001,
            description="Target 2θ (°):",
            layout=widgets.Layout(width="190px"),
            style={"description_width": "100px"},
        )
        self.calib_apply_btn = widgets.Button(
            description="🎯  Apply Shift",
            button_style="info",
            layout=widgets.Layout(width="150px", height="34px"),
        )
        self.calib_status = widgets.Output(layout=widgets.Layout(margin="4px 0"))

        # ── Tab 3 : Export ────────────────────────────────────────────────────
        self.export_html_btn = widgets.Button(
            description="💾  Download Plot (HTML)",
            button_style="info",
            layout=widgets.Layout(width="215px"),
        )
        self.export_csv_btn = widgets.Button(
            description="📄  Download Data (ZIP)",
            button_style="info",
            layout=widgets.Layout(width="195px"),
        )
        self.export_output = widgets.Output(
            layout=widgets.Layout(
                border="1px solid #e0e0e0",
                padding="8px",
                margin="8px 0",
            )
        )

        self.tabs = widgets.Tab()
        self._assemble_tabs()

    # ── tab assembly ──────────────────────────────────────────────────────────

    def _assemble_tabs(self):
        # ── Tab 0 ─────────────────────────────────────────────────────────────
        tab0 = widgets.VBox(
            [
                self.auth_ui.get_widget(),
                widgets.HTML("<h3 style='margin-top:20px;'>📁 Select Uploads</h3>"),
                widgets.HTML(
                    "<p style='color:#555; margin:0 0 8px 0;'>"
                    "Select one or more batches that contain XRD measurements "
                    f"(<code>{ENTRY_TYPES['xrd']}</code>). "
                    "Click <b>Load</b> in the batch widget to fetch the data.</p>"
                ),
                self.batch_container,
                self.load_status,
            ]
        )

        # ── Tab 1 ─────────────────────────────────────────────────────────────
        selector_box = widgets.VBox(
            [
                widgets.HTML("<b>Patterns</b>"),
                self.pattern_selector,
                widgets.HBox([self.select_all_btn, self.deselect_all_btn]),
            ],
            layout=widgets.Layout(margin="0 24px 0 0"),
        )
        options_box = widgets.VBox(
            [
                widgets.HTML("<b>Plot options</b>"),
                self.normalize_cb,
                widgets.HBox([self.offset_cb, self.offset_step]),
                self.log_scale_cb,
                self.color_dropdown,
                self.display_name_dropdown,
                self.line_width_input,
                widgets.HTML("&nbsp;"),
                self.plot_btn,
            ]
        )
        tab1 = widgets.VBox(
            [
                widgets.HTML("<h3>XRD Diffractograms</h3>"),
                widgets.HBox([selector_box, options_box]),
                widgets.HTML("<hr style='margin:12px 0;'>"),
                self.plot_output,
            ]
        )

        # ── Tab 2 ─────────────────────────────────────────────────────────────
        tab2 = widgets.VBox(
            [
                widgets.HTML("<h3>Peak Analysis</h3>"),
                widgets.HTML(
                    "<p style='color:#555; margin:0 0 8px 0;'>"
                    "Select a single pattern, detect peaks, then optionally fit "
                    "Gaussian profiles to each peak.</p>"
                ),
                self.ref_pattern_dropdown,
                self.peak_normalize_cb,
                widgets.HTML("<hr style='margin:8px 0;'>"),
                widgets.HTML("<b>Detection parameters</b>"),
                widgets.HBox(
                    [
                        self.prominence_input,
                        self.distance_input,
                        self.bg_model_dropdown,
                        self.poly_degree_input,
                    ]
                ),
                widgets.HBox(
                    [self.detect_btn, self.fit_btn],
                    layout=widgets.Layout(margin="10px 0"),
                ),
                self.peak_plot_output,
                widgets.HTML("<b>Peak parameters</b>"),
                self.peak_table_output,
                widgets.HTML("<hr style='margin:8px 0;'>"),
                widgets.HTML("<b>2θ Calibration</b>"),
                widgets.HTML(
                    "<p style='color:#555; margin:0 0 8px 0;'>"
                    "Normalize your XRD data to a specific reference peak (typically the ITO substrate peak). "
                    "Check the reference: <a href='https://doi.org/10.1006/jssc.1997.7613' target='_blank'>10.1006/jssc.1997.7613</a>. "
                    "At 298K the highest intensity ITO peak is at 30.562°.</p>"
                ),
                widgets.HBox(
                    [
                        self.calib_peak_dropdown,
                        self.calib_target_input,
                        self.calib_apply_btn,
                    ]
                ),
                self.calib_status,
            ]
        )

        # ── Tab 3 ─────────────────────────────────────────────────────────────
        tab3 = widgets.VBox(
            [
                widgets.HTML("<h3>Export</h3>"),
                widgets.HTML(
                    "<p style='color:#555; margin:0 0 8px 0;'>"
                    "Download the current overlay plot as a self-contained HTML file, "
                    "or export all loaded patterns as CSV files bundled in a ZIP archive.</p>"
                ),
                widgets.HBox(
                    [self.export_html_btn, self.export_csv_btn],
                    layout=widgets.Layout(margin="8px 0"),
                ),
                self.export_output,
            ]
        )

        self.tabs.children = [tab0, tab1, tab2, tab3]
        for idx, title in enumerate(["Login & Upload", "XRD Patterns", "Peak Analysis", "Export"]):
            self.tabs.set_title(idx, title)

    # ── callbacks ─────────────────────────────────────────────────────────────

    def _setup_callbacks(self):
        self.auth_ui.set_success_callback(self._on_auth_success)
        self.select_all_btn.on_click(
            lambda _: setattr(self.pattern_selector, "value", tuple(self._pattern_option_values))
        )
        self.deselect_all_btn.on_click(lambda _: setattr(self.pattern_selector, "value", ()))
        self.plot_btn.on_click(self._on_plot)
        self.detect_btn.on_click(self._on_detect_peaks)
        self.fit_btn.on_click(self._on_fit_peaks)
        self.calib_apply_btn.on_click(self._on_apply_calibration)
        self.export_html_btn.on_click(self._on_export_html)
        self.export_csv_btn.on_click(self._on_export_csv)
        self.bg_model_dropdown.observe(self._on_bg_model_change, names="value")
        self.peak_normalize_cb.observe(self._on_peak_normalize_change, names="value")

    def _on_bg_model_change(self, change):
        """Show the polynomial-degree input only when it is relevant."""
        self.poly_degree_input.layout.display = "flex" if change["new"] == "Polynomial" else "none"

    def _on_peak_normalize_change(self, change):
        """Rescale the Prominence bound so it stays usable in both normalized and raw-counts mode."""
        if change["new"]:
            self.prominence_input.min = 0.001
            self.prominence_input.max = 1.0
            self.prominence_input.step = 0.005
            if self.prominence_input.value > 1.0:
                self.prominence_input.value = 0.05
            return

        ymax = 1.0
        label = self.ref_pattern_dropdown.value
        if label and label in self.loaded_patterns:
            y = self.loaded_patterns[label]["intensity"].astype(float)
            if y.size:
                ymax = float(y.max())
        self.prominence_input.max = max(ymax, 1.0)
        self.prominence_input.step = max(ymax * 0.005, 0.005)
        self.prominence_input.value = max(ymax * 0.05, 0.05)

    def _auto_authenticate(self):
        is_hub = bool(os.environ.get("JUPYTERHUB_USER"))
        if is_hub:
            self.auth_ui.auth_method_selector.value = "Token (from ENV)"
            self.auth_ui.local_auth_box.layout.display = "none"
        else:
            self.auth_ui.auth_method_selector.value = "Username/Password"
            self.auth_ui.local_auth_box.layout.display = "flex"
        self.auth_ui._on_auth_button_clicked(None)

    # ── auth / data loading ───────────────────────────────────────────────────

    def _on_auth_success(self):
        self.tabs.selected_index = 0
        self._init_batch_selection()

    def _init_batch_selection(self):
        with self.batch_container:
            clear_output(wait=True)
            if not self.auth_manager.is_authenticated():
                return
            try:
                widget = create_batch_selection(
                    self.auth_manager.url,
                    self.auth_manager.current_token,
                    self._load_xrd_from_selection,
                )
                # widget.children == (search_field, batch_ids_selector, load_batch_button)
                self._batch_selector = widget.children[1]
                self._all_batch_options = list(self._batch_selector.options)

                search_xrd_btn = widgets.Button(
                    description="🔬 Search for XRD",
                    button_style="info",
                    tooltip="Scan all listed batches and keep only those that contain XRD data",
                    layout=widgets.Layout(width="170px"),
                )
                search_xrd_btn.on_click(self._on_search_for_xrd)
                self._xrd_search_status = widgets.Output(layout=widgets.Layout(margin="4px 0"))

                display(
                    widgets.VBox(
                        [
                            widget,
                            widgets.HBox([search_xrd_btn], layout=widgets.Layout(margin="6px 0")),
                            self._xrd_search_status,
                        ]
                    )
                )
            except Exception as exc:
                print(f"⚠  Could not create batch selector: {exc}")

    def _on_search_for_xrd(self, button=None):
        """Filter the batch list down to batches that actually contain XRD data.

        Mirrors the proven approach used in MPPT_Analysis: reuse the existing
        get_ids_in_batch / get_all_xrd calls per batch instead of custom queries.
        """
        from perotf_utils.api_calls import get_all_xrd, get_ids_in_batch

        if (
            self._batch_selector is None
            or self._xrd_search_status is None
            or not self._all_batch_options
        ):
            return

        url = self.auth_manager.url
        token = self.auth_manager.current_token
        all_batch_ids = list(self._all_batch_options)
        total = len(all_batch_ids)

        if button is not None:
            button.disabled = True
            button.description = "🔄 Searching…"

        valid_batches = []
        for i, batch_id in enumerate(all_batch_ids):
            if i % 5 == 0 or i == total - 1:
                with self._xrd_search_status:
                    clear_output(wait=True)
                    print(f"🔍  Progress: {i + 1}/{total} — found {len(valid_batches)} so far")
                    print(f"   Currently testing: {batch_id}")
            try:
                sample_ids = get_ids_in_batch(url, token, [batch_id])
                if sample_ids and get_all_xrd(url, token, sample_ids):
                    valid_batches.append(batch_id)
            except Exception:
                continue

        self._batch_selector.options = valid_batches
        self._batch_selector.value = ()

        with self._xrd_search_status:
            clear_output(wait=True)
            if valid_batches:
                print(f"✅  {len(valid_batches)} of {total} batch(es) contain XRD data.")
            else:
                print("❌  None of the listed batches contain XRD data.")

        if button is not None:
            button.disabled = False
            button.description = "🔬 Search for XRD"

    def _load_xrd_from_selection(self, batch_selector):
        """Fetch XRD entries for all selected batches and populate the app."""
        from perotf_utils.api_calls import get_all_xrd, get_ids_in_batch, get_sample_description

        batch_ids = list(batch_selector.value) if batch_selector.value else []
        self.selected_batch_ids = batch_ids

        if not batch_ids:
            with self.load_status:
                clear_output(wait=True)
                print("Please select at least one batch.")
            return

        with self.load_status:
            clear_output(wait=True)
            print(f"⏳  Loading XRD data for {len(batch_ids)} batch(es)…")

        url = self.auth_manager.url
        token = self.auth_manager.current_token

        try:
            # Collect sample IDs from all selected batches
            all_sample_ids: list = []
            failed_batches: list = []
            for bid in batch_ids:
                try:
                    ids = get_ids_in_batch(url, token, [bid])
                    all_sample_ids.extend(ids)
                except Exception as exc:
                    failed_batches.append(bid)
                    with self.load_status:
                        print(f"  ⚠  Batch {bid}: {exc}")

            if not all_sample_ids:
                with self.load_status:
                    clear_output(wait=True)
                    print("❌  No samples found in the selected batches.")
                return

            with self.load_status:
                print(f"   Found {len(all_sample_ids)} sample(s). Fetching XRD measurements…")

            xrd_raw = get_all_xrd(url, token, all_sample_ids)

            # Variation names ("identifier"/description), same source as JV-Analysis
            try:
                identifiers = get_sample_description(url, token, all_sample_ids)
            except Exception:
                identifiers = {}

            # Parse and store patterns
            self.loaded_patterns = {}
            skipped = 0
            for lab_id, measurements in xrd_raw.items():
                for i, (archive_data, metadata) in enumerate(measurements):
                    two_theta, intensity = _extract_xrd_arrays(archive_data)
                    if two_theta is None:
                        skipped += 1
                        continue
                    suffix = f"_m{i + 1}" if len(measurements) > 1 else ""
                    label = f"{lab_id}{suffix}"
                    upload = (metadata.get("upload_name") or metadata.get("upload_id", "?"))[:50]
                    self.loaded_patterns[label] = {
                        "two_theta": two_theta,
                        "intensity": intensity,
                        "sample_id": lab_id,
                        "upload": upload,
                        "mainfile": metadata.get("mainfile", ""),
                        "variation": identifiers.get(lab_id, "No variation specified"),
                    }

            n = len(self.loaded_patterns)
            with self.load_status:
                clear_output(wait=True)
                if n:
                    print(f"✅  Loaded {n} XRD pattern(s) from {len(xrd_raw)} sample(s).")
                    if skipped:
                        print(f"   ⚠  {skipped} entr(y/ies) skipped (unrecognised data format).")
                    if failed_batches:
                        print(f"   ⚠  Failed batches: {failed_batches}")
                else:
                    print("❌  No XRD patterns could be extracted.")
                    print(
                        "   Verify that the selected batches contain "
                        f"{ENTRY_TYPES['xrd']} entries with recognisable "
                        "two_theta / intensity fields."
                    )
                    if skipped:
                        print(f"   ({skipped} entries had unrecognised formats.)")
                    return

            labels = sorted(self.loaded_patterns.keys())
            self._pattern_option_values = labels
            pattern_options = [
                (f"{lbl} | {self.loaded_patterns[lbl]['variation']}", lbl) for lbl in labels
            ]
            self.pattern_selector.options = pattern_options
            self.pattern_selector.value = tuple(labels[: min(8, len(labels))])
            self.ref_pattern_dropdown.options = pattern_options
            self.ref_pattern_dropdown.value = labels[0] if labels else None
            self.tabs.selected_index = 1

        except Exception as exc:
            with self.load_status:
                clear_output(wait=True)
                print(f"❌  Error loading XRD data:\n{exc}")
                traceback.print_exc()

    # ── overlay plot ──────────────────────────────────────────────────────────

    def _color_palette(self, n: int) -> list:
        palette = _COLOR_MAP.get(self.color_dropdown.value, px.colors.qualitative.Plotly)
        if n <= len(palette):
            return list(palette[:n])
        return [palette[i % len(palette)] for i in range(n)]

    def _get_display_name(self, label: str, mode: str = "Full name") -> str:
        """Build the legend/trace name for a pattern, depending on the chosen mode."""
        p = self.loaded_patterns.get(label, {})
        sample_id = p.get("sample_id", label)
        if mode == "Variation":
            return p.get("variation") or "No variation specified"
        if mode == "Sample name":
            suffix = label[len(sample_id) :]  # e.g. "_m2" for repeated measurements
            base = sample_id.split("_")[-1]
            return f"{base}{suffix}"
        return label  # "Full name"

    def _on_plot(self, _b=None):
        selected = list(self.pattern_selector.value)
        if not selected:
            with self.plot_output:
                clear_output(wait=True)
                print("No patterns selected.")
            return

        normalize = self.normalize_cb.value
        use_offset = self.offset_cb.value
        step = self.offset_step.value
        log_y = self.log_scale_cb.value
        lw = self.line_width_input.value
        colors = self._color_palette(len(selected))

        fig = go.Figure()
        legend_mode = self.display_name_dropdown.value

        for idx, label in enumerate(selected):
            p = self.loaded_patterns[label]
            x = p["two_theta"]
            y = p["intensity"].astype(float)
            display_name = self._get_display_name(label, legend_mode)

            if normalize:
                ymax = y.max()
                if ymax > 0:
                    y = y / ymax

            if use_offset:
                y = y + idx * step

            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y,
                    mode="lines",
                    name=display_name,
                    line=dict(color=colors[idx], width=lw),
                    hovertemplate=(
                        f"<b>{display_name}</b><br>2θ: %{{x:.3f}}°<br>I: %{{y:.4f}}<extra></extra>"
                    ),
                )
            )

        fig.update_layout(
            title=dict(text="XRD Diffractograms", font=dict(size=18)),
            xaxis_title="2θ (°)",
            yaxis_title="Normalised Intensity" if normalize else "Intensity (counts)",
            yaxis_type="log" if log_y else "linear",
            template="plotly_white",
            height=600,
            legend=dict(
                orientation="v",
                yanchor="top",
                y=1.0,
                xanchor="left",
                x=1.01,
                bgcolor="rgba(255,255,255,0.92)",
                bordercolor="lightgray",
                borderwidth=1,
            ),
            margin=dict(l=70, r=30, t=70, b=60),
            hovermode="x unified",
        )
        fig.update_xaxes(showgrid=True, gridcolor="lightgray", gridwidth=1)
        fig.update_yaxes(showgrid=True, gridcolor="lightgray", gridwidth=1)

        self._last_overlay_fig = fig
        with self.plot_output:
            clear_output(wait=True)
            display(go.FigureWidget(fig))

    # ── peak analysis ─────────────────────────────────────────────────────────

    def _on_detect_peaks(self, _b=None):
        label = self.ref_pattern_dropdown.value
        if not label or label not in self.loaded_patterns:
            with self.peak_plot_output:
                clear_output(wait=True)
                print("Please select a pattern from the dropdown.")
            return

        p = self.loaded_patterns[label]
        x = p["two_theta"]
        y = p["intensity"].astype(float)
        if self.peak_normalize_cb.value:
            ymax = y.max()
            y_norm = y / ymax if ymax > 0 else y
        else:
            y_norm = y

        try:
            peaks = self.fitting_engine.detect_peaks(
                x,
                y_norm,
                prominence=self.prominence_input.value,
                distance=self.distance_input.value,
            )
            self._detected_peaks = peaks
            self._peak_label = label
            self._peak_x = x
            self._peak_y_norm = y_norm
            self._last_fit_result = None  # a prior fit no longer matches the (re-)detected peaks

            self.fit_btn.disabled = len(peaks) == 0
            self._update_calibration_dropdown(peaks)

            self._draw_peak_plot(label, x, y_norm, peaks)
            self._draw_peak_table(peaks)

            if not peaks:
                with self.peak_table_output:
                    print("No peaks found. Try lowering Prominence or Distance.")

        except Exception as exc:
            with self.peak_plot_output:
                clear_output(wait=True)
                print(f"Peak detection failed: {exc}")

    def _draw_peak_plot(self, label, x, y_norm, peaks, fit_result=None):
        """Render the pattern (normalised or raw, per the checkbox) with peak markers and optional fit overlay."""
        fig = go.Figure()
        intensity_label = (
            "Normalised Intensity" if self.peak_normalize_cb.value else "Intensity (counts)"
        )

        fig.add_trace(
            go.Scatter(
                x=x,
                y=y_norm,
                mode="lines",
                name=label,
                line=dict(color="#1f77b4", width=2),
                hovertemplate="2θ: %{x:.3f}°<br>I: %{y:.4f}<extra></extra>",
            )
        )

        if fit_result is not None:
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=fit_result.best_fit,
                    mode="lines",
                    name="Total fit",
                    line=dict(color="crimson", width=2.5, dash="dash"),
                )
            )
            if hasattr(fit_result, "eval_components"):
                for ci, (cname, cvals) in enumerate(fit_result.eval_components().items()):
                    if cname.startswith("p"):
                        fig.add_trace(
                            go.Scatter(
                                x=x,
                                y=cvals,
                                mode="lines",
                                name=cname,
                                line=dict(
                                    color=_COMPONENT_COLORS[ci % len(_COMPONENT_COLORS)],
                                    width=1.5,
                                    dash="dot",
                                ),
                            )
                        )
                    else:
                        # background component (e.g. "bg_") — show it so it's
                        # visible that it is actually fitted to the baseline
                        fig.add_trace(
                            go.Scatter(
                                x=x,
                                y=cvals,
                                mode="lines",
                                name="Background",
                                line=dict(color="rgba(90,90,90,0.9)", width=1.5, dash="dashdot"),
                            )
                        )

        if peaks:
            y_span = float(np.max(y_norm) - np.min(y_norm)) if len(y_norm) else 0.0
            marker_offset = 0.04 * y_span if y_span > 0 else 0.04
            pk_x = [pk["center"] for pk in peaks]
            pk_y = [pk["height"] + marker_offset for pk in peaks]
            pk_txt = [f"{pk['center']:.3f}°" for pk in peaks]
            fig.add_trace(
                go.Scatter(
                    x=pk_x,
                    y=pk_y,
                    mode="markers+text",
                    marker=dict(symbol="triangle-down", size=11, color="orangered"),
                    text=pk_txt,
                    textposition="top center",
                    textfont=dict(size=9, color="orangered"),
                    name="Detected peaks",
                    hovertemplate="2θ = %{x:.3f}°<extra></extra>",
                )
            )

        fig.update_layout(
            title=f"Peak Analysis — {label}",
            xaxis_title="2θ (°)",
            yaxis_title=intensity_label,
            template="plotly_white",
            height=520,
            legend=dict(
                orientation="v",
                yanchor="top",
                y=1.0,
                xanchor="left",
                x=1.01,
                bgcolor="rgba(255,255,255,0.92)",
                bordercolor="lightgray",
                borderwidth=1,
            ),
            margin=dict(l=70, r=30, t=70, b=60),
            hovermode="x unified",
        )
        fig.update_xaxes(showgrid=True, gridcolor="lightgray")
        fig.update_yaxes(showgrid=True, gridcolor="lightgray")

        with self.peak_plot_output:
            clear_output(wait=True)
            display(go.FigureWidget(fig))

    def _draw_peak_table(self, peaks, fit_result=None):
        """Print a tidy table of detected (and optionally fitted) peak parameters."""
        with self.peak_table_output:
            clear_output(wait=True)
            if not peaks:
                return

            rows = []
            height_col = "Height (norm.)" if self.peak_normalize_cb.value else "Height (counts)"
            for i, pk in enumerate(peaks):
                row = {
                    "Peak": i + 1,
                    "2θ detected (°)": f"{pk['center']:.4f}",
                    height_col: f"{pk['height']:.4f}",
                    "FWHM est. (°)": f"{pk.get('sigma', 0) * 2.355:.4f}",
                }
                if fit_result is not None:
                    prefix = f"p{i}_"
                    c = fit_result.params.get(f"{prefix}center")
                    s = fit_result.params.get(f"{prefix}sigma")
                    a = fit_result.params.get(f"{prefix}amplitude")
                    row["2θ fitted (°)"] = f"{c.value:.4f}" if c else "—"
                    row["FWHM fitted (°)"] = f"{abs(s.value) * 2.355:.4f}" if s else "—"
                    row["Amplitude"] = f"{a.value:.5f}" if a else "—"
                rows.append(row)

            df = pd.DataFrame(rows)
            if fit_result is not None:
                r2 = getattr(fit_result, "rsquared", None)
                if r2 is not None:
                    print(f"Fit  R² = {r2:.6f}\n")

            print(df.to_string(index=False))

    def _on_fit_peaks(self, _b=None):
        if not self._detected_peaks:
            with self.peak_plot_output:
                clear_output(wait=True)
                print("Please detect peaks first.")
            return

        x = self._peak_x
        y_norm = self._peak_y_norm
        label = self._peak_label

        # Minimum sigma = 2.5× the median step so the Gaussian never collapses to zero
        x_arr = np.asarray(x) if x is not None else np.array([])
        x_step = float(np.median(np.diff(x_arr))) if len(x_arr) > 1 else 0.02
        min_sigma = max(x_step * 2.5, 0.02)
        # Keep peaks within ±5× their own sigma of their detected centre
        peak_models = [
            {
                "type": "Gaussian",
                "center": float(pk["center"]),
                "height": max(float(pk["height"]), 0.01),
                "sigma": max(float(pk.get("sigma", min_sigma * 3)), min_sigma),
                "gamma": 1.0,
                "min_sigma": min_sigma,
                "center_tol": min(10.0, max(x_step * 20, 1.0)),
            }
            for pk in self._detected_peaks
        ]

        try:
            self.fitting_engine.create_fit_parameters(
                peak_models,
                background_model=self.bg_model_dropdown.value,
                poly_degree=self.poly_degree_input.value,
            )
            result = self.fitting_engine.fit_current_spectrum(x, y_norm)
            self._last_fit_result = result
            self._draw_peak_plot(label, x, y_norm, self._detected_peaks, fit_result=result)
            self._draw_peak_table(self._detected_peaks, fit_result=result)

        except Exception as exc:
            with self.peak_plot_output:
                clear_output(wait=True)
                print(f"Fitting failed: {exc}")
                traceback.print_exc()

    def _update_calibration_dropdown(self, peaks):
        """Refresh the 2θ-calibration peak selector, defaulting to the peak closest to the ITO reference."""
        if not peaks:
            self.calib_peak_dropdown.options = []
            self.calib_peak_dropdown.value = None
            return
        self.calib_peak_dropdown.options = [
            (f"Peak {i + 1} (2θ={pk['center']:.3f}°)", i) for i, pk in enumerate(peaks)
        ]
        closest_idx = min(
            range(len(peaks)),
            key=lambda i: abs(peaks[i]["center"] - self.ITO_REFERENCE_2THETA),
        )
        self.calib_peak_dropdown.value = closest_idx
        self.calib_target_input.value = self.ITO_REFERENCE_2THETA

    def _on_apply_calibration(self, _b=None):
        """Shift the whole pattern (and its detected peaks) so the chosen peak lands on the target 2θ."""
        idx = self.calib_peak_dropdown.value
        if not self._detected_peaks or idx is None or idx >= len(self._detected_peaks):
            with self.calib_status:
                clear_output(wait=True)
                print("Please detect peaks and select one to align first.")
            return

        label = self._peak_label
        if not label or label not in self.loaded_patterns:
            with self.calib_status:
                clear_output(wait=True)
                print("No pattern selected.")
            return

        # Prefer the fitted center (more precise) if a fit for this peak set already exists
        current_center = float(self._detected_peaks[idx]["center"])
        if self._last_fit_result is not None:
            fitted_center = self._last_fit_result.params.get(f"p{idx}_center")
            if fitted_center is not None:
                current_center = float(fitted_center.value)

        target = float(self.calib_target_input.value)
        shift = target - current_center

        if abs(shift) < 1e-9:
            with self.calib_status:
                clear_output(wait=True)
                print("Shift is 0° — nothing to do.")
            return

        pattern = self.loaded_patterns[label]
        pattern["two_theta"] = pattern["two_theta"] + shift
        pattern["shift_deg"] = pattern.get("shift_deg", 0.0) + shift

        with self.calib_status:
            clear_output(wait=True)
            print(
                f"✅  Shifted '{label}' by {shift:+.4f}° "
                f"(peak {current_center:.4f}° → {target:.4f}°). "
                f"Cumulative shift: {pattern['shift_deg']:+.4f}°."
            )
            print("Re-detecting peaks on the corrected pattern…")

        # Re-detect on the corrected data — refreshes plot/table/fit button and
        # invalidates the stale fit result from before the shift.
        self._on_detect_peaks()

    # ── export ────────────────────────────────────────────────────────────────

    def _on_export_html(self, _b=None):
        if self._last_overlay_fig is None:
            with self.export_output:
                clear_output(wait=True)
                print("No overlay plot available. Create a plot in the XRD Patterns tab first.")
            return

        html = self._last_overlay_fig.to_html(include_plotlyjs="cdn", full_html=True)
        b64 = base64.b64encode(html.encode()).decode()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"XRD_overlay_{ts}.html"

        js = f"""
(function(){{
    var a = document.createElement('a');
    a.href = 'data:text/html;base64,{b64}';
    a.download = '{fname}';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
}})();"""
        with self.export_output:
            clear_output(wait=True)
            print(f"✅  Downloading {fname} …")
            display(Javascript(js))

    def _on_export_csv(self, _b=None):
        if not self.loaded_patterns:
            with self.export_output:
                clear_output(wait=True)
                print("No data loaded.")
            return

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for label, p in self.loaded_patterns.items():
                csv = pd.DataFrame(
                    {
                        "two_theta_deg": p["two_theta"],
                        "intensity": p["intensity"],
                    }
                ).to_csv(index=False)
                safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in label)
                zf.writestr(f"{safe}.csv", csv)

        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"XRD_data_{ts}.zip"

        js = f"""
(function(){{
    var b64 = '{b64}';
    var bs  = atob(b64);
    var arr = new Uint8Array(bs.length);
    for (var i = 0; i < bs.length; i++) arr[i] = bs.charCodeAt(i);
    var blob = new Blob([arr], {{type: 'application/zip'}});
    var url  = URL.createObjectURL(blob);
    var a    = document.createElement('a');
    a.href = url; a.download = '{fname}';
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
}})();"""
        with self.export_output:
            clear_output(wait=True)
            print(f"✅  Downloading {fname} ({len(self.loaded_patterns)} pattern(s)) …")
            display(Javascript(js))

    # ── public API ────────────────────────────────────────────────────────────

    def get_dashboard(self) -> widgets.VBox:
        """Return the complete application widget ready for display()."""
        header = widgets.HTML("""
        <div style="
            background: linear-gradient(135deg, #1f3964 0%, #1B6B5E 100%);
            padding: 18px 26px; border-radius: 10px;
            margin-bottom: 16px; color: white;
        ">
          <h1 style="margin: 0 0 5px 0; font-size: 1.85em; font-weight: 700;">
            🔬 XRD Analysis Dashboard
          </h1>
          <p style="margin: 0; opacity: 0.85; font-size: 0.95em;">
            Load diffractograms from the NOMAD API &nbsp;·&nbsp;
            Overlay &amp; compare patterns &nbsp;·&nbsp;
            Peak detection &amp; Gaussian fitting &nbsp;·&nbsp;
            Export HTML / CSV
          </p>
        </div>
        """)
        return widgets.VBox(
            [header, self.tabs],
            layout=widgets.Layout(max_width="1200px", margin="0 auto", padding="15px"),
        )
