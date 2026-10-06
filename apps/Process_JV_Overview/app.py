"""
Process & JV Overview
Combines the Overview_Dashboard (processing steps per batch, details per step)
with the JV-Analysis combined boxplot ("Boxplot - all - by Variable",
forward/reverse separated) so processes and efficiencies can be correlated
batch by batch.

Batches are filtered by the name and date encoded in the batch id
("KIT_<Name>_<YYYYMMDD>_<rest>"); batches without JV measurements are hidden.
"""

__author__ = "Joshua Damm"
__institution__ = "KIT"
__created__ = "October 2026"

import contextlib
import html
import io
import os
import queue
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

import ipywidgets as widgets
import pandas as pd
import plotly.express as px
import requests

# Own copies of the JV-Analysis modules, free to diverge from the JV app
from data_manager import DataManager
from IPython.display import HTML, display
from plot_manager import plotting_string_action
from resizable_plot_utility import display_resizable_plot

from perotf_utils import process_handling
from perotf_utils.api_calls import (
    get_all_batches_wth_data,
    get_ids_in_batch,
    get_processing_steps,
    get_sample_description,
)
from perotf_utils.auth_ui import AuthenticationUI
from perotf_utils.batch_selection import extract_date, get_batch_ids, sort_by_date_desc
from perotf_utils.config import API_ENDPOINT, ENTRY_TYPES, URL_BASE

JV_ENTRY_TYPE = ENTRY_TYPES["jv"]

OTHER_NAME = "(no name pattern)"
BATCH_PATTERN = re.compile(r"^(?P<inst>[^_]+)_(?P<name>[^_]+)_(?P<date>\d{8})(?:_|$)")
DATE_PATTERN = re.compile(r"^\d{8}$")

# Same fallback text as the JV app for samples without description
NO_VARIATION = "No variation specified"

# Plot code of the JV app: Option 1 = "all", Option 2 = "by Variable"
BOXPLOT_SELECTION = [("Boxplot", "all", "by Variable")]

# JV app filter defaults (JV-Analysis gui_components.FilterUI): numeric preset "Default", direction "Both",
# cycle mode "Best Cycle Only"
DEFAULT_FILTERS = [
    ("PCE(%)", "<", "40"),
    ("FF(%)", "<", "89"),
    ("FF(%)", ">", "24"),
    ("Voc(V)", "<", "2.5"),
    ("Voc(V)", ">", "0.5"),
    ("Jsc(mA/cm2)", "<", "0"),
    ("Jsc(mA/cm2)", ">", "-30"),
]
DEFAULT_DIRECTION = "Both"

# Sample-IDs, process steps, JV data (worker threads) + plot (main thread)
STEPS_PER_BATCH = 4
MAX_WORKERS = 4

PLOT_MIN_WIDTH = 500
FIG_HEIGHT = 600


# ── Auth manager ─────────────────────────────────────────────────────────────


class SimpleAuthManager:
    """Auth manager – mirrors the JV-Analysis pattern."""

    def __init__(self, base_url, api_endpoint):
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

    def authenticate_with_credentials(self, username, password):
        if not username or not password:
            raise ValueError("Username and Password are required.")
        response = requests.get(
            f"{self.url}/auth/token", params=dict(username=username, password=password), timeout=10
        )
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
        response = requests.get(
            f"{self.url}/users/me",
            headers={"Authorization": f"Bearer {self.current_token}"},
            timeout=10,
        )
        response.raise_for_status()
        self.current_user_info = response.json()
        return self.current_user_info

    def is_authenticated(self):
        return self.current_token is not None and self.current_user_info is not None

    def clear_authentication(self):
        self.current_token = None
        self.current_user_info = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def parse_batch_id(batch_id):
    """Return (name, 'YYYYMMDD' or None) from a batch id like KIT_Name_Date_rest."""
    match = BATCH_PATTERN.match(batch_id)
    if match:
        return match.group("name"), match.group("date")
    date = extract_date(batch_id)
    return OTHER_NAME, str(date) if date else None


def format_date(date):
    if not date:
        return "unknown date"
    return f"{date[0:4]}-{date[4:6]}-{date[6:8]}"


def format_duration(seconds):
    if seconds is None:
        return "--:--"
    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def plural(n, word, word_plural=None):
    return f"{n} {word}" if n == 1 else f"{n} {word_plural or word + 's'}"


def count_samples(n):
    return plural(n, "sample")


def variation_from_identifier(identifier):
    """Same default as the JV app ('Variation'): the part after '&'."""
    if identifier and "&" in str(identifier):
        return str(identifier).split("&", 1)[1]
    return "Unknown"


def format_error(exc):
    return f"{type(exc).__name__}: {exc}"


def jv_app_colors(num_colors):
    """Boxplot colours as the JV app picks them after filtering: Viridis with one colour per variation,
    clamped to 2..20 (ColorSchemeSelector._generate_continuous_colors)."""
    num_colors = max(2, min(20, num_colors))
    palette = px.colors.sequential.Viridis
    if num_colors <= len(palette):
        step = (len(palette) - 1) / (num_colors - 1)
        return [palette[int(i * step)] for i in range(num_colors)]

    def to_rgb(hex_color):
        hex_color = hex_color.lstrip("#")
        return [int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]

    colors = []
    for i in range(num_colors):
        palette_index = i / (num_colors - 1) * (len(palette) - 1)
        lower = int(palette_index)
        upper = min(lower + 1, len(palette) - 1)
        factor = palette_index - lower
        if factor == 0 or lower == upper:
            colors.append(palette[lower])
            continue
        rgb = [a + (b - a) * factor for a, b in zip(to_rgb(palette[lower]), to_rgb(palette[upper]))]
        colors.append("#{:02x}{:02x}{:02x}".format(*(int(c * 255) for c in rgb)))
    return colors


def get_batches_with_uploads(url, token, batch_type=ENTRY_TYPES["batch"]):
    """Like api_calls.get_batch_ids, but returns {batch lab_id: {"upload_id", "upload_name"}}."""
    query = {
        "required": {
            "data": "*",
            "metadata": {"upload_id": "*", "upload_name": "*"},
        },
        "owner": "visible",
        "query": {"entry_type": batch_type},
        "pagination": {"page_size": 10000},
    }
    response = requests.post(
        f"{url}/entries/archive/query", headers={"Authorization": f"Bearer {token}"}, json=query
    )
    response.raise_for_status()
    batches = {}
    for entry in response.json()["data"]:
        archive = entry.get("archive", {})
        lab_id = archive.get("data", {}).get("lab_id")
        if not lab_id:
            continue
        metadata = archive.get("metadata", {})
        batches[lab_id] = {
            "upload_id": entry.get("upload_id") or metadata.get("upload_id", ""),
            "upload_name": metadata.get("upload_name") or "",
        }
    return batches


def get_upload_ids_with_entries(url, token, entry_type):
    """Upload ids containing at least one entry of entry_type (one aggregation request, no entries downloaded)."""
    query = {
        "owner": "visible",
        "query": {"entry_type": entry_type},
        "pagination": {"page_size": 0},
        "aggregations": {
            "uploads": {"terms": {"quantity": "upload_id", "pagination": {"page_size": 10000}}}
        },
    }
    response = requests.post(
        f"{url}/entries/query", headers={"Authorization": f"Bearer {token}"}, json=query
    )
    response.raise_for_status()
    buckets = response.json()["aggregations"]["uploads"]["terms"]["data"]
    return {bucket["value"] for bucket in buckets}


def get_upload_name(url, token, upload_id):
    """Upload name of a single upload (fallback when the batch query did not return it)."""
    response = requests.get(
        f"{url}/uploads/{upload_id}", headers={"Authorization": f"Bearer {token}"}, timeout=10
    )
    response.raise_for_status()
    return response.json().get("data", {}).get("upload_name") or ""


class ToggleBatchProcess(process_handling.batch_process):
    """batch_process with a compact step grid, 'details' buttons that open and close the details
    and a variation column in the detail tables."""

    def __init__(self, *args, variations=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.variations = variations or {}  # sample lab_id -> variation
        self.open_step = None
        # Buttons directly behind the step names instead of the fixed 3fr/1fr grid
        self.layout.grid_template_columns = "max-content max-content"
        self.layout.grid_gap = "2px 12px"
        self.layout.align_items = "center"
        self.layout.width = "fit-content"
        self.layout.max_width = "100%"
        self.layout.padding = "4px 8px"

    def show_process_details(self, step_index):
        if self.open_step == step_index:
            self.detail_widget.clear_output()
            self.open_step = None
        else:
            self._render_details(step_index)
            self.open_step = step_index

        buttons = [child for child in self.children if isinstance(child, widgets.Button)]
        for index, button in enumerate(buttons):
            is_open = index == self.open_step
            button.description = "hide" if is_open else "details"
            button.button_style = "info" if is_open else ""

    def _variations_of(self, sample_ids):
        unique = dict.fromkeys(
            self.variations.get(sample_id, NO_VARIATION) for sample_id in sample_ids
        )
        return ", ".join(unique)

    def _render_details(self, step_index):
        """Like batch_process.show_process_details, plus a 'Variation' column for the samples of each row."""
        self.detail_widget.clear_output()
        sample_lists = self.samples_for_processes_in_step(step_index)
        with self.detail_widget:
            for process_idx, process in enumerate(self.steps_merged[step_index]):
                table = process_handling.make_table(
                    process,
                    sample_lists,
                    remove_constants=self.exclude_constants.value,
                    remove_string=self.exclude_strings.value,
                    abbreviate_keys=self.abbreviate_keys.value,
                )
                table.insert(
                    0,
                    "Variation",
                    [self._variations_of(sample_lists[idx]) for idx in process["indices"]],
                    allow_duplicates=True,
                )
                display(HTML(table.to_html()))
                display(
                    widgets.GridBox(
                        self.manufacturing_params[step_index][process_idx],
                        layout=widgets.Layout(grid_template_columns="repeat(10, 1fr)"),
                    )
                )


# ── Progress bar ─────────────────────────────────────────────────────────────


class LoadingProgress:
    """tqdm-like progress bar: percentage, steps, elapsed < remaining, message."""

    def __init__(self):
        self.bar = widgets.IntProgress(
            value=0,
            min=0,
            max=1,
            bar_style="info",
            layout=widgets.Layout(width="100%", height="22px"),
        )
        self.label = widgets.HTML()
        self.widget = widgets.VBox(
            [self.label, self.bar], layout=widgets.Layout(display="none", margin="0 0 10px 0")
        )
        self._t0 = time.time()
        self._message = ""

    def start(self, total, message="Starting ..."):
        self._t0 = time.time()
        self.bar.max = max(total, 1)
        self.bar.value = 0
        self.bar.bar_style = "info"
        self.widget.layout.display = "flex"
        self.update(message)

    def advance(self, message=None, n=1):
        self.bar.value = min(self.bar.value + n, self.bar.max)
        self.update(message)

    def update(self, message=None):
        if message is not None:
            self._message = message
        done, total = self.bar.value, self.bar.max
        elapsed = time.time() - self._t0
        remaining = elapsed / done * (total - done) if done else None
        self.label.value = (
            f"<span style='font-family:monospace'><b>{100 * done / total:3.0f}%</b> "
            f"| {done}/{total} steps "
            f"[{format_duration(elapsed)} &lt; {format_duration(remaining)}]</span>"
            f" &nbsp; {html.escape(self._message)}"
        )

    def finish(self, message, bar_style="success"):
        self.bar.value = self.bar.max
        self.bar.bar_style = bar_style
        self.update(message)


# ── Main application ─────────────────────────────────────────────────────────


class ProcessJVOverviewApp:
    """Batch filter by name/date, then per batch: process steps (left) and JV boxplots (right)."""

    def __init__(self):
        self.auth_manager = SimpleAuthManager(URL_BASE, API_ENDPOINT)
        self.all_batches = []
        self.batch_info = {}  # batch_id -> (name, date)
        self.upload_info = {}  # batch_id -> {"upload_id", "upload_name"}
        # batch_id -> {"process": ToggleBatchProcess | None, "jvc": DataFrame, "sample_ids": [...], "variations": {...}}
        self.batch_results = {}

        self._create_widgets()
        self._setup_callbacks()
        self._auto_authenticate()

    # ── UI construction ──────────────────────────────────────────────────────

    def _create_widgets(self):
        self.auth_ui = AuthenticationUI(self.auth_manager)
        self.status_html = widgets.HTML()

        self.name_select = widgets.SelectMultiple(
            options=[], description="Names", rows=12, layout=widgets.Layout(width="280px")
        )
        self.date_from = widgets.Text(
            placeholder="YYYYMMDD",
            description="Date from",
            style={"description_width": "80px"},
            layout=widgets.Layout(width="230px"),
        )
        self.date_to = widgets.Text(
            placeholder="YYYYMMDD",
            description="Date to",
            style={"description_width": "80px"},
            layout=widgets.Layout(width="230px"),
        )
        self.search_field = widgets.Text(
            placeholder="batch or upload name",
            description="Search",
            style={"description_width": "80px"},
            layout=widgets.Layout(width="230px"),
        )
        self.date_hint = widgets.HTML()
        self.clear_filter_button = widgets.Button(
            description="Reset filters", icon="times", layout=widgets.Layout(width="230px")
        )

        self.batch_select = widgets.SelectMultiple(
            options=[], description="Batches", rows=12, layout=widgets.Layout(width="520px")
        )
        self.match_label = widgets.HTML()
        self.select_all_button = widgets.Button(
            description="All matches", icon="check-square-o", layout=widgets.Layout(width="140px")
        )
        self.select_none_button = widgets.Button(
            description="None", icon="square-o", layout=widgets.Layout(width="100px")
        )
        self.load_button = widgets.Button(
            description="Load data",
            button_style="primary",
            icon="download",
            disabled=True,
            layout=widgets.Layout(width="240px"),
        )

        self.exclude_const = widgets.Checkbox(description="hide nonvaried values", indent=False)
        self.exclude_string = widgets.Checkbox(description="hide text values", indent=False)
        self.abbreviate_keys = widgets.Checkbox(description="abbreviate value names", indent=False)

        self.progress = LoadingProgress()
        self.results_box = widgets.VBox()

        filter_column = widgets.VBox(
            [
                self.date_from,
                self.date_to,
                self.search_field,
                self.date_hint,
                self.clear_filter_button,
            ]
        )
        batch_column = widgets.VBox(
            [
                self.batch_select,
                widgets.HBox([self.select_all_button, self.select_none_button]),
                self.match_label,
                self.load_button,
            ]
        )
        self.selection_box = widgets.VBox(
            [
                widgets.HTML(
                    "<h3 style='margin:4px 0'>Select batches</h3>"
                    "<p style='margin:0 0 8px 0'><i>Batch scheme: KIT_Name_YYYYMMDD_rest. "
                    "No name selected means all names, empty date fields mean no limit. "
                    "Only batches with JV measurements are listed.</i></p>"
                ),
                widgets.HBox(
                    [self.name_select, filter_column, batch_column],
                    layout=widgets.Layout(gap="20px", flex_flow="row wrap"),
                ),
            ],
            layout=widgets.Layout(
                display="none", border="1px solid #ccc", padding="10px", margin="0 0 10px 0"
            ),
        )

        self.detail_options_box = widgets.HBox(
            [
                widgets.HTML("<b>Detail tables:</b>&nbsp;"),
                self.exclude_const,
                self.exclude_string,
                self.abbreviate_keys,
            ],
            layout=widgets.Layout(display="none", gap="15px", margin="0 0 10px 0"),
        )

        self.dashboard = widgets.VBox(
            [
                widgets.HTML("<h2 style='margin:4px 0'>Process &amp; JV Overview</h2>"),
                self.auth_ui.get_widget(),
                self.status_html,
                self.selection_box,
                self.progress.widget,
                self.detail_options_box,
                self.results_box,
            ]
        )

    def _setup_callbacks(self):
        self.auth_ui.set_success_callback(self._on_auth_success)
        for widget in (self.name_select, self.date_from, self.date_to, self.search_field):
            widget.observe(self._apply_batch_filter, names="value")
        self.batch_select.observe(self._update_load_button, names="value")
        self.clear_filter_button.on_click(self._on_clear_filter)
        self.select_all_button.on_click(
            lambda _b: setattr(
                self.batch_select,
                "value",
                tuple(value for _label, value in self.batch_select.options),
            )
        )
        self.select_none_button.on_click(lambda _b: setattr(self.batch_select, "value", ()))
        self.load_button.on_click(self._on_load_clicked)

    def get_dashboard(self):
        return self.dashboard

    # ── Authentication & batch list ──────────────────────────────────────────

    def _auto_authenticate(self):
        if os.environ.get("JUPYTERHUB_USER"):
            self.auth_ui.auth_method_selector.value = "Token (from ENV)"
            self.auth_ui._on_auth_button_clicked(None)
        else:
            # Local use: open the connection settings so username/password can be entered
            self.auth_ui.auth_method_selector.value = "Username/Password"
            self.auth_ui._toggle_settings(None)

    def _set_status(self, message, color="#333"):
        self.status_html.value = f"<p style='color:{color};margin:4px 0'>{message}</p>"

    def _on_auth_success(self):
        self.auth_ui.close_settings()
        self._set_status("⏳ Loading batch list ...")
        url, token = self.auth_manager.url, self.auth_manager.current_token
        try:
            self.upload_info = get_batches_with_uploads(url, token)
            all_ids = list(self.upload_info)
        except Exception:
            # Fall back to the plain batch list (without upload names)
            try:
                self.upload_info = {}
                all_ids = list(get_batch_ids(url, token))
            except Exception as exc:
                self._set_status(
                    f"❌ Could not load the batch list: {html.escape(format_error(exc))}", "red"
                )
                return

        # Same rule as batch_selection.create_batch_selection: hide sub-batches
        id_set = set(all_ids)
        main_batches = [b for b in all_ids if "_".join(b.split("_")[:-1]) not in id_set]

        batches_with_jv = self._filter_batches_with_jv(url, token, main_batches)
        if batches_with_jv is None:
            jv_note = "JV filter unavailable, showing all batches"
            batches_with_jv = main_batches
        else:
            jv_note = f"{plural(len(main_batches) - len(batches_with_jv), 'batch', 'batches')} without JV data hidden"

        self.all_batches = sort_by_date_desc(batches_with_jv)
        self.batch_info = {b: parse_batch_id(b) for b in self.all_batches}

        name_counts = pd.Series(
            [name for name, _ in self.batch_info.values()], dtype=object
        ).value_counts()
        names = sorted(name_counts.index, key=lambda n: (n == OTHER_NAME, n.lower()))
        self.name_select.options = [(f"{name} ({name_counts[name]})", name) for name in names]

        self._set_status(
            f"✅ Found {plural(len(self.all_batches), 'batch', 'batches')} from "
            f"{plural(len(names), 'name')} ({jv_note}).",
            "green",
        )
        self.selection_box.layout.display = "flex"
        self.detail_options_box.layout.display = "flex"
        self._apply_batch_filter()

    def _filter_batches_with_jv(self, url, token, batch_ids):
        """Keep only batches whose upload contains JV measurements (hides e.g. test batches).
        Returns None if neither lookup works."""
        try:
            if self.upload_info:
                jv_uploads = get_upload_ids_with_entries(url, token, JV_ENTRY_TYPE)
                if jv_uploads:
                    return [
                        b
                        for b in batch_ids
                        if self.upload_info.get(b, {}).get("upload_id") in jv_uploads
                    ]
        except Exception:
            pass
        try:
            # Existing JV app call: batches in uploads that contain JV entries
            with_jv = set(get_all_batches_wth_data(url, token, JV_ENTRY_TYPE))
            return [b for b in batch_ids if b in with_jv]
        except Exception:
            return None

    # ── Batch filtering ──────────────────────────────────────────────────────

    def _read_date(self, text_widget, label, hints):
        value = text_widget.value.strip()
        if not value:
            return None
        if not DATE_PATTERN.match(value):
            hints.append(
                f"⚠️ {label}: '{html.escape(value)}' is not a date in YYYYMMDD format – ignored."
            )
            return None
        return value

    def _apply_batch_filter(self, _change=None):
        hints = []
        date_from = self._read_date(self.date_from, "Date from", hints)
        date_to = self._read_date(self.date_to, "Date to", hints)
        if date_from and date_to and date_from > date_to:
            hints.append("⚠️ 'Date from' is after 'Date to'.")
        self.date_hint.value = "<br>".join(f"<span style='color:#c0392b'>{h}</span>" for h in hints)

        names = set(self.name_select.value)
        search = self.search_field.value.strip().lower()

        matches = []
        for batch_id in self.all_batches:
            name, date = self.batch_info[batch_id]
            if names and name not in names:
                continue
            if (date_from or date_to) and date is None:
                continue
            if date_from and date < date_from:
                continue
            if date_to and date > date_to:
                continue
            if (
                search
                and search not in batch_id.lower()
                and search not in self._upload_name(batch_id).lower()
            ):
                continue
            matches.append(batch_id)

        # One sync message for options + selection, so the frontend never sees an index without its option
        with self.batch_select.hold_sync():
            self.batch_select.options = [
                (self._batch_label(batch_id), batch_id) for batch_id in matches
            ]
            # Pre-select all matches once a filter is active; the unfiltered list starts empty-selected
            if names or date_from or date_to or search:
                self.batch_select.value = tuple(matches)
            else:
                self.batch_select.value = ()
        self.match_label.value = (
            f"<i>{len(matches)} of {plural(len(self.all_batches), 'batch', 'batches')} "
            f"match the filter</i>"
        )
        self._update_load_button()

    def _upload_name(self, batch_id):
        return self.upload_info.get(batch_id, {}).get("upload_name", "")

    def _batch_label(self, batch_id):
        upload_name = self._upload_name(batch_id)
        return (
            f"{batch_id}  ·  {upload_name}" if upload_name and upload_name != batch_id else batch_id
        )

    def _update_load_button(self, _change=None):
        count = len(self.batch_select.value)
        self.load_button.disabled = count == 0
        self.load_button.description = (
            f"Load data ({plural(count, 'batch', 'batches')})" if count else "Load data"
        )

    def _on_clear_filter(self, _button):
        self.name_select.value = ()
        self.date_from.value = ""
        self.date_to.value = ""
        self.search_field.value = ""

    # ── Loading (worker threads) ─────────────────────────────────────────────

    def _load_jv(self, batch_id):
        """Load JV parameters via the JV app's DataManager (condition = sample variation) and apply the
        JV app's default filtering like its _on_apply_filters: best cycle only, then the numeric preset.
        Returns (all JV rows, filtered JV rows) or (None, None)."""
        data_manager = DataManager(self.auth_manager)
        if not data_manager.load_batch_data([batch_id], None):
            return None, None
        jvc = data_manager.data["jvc"]
        conditions = {
            ident: variation_from_identifier(ident) for ident in jvc["identifier"].unique()
        }
        data_manager.apply_conditions(conditions)
        jvc_all = data_manager.data["jvc"]

        working = jvc_all
        if data_manager.has_cycle_data:
            working = data_manager.apply_best_cycle_filter(working, verbose=False)

        # apply_filters works on data["jvc"] (swapped like in the JV app) and would also match the
        # JV curves row by row – curves are not plotted here, so drop them to save time
        data_manager.data.pop("curves", None)
        data_manager.data["jvc"] = working
        filtered, _omitted, _params = data_manager.apply_filters(
            DEFAULT_FILTERS, DEFAULT_DIRECTION, None, verbose=False
        )
        data_manager.data["jvc"] = jvc_all
        return jvc_all, filtered

    def _fetch_batch(self, batch_id, events):
        """Runs in a worker thread – must not touch widgets, only post events."""
        url, token = self.auth_manager.url, self.auth_manager.current_token
        result = {
            "batch_id": batch_id,
            "sample_ids": [],
            "variations": {},
            "process_list": [],
            "jvc": None,
            "jvc_filtered": None,
            "errors": [],
            "upload_name": self._upload_name(batch_id),
        }
        try:
            upload_id = self.upload_info.get(batch_id, {}).get("upload_id")
            if not result["upload_name"] and upload_id:
                try:
                    result["upload_name"] = get_upload_name(url, token, upload_id)
                except Exception:
                    pass  # the section title then falls back to the batch id

            try:
                result["sample_ids"] = get_ids_in_batch(url, token, [batch_id])
            except Exception as exc:
                result["errors"].append(f"Sample IDs: {format_error(exc)}")
            if result["sample_ids"]:
                # Sample description = variation (same source as the JV app's "Variation" default)
                try:
                    result["variations"] = get_sample_description(url, token, result["sample_ids"])
                except Exception as exc:
                    result["errors"].append(f"Variations: {format_error(exc)}")
            events.put(("step", batch_id, "sample IDs and variations loaded"))

            if result["sample_ids"]:
                try:
                    result["process_list"] = get_processing_steps(url, token, result["sample_ids"])
                except Exception as exc:
                    result["errors"].append(f"Process steps: {format_error(exc)}")
            events.put(("step", batch_id, "process steps loaded"))

            if result["sample_ids"]:
                try:
                    result["jvc"], result["jvc_filtered"] = self._load_jv(batch_id)
                except Exception as exc:
                    result["errors"].append(f"JV data: {format_error(exc)}")
            events.put(("step", batch_id, "JV data loaded"))
        except Exception as exc:
            result["errors"].append(format_error(exc))
        finally:
            events.put(("done", batch_id, result))

    def _on_load_clicked(self, _button):
        batch_ids = list(self.batch_select.value)
        if not batch_ids:
            return
        self.load_button.disabled = True
        try:
            self._load_batches(batch_ids)
        except Exception as exc:
            self.progress.finish(f"Aborted: {format_error(exc)}", bar_style="danger")
            traceback.print_exc()
        finally:
            self._update_load_button()

    def _load_batches(self, batch_ids):
        self.batch_results = {}
        slots = {batch_id: self._placeholder(batch_id) for batch_id in batch_ids}
        self.results_box.children = [slots[b] for b in batch_ids]

        total_batches = len(batch_ids)
        self.progress.start(
            total_batches * STEPS_PER_BATCH,
            f"Loading {plural(total_batches, 'batch', 'batches')} with "
            f"{plural(min(MAX_WORKERS, total_batches), 'parallel request')} ...",
        )
        events = queue.Queue()
        finished = 0
        failed = 0

        # API calls run in parallel threads; widgets and plots are only touched here (main thread)
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, total_batches)) as pool:
            for batch_id in batch_ids:
                pool.submit(self._fetch_batch, batch_id, events)

            while finished < total_batches:
                try:
                    kind, batch_id, payload = events.get(timeout=0.5)
                except queue.Empty:
                    self.progress.update()  # keep the elapsed time ticking
                    continue

                if kind == "step":
                    self.progress.advance(f"{batch_id}: {payload}")
                    continue

                self.progress.update(f"{batch_id}: building overview and boxplot ...")
                try:
                    self._render_batch(slots[batch_id], payload)
                except Exception as exc:
                    slots[batch_id].children = [
                        self._header(batch_id),
                        self._message_html(f"Rendering failed: {format_error(exc)}", "error"),
                    ]
                if payload["errors"]:
                    failed += 1
                finished += 1
                self.progress.advance(f"{batch_id}: done ({finished}/{total_batches} batches)")

        summary = f"Done: {plural(total_batches, 'batch', 'batches')} loaded"
        if failed:
            summary += f", {failed} with errors (see red notes)"
        self.progress.finish(summary, bar_style="warning" if failed else "success")

    # ── Rendering (main thread) ──────────────────────────────────────────────

    @staticmethod
    def _message_html(message, kind="info"):
        colors = {
            "info": ("#555", "#f4f6f8"),
            "warning": ("#8a6d3b", "#fcf8e3"),
            "error": ("#a94442", "#f2dede"),
        }
        color, background = colors[kind]
        return widgets.HTML(
            f"<div style='color:{color};background:{background};padding:6px 10px;"
            f"border-radius:4px;margin:4px 0'>{html.escape(message)}</div>"
        )

    @staticmethod
    def _log_html(title, log_text, max_lines=25):
        lines = log_text.strip().splitlines()[-max_lines:]
        return widgets.HTML(
            f"<div style='color:#a94442;background:#f2dede;padding:6px 10px;border-radius:4px;margin:4px 0'>"
            f"{html.escape(title)}<pre style='white-space:pre-wrap;font-size:11px;margin:6px 0 0 0'>"
            f"{html.escape(chr(10).join(lines))}</pre></div>"
        )

    def _header(self, batch_id, details=""):
        name, date = self.batch_info.get(batch_id, parse_batch_id(batch_id))
        upload_name = self._upload_name(batch_id)
        if upload_name and upload_name != batch_id:
            title = (
                f"<span style='font-size:1.25em;font-weight:bold'>{html.escape(upload_name)}</span>"
                f" &nbsp;<span style='color:#666;font-family:monospace'>{html.escape(batch_id)}</span>"
            )
        else:
            title = (
                f"<span style='font-size:1.25em;font-weight:bold'>{html.escape(batch_id)}</span>"
            )
        return widgets.HTML(
            f"<div style='margin:0 0 6px 0'>{title}<br><span style='color:#555'>{format_date(date)} · "
            f"{html.escape(name)}{details}</span></div>"
        )

    def _placeholder(self, batch_id):
        return widgets.VBox(
            [self._header(batch_id), self._message_html("⏳ loading ...")],
            layout=widgets.Layout(border="1px solid #bbb", padding="10px", margin="0 0 14px 0"),
        )

    @staticmethod
    def _variation_overview(sample_ids, variations):
        """Collapsible two-column table above the process steps: variation -> samples (display only)."""
        groups = {}
        for sample_id in sample_ids:
            groups.setdefault(variations.get(sample_id, NO_VARIATION), []).append(sample_id)

        cell = "border:1px solid #ccc;padding:3px 8px;vertical-align:top;text-align:left"
        rows = "".join(
            f"<tr><td style='{cell}'>{html.escape(variation)} <span style='color:#888'>({len(samples)})</span></td>"
            f"<td style='{cell}'>{', '.join(html.escape(s) for s in samples)}</td></tr>"
            for variation, samples in groups.items()
        )
        table = widgets.HTML(
            f"<table style='border-collapse:collapse;margin:2px 0 8px 0;font-size:0.95em'>"
            f"<tr><th style='{cell}'>Variation</th><th style='{cell}'>Samples</th></tr>{rows}</table>",
            layout=widgets.Layout(display="none"),
        )

        label = f"Variations ({len(groups)}, {count_samples(len(sample_ids))})"
        toggle = widgets.Button(
            description=f"▶ {label}",
            tooltip="Show which samples belong to which variation",
            layout=widgets.Layout(width="auto"),
        )

        def on_toggle(_button):
            opening = table.layout.display == "none"
            table.layout.display = None if opening else "none"
            toggle.description = f"{'▼' if opening else '▶'} {label}"

        toggle.on_click(on_toggle)
        return widgets.VBox([toggle, table], layout=widgets.Layout(margin="0 0 8px 0"))

    def _render_batch(self, slot, result):
        batch_id = result["batch_id"]
        sample_ids = result["sample_ids"]
        process_list = result["process_list"]
        jvc = result["jvc"] if result["jvc"] is not None else pd.DataFrame()
        jvc_filtered = (
            result["jvc_filtered"] if result["jvc_filtered"] is not None else pd.DataFrame()
        )
        has_jv = not jvc.empty
        has_filtered = not jvc_filtered.empty
        if result.get("upload_name"):
            self.upload_info.setdefault(batch_id, {})["upload_name"] = result["upload_name"]

        details = f" · {count_samples(len(sample_ids))}"
        if has_jv:
            details += (
                f" · {len(jvc_filtered)} of {len(jvc)} JV measurements kept by the default filters"
            )
        if has_filtered:
            details += (
                f" · PCE max {jvc_filtered['PCE(%)'].max():.2f} % "
                f"/ median {jvc_filtered['PCE(%)'].median():.2f} %"
            )
        header = self._header(batch_id, html.escape(details))
        messages = [self._message_html(error, "error") for error in result["errors"]]

        # Left: variations + processing steps like the Overview_Dashboard
        variations = result["variations"]
        left_children = [self._variation_overview(sample_ids, variations)] if sample_ids else []
        detail_output = widgets.Output(layout=widgets.Layout(max_height="650px", overflow="auto"))
        parameter_output = widgets.Output()
        process = None
        if process_list:
            # Best PCE per sample feeds batch_process.efficiencies (used by get_selected_manufacturing_parameters)
            efficiencies = (
                jvc_filtered.groupby("sample_id")["PCE(%)"].max().to_dict() if has_filtered else {}
            )
            try:
                process = ToggleBatchProcess(
                    process_list,
                    efficiencies,
                    batch_id,
                    detail_output,
                    parameter_output,
                    self.exclude_const,
                    self.exclude_string,
                    self.abbreviate_keys,
                    variations=variations,
                )
                left_children += [
                    widgets.HTML("<b>Process steps</b>"),
                    process,
                    detail_output,
                    parameter_output,
                ]
            except Exception as exc:
                left_children.append(
                    self._message_html(
                        f"Could not prepare the process steps: {format_error(exc)}", "error"
                    )
                )
        else:
            left_children.append(self._message_html("No process steps found.", "warning"))
        # Width follows the content (step names, opened details), at most half of the row
        left = widgets.VBox(
            left_children,
            layout=widgets.Layout(
                flex="0 1 auto", min_width="300px", max_width="50%", margin="0 20px 0 0"
            ),
        )

        # Right: combined 2x2 JV boxplot by variation, forward/reverse separated, JV app default filters.
        # No fixed pixel widths: the plot takes the remaining row width and follows window resizes.
        plot_output = widgets.Output(
            layout=widgets.Layout(flex=f"1 1 {PLOT_MIN_WIDTH}px", min_width=f"{PLOT_MIN_WIDTH}px")
        )
        if has_filtered:
            try:
                fig, log_text = self._make_boxplot(jvc_filtered, jvc)
            except Exception:
                fig, log_text = None, traceback.format_exc()
            with plot_output:
                if fig is not None:
                    # Not fig.show(): the 'notebook' renderer needs require.js, which Voila does not provide
                    n_conditions = (
                        jvc_filtered["condition"].nunique()
                        if "condition" in jvc_filtered.columns
                        else 0
                    )
                    display_resizable_plot(
                        fig,
                        title="JV boxplots by variation",
                        width="100%",
                        height=FIG_HEIGHT,
                        subtitle=(
                            f"{len(jvc_filtered)} of {len(jvc)} measurements, {n_conditions} variations · "
                            f"best cycle only, default filter preset · dark = reverse, light = forward scan"
                        ),
                        filename=f"{batch_id}_JV_boxplots",
                    )
                else:
                    display(
                        self._log_html("Could not create the boxplot:", log_text or "no output")
                    )
        elif has_jv:
            with plot_output:
                display(
                    self._message_html(
                        f"All {len(jvc)} JV measurements were removed by the default filters.",
                        "warning",
                    )
                )
        else:
            with plot_output:
                display(self._message_html("No JV data found.", "warning"))

        self.batch_results[batch_id] = {
            "process": process,
            "jvc": jvc,
            "jvc_filtered": jvc_filtered,
            "sample_ids": sample_ids,
            "variations": variations,
        }
        slot.children = [
            header,
            *messages,
            widgets.HBox(
                [left, plot_output],
                layout=widgets.Layout(flex_flow="row wrap", align_items="flex-start"),
            ),
        ]

    @staticmethod
    def _make_boxplot(jvc_filtered, jvc_all):
        """Return (figure or None, captured console output of the JV plotting code)."""
        empty = pd.DataFrame()
        n_conditions = (
            jvc_filtered["condition"].nunique() if "condition" in jvc_filtered.columns else 8
        )
        log = io.StringIO()
        # plotting_string_action reports errors only via print/traceback – capture them for the UI
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            figs, _names = plotting_string_action(
                BOXPLOT_SELECTION,
                (
                    jvc_filtered,
                    jvc_all,
                    empty,
                ),  # filtered_jv, complete_jv, curves (unused for boxplots)
                (
                    empty,
                    [],
                    True,
                    os.getcwd(),
                    [],
                ),  # omitted_jv, filter_pars, is_conditions, path, samples
                is_voila=True,
                color_scheme=jv_app_colors(n_conditions),
                separate_scan_dir=True,
            )
        if not figs or figs[0] is None:
            return None, log.getvalue()
        return figs[0], log.getvalue()
