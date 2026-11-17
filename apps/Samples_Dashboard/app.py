"""Samples Dashboard (admin): how many samples each person uploaded, and when.

Replaces the samples dashboard notebook of the old admin scripts (nomad_api package, %run
module notebooks, a local cache). Loads every sample entry with one NOMAD query, plots
samples per author and over time, and keeps the attribution overrides (who an upload is
credited to) in a CSV file next to the usage log. Nothing here writes to NOMAD.
"""

import html
import logging
import os
from datetime import datetime

import ipywidgets as widgets
import pandas as pd
from data_manager import (
    SCOPE_ADMIN,
    OverridesChangedError,
    changed_uploads,
    effective_authors,
    filter_uploads,
    known_authors,
    load_samples,
    overrides_csv,
    parse_overrides_csv,
    read_overrides,
    samples_frame,
    save_overrides,
    set_override,
    uploads_table,
)
from IPython.display import display
from plot_manager import (
    GROUPINGS,
    author_counts,
    author_figure,
    filter_by_date,
    time_counts,
    time_figure,
)

from perotf_utils.auth_manager import AuthenticationManager
from perotf_utils.auth_ui import AuthenticationUI
from perotf_utils.config import API_ENDPOINT, URL_BASE
from perotf_utils.downloads import start_download
from perotf_utils.manual import manual_panel
from perotf_utils.table_utils import csv_safe

logger = logging.getLogger(__name__)

INTRO = """
<h3 style="margin:0 0 6px 0">Samples Dashboard</h3>
<p style="margin:0 0 4px 0">How many samples each person uploaded, and when. Uploads can be
credited to someone other than their NOMAD main author (attribution overrides, kept in a file
next to the usage log); nothing here changes NOMAD.</p>
"""

STYLES = {"Stacked": True, "Side by side": False}


def _esc(text):
    return html.escape(str(text))


def _stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


class SamplesDashboardApp:
    def __init__(self):
        self.auth_manager = AuthenticationManager(URL_BASE, API_ENDPOINT)
        self.samples = samples_frame([])
        self.scope = None
        self.loaded = read_overrides()
        self.overrides = dict(self.loaded.overrides)
        self.current = {}  # the tables and figures on screen, for the exports
        self._busy = False

        self._create_widgets()
        self._setup_callbacks()
        self._refresh_uploads()
        self._auto_authenticate()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _create_widgets(self):
        self.auth_ui = AuthenticationUI(self.auth_manager)
        self.status_html = widgets.HTML()
        self.load_button = widgets.Button(
            description="Load samples", icon="database", button_style="info", disabled=True
        )
        self.summary_html = widgets.HTML()
        self.download_output = widgets.Output(layout=widgets.Layout(height="0px"))

        # Overview
        self.start_date = widgets.DatePicker(description="From:")
        self.end_date = widgets.DatePicker(description="To:")
        self.grouping = widgets.Dropdown(
            options=list(GROUPINGS), value="Monthly", description="Group by:"
        )
        self.style = widgets.ToggleButtons(options=list(STYLES), value="Stacked")
        self.use_overrides = widgets.Checkbox(
            value=True, description="Apply attribution overrides", indent=False
        )
        self.author_output = widgets.Output()
        self.time_output = widgets.Output()
        self.export_buttons = {
            key: widgets.Button(description=label, icon="download", layout={"width": "210px"})
            for key, label in (
                ("authors_csv", "Samples per author (CSV)"),
                ("authors_html", "Author plot (HTML)"),
                ("time_csv", "Samples over time (CSV)"),
                ("time_html", "Time plot (HTML)"),
                ("samples_csv", "All samples (CSV)"),
            )
        }
        overview = widgets.VBox(
            [
                widgets.HBox([self.start_date, self.end_date]),
                widgets.HBox([self.grouping, self.style, self.use_overrides]),
                self.author_output,
                self.time_output,
                widgets.HTML("<b>Download</b> (the period and settings shown above):"),
                widgets.HBox(list(self.export_buttons.values())[:3]),
                widgets.HBox(list(self.export_buttons.values())[3:]),
            ]
        )

        # Attribution
        text = {"layout": widgets.Layout(width="320px")}
        self.f_author = widgets.Text(description="Author:", placeholder="NOMAD or credited", **text)
        self.f_name = widgets.Text(description="Upload name:", **text)
        self.f_id = widgets.Text(description="Upload id:", **text)
        self.f_from = widgets.DatePicker(description="From:")
        self.f_to = widgets.DatePicker(description="To:")
        self.uploads_select = widgets.SelectMultiple(
            options=[], rows=14, layout=widgets.Layout(width="100%")
        )
        self.shown_html = widgets.HTML()
        self.select_all_button = widgets.Button(description="Select all shown")
        self.select_none_button = widgets.Button(description="Select none")
        self.new_author = widgets.Combobox(
            placeholder="Type or pick a name",
            description="Credit to:",
            ensure_option=False,
            layout=widgets.Layout(width="320px"),
        )
        self.assign_button = widgets.Button(
            description="Credit selected uploads", icon="user", button_style="warning"
        )
        self.clear_button = widgets.Button(description="Remove their overrides", icon="eraser")
        self.pending_html = widgets.HTML()
        self.save_button = widgets.Button(
            description="Save overrides", icon="save", button_style="success"
        )
        self.discard_button = widgets.Button(description="Discard changes", icon="undo")
        self.download_overrides_button = widgets.Button(
            description="Download overrides (CSV)", icon="download"
        )
        self.import_upload = widgets.FileUpload(
            accept=".csv", multiple=False, description="Import CSV"
        )
        self.attr_status = widgets.HTML()
        attribution = widgets.VBox(
            [
                widgets.HTML("<b>Find uploads</b>"),
                widgets.HBox([self.f_author, self.f_name]),
                widgets.HBox([self.f_id]),
                widgets.HBox([self.f_from, self.f_to]),
                self.shown_html,
                self.uploads_select,
                widgets.HBox([self.select_all_button, self.select_none_button]),
                widgets.HTML("<b>Change who the selected uploads are credited to</b>"),
                widgets.HBox([self.new_author, self.assign_button, self.clear_button]),
                self.pending_html,
                widgets.HBox(
                    [
                        self.save_button,
                        self.discard_button,
                        self.download_overrides_button,
                        self.import_upload,
                    ]
                ),
                self.attr_status,
            ]
        )

        self.tabs = widgets.Tab(children=[overview, attribution])
        self.tabs.titles = ("Overview", "Attribution")

        self.dashboard = widgets.VBox(
            [
                widgets.HTML(INTRO),
                manual_panel(__file__),
                self.auth_ui.get_widget(),
                self.status_html,
                self.load_button,
                self.summary_html,
                self.tabs,
                self.download_output,
            ],
            layout=widgets.Layout(max_width="1200px"),
        )

    def _setup_callbacks(self):
        self.auth_ui.set_success_callback(self._on_auth_success)
        self.load_button.on_click(lambda _b: self._guarded(self._load))
        for widget in (self.start_date, self.end_date, self.grouping, self.style):
            widget.observe(lambda _c: self._guarded(self._update_plots), names="value")
        self.use_overrides.observe(lambda _c: self._guarded(self._update_plots), names="value")
        for key, button in self.export_buttons.items():
            button.on_click(lambda _b, key=key: self._guarded(lambda: self._export(key)))
        for widget in (self.f_author, self.f_name, self.f_id, self.f_from, self.f_to):
            widget.observe(lambda _c: self._refresh_uploads(), names="value")
        self.uploads_select.observe(lambda _c: self._show_counts(), names="value")
        self.select_all_button.on_click(lambda _b: self._select(all_shown=True))
        self.select_none_button.on_click(lambda _b: self._select(all_shown=False))
        self.assign_button.on_click(lambda _b: self._guarded(lambda: self._assign(True)))
        self.clear_button.on_click(lambda _b: self._guarded(lambda: self._assign(False)))
        self.save_button.on_click(lambda _b: self._guarded(self._save))
        self.discard_button.on_click(lambda _b: self._guarded(self._discard))
        self.download_overrides_button.on_click(lambda _b: self._guarded(self._download_overrides))
        self.import_upload.observe(lambda _c: self._guarded(self._import), names="value")

    def get_dashboard(self):
        return self.dashboard

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _set_status(self, widget, message, color="#333"):
        widget.value = (
            f"<p style='color:{color};margin:4px 0'>{_esc(message)}</p>" if message else ""
        )

    def _guarded(self, action):
        """Run a callback; show its error in the app (Voila would swallow it)."""
        if self._busy:
            return
        self._busy = True
        try:
            action()
        except Exception as exc:
            logger.exception("Samples Dashboard action failed")
            self._set_status(self.status_html, f"{type(exc).__name__}: {exc}", "red")
        finally:
            self._busy = False

    def _authors(self, samples):
        if self.use_overrides.value:
            return effective_authors(samples, self.overrides)
        return samples["author_name"]

    # ── Authentication and loading ───────────────────────────────────────────

    def _auto_authenticate(self):
        if os.environ.get("JUPYTERHUB_USER"):
            self.auth_ui.auth_method_selector.value = "Token (from ENV)"
            self.auth_ui._on_auth_button_clicked(None)
        else:
            # Local use: open the connection settings so username/password can be entered
            self.auth_ui.auth_method_selector.value = "Username/Password"
            self.auth_ui._toggle_settings(None)

    def _on_auth_success(self):
        self.auth_ui.close_settings()
        self.load_button.disabled = False
        self._guarded(self._load)

    def _load(self):
        self._set_status(self.status_html, "Loading the sample entries from NOMAD ...")
        result = load_samples(self.auth_manager.url, self.auth_manager.current_token)
        self.samples, self.scope = result.samples, result.scope
        self._set_status(self.status_html, "")
        self._show_summary()
        self._refresh_uploads()
        self._update_plots()

    def _show_summary(self):
        samples = self.samples
        if self.scope == SCOPE_ADMIN:
            scope = "all uploads of the Oasis"
        else:
            scope = (
                "only the uploads this account can see (NOMAD refused the admin query: sign in "
                "with the NOMAD admin account to see all)"
            )
        self.summary_html.value = (
            f"<p style='margin:4px 0'><b>{len(samples)}</b> samples in "
            f"<b>{samples['upload_id'].nunique()}</b> uploads by "
            f"<b>{samples['author_name'].nunique()}</b> NOMAD authors; {_esc(scope)}.</p>"
        )

    # ── Overview ─────────────────────────────────────────────────────────────

    def _update_plots(self):
        if self.samples.empty:
            self.current = {}
            for output in (self.author_output, self.time_output):
                output.clear_output()
            return
        samples = filter_by_date(self.samples, self.start_date.value, self.end_date.value)
        authors = self._authors(samples)
        counts = author_counts(authors)
        table = time_counts(samples["upload_date"], authors, self.grouping.value)
        note = " (with attribution overrides)" if self.use_overrides.value else ""
        author_fig = author_figure(counts, f"Samples by author{note}")
        time_fig = time_figure(table, STYLES[self.style.value], f"Samples over time{note}")
        self.current = {
            "samples": samples.assign(credited_to=authors),
            "counts": counts,
            "table": table,
            "author_fig": author_fig,
            "time_fig": time_fig,
        }
        for output, fig in ((self.author_output, author_fig), (self.time_output, time_fig)):
            with output:
                output.clear_output(wait=True)
                if len(samples):
                    fig.show()
                else:
                    display(widgets.HTML("<p>No samples in this period.</p>"))

    def _export(self, key):
        if not self.current:
            raise ValueError("Load the samples first.")
        stamp = _stamp()
        if key == "authors_csv":
            content = csv_safe(self.current["counts"]).to_csv(index=False)
            name, mime = f"samples_per_author_{stamp}.csv", "text/csv"
        elif key == "time_csv":
            content = csv_safe(self.current["table"]).to_csv()
            name, mime = f"samples_over_time_{stamp}.csv", "text/csv"
        elif key == "samples_csv":
            content = csv_safe(self.current["samples"]).to_csv(index=False)
            name, mime = f"samples_{stamp}.csv", "text/csv"
        else:
            fig = self.current["author_fig" if key == "authors_html" else "time_fig"]
            content = fig.to_html(include_plotlyjs=True, full_html=True)
            plot = "samples_per_author" if key == "authors_html" else "samples_over_time"
            name, mime = f"{plot}_{stamp}.html", "text/html"
        start_download(self.download_output, content, name, mime)

    # ── Attribution ──────────────────────────────────────────────────────────

    def _shown_uploads(self):
        table = uploads_table(self.samples, self.overrides)
        return filter_uploads(
            table,
            author=self.f_author.value,
            upload_name=self.f_name.value,
            upload_id=self.f_id.value,
            date_from=self.f_from.value,
            date_to=self.f_to.value,
        )

    def _refresh_uploads(self):
        shown = self._shown_uploads()
        keep = set(self.uploads_select.value)
        options = []
        for row in shown.itertuples():
            day = row.upload_date.strftime("%Y-%m-%d") if pd.notna(row.upload_date) else ""
            label = f"{day}  {row.upload_name or row.upload_id}  ({row.samples} samples)  "
            label += f"NOMAD: {row.author_name}"
            if row.override:
                label += f"  →  credited to {row.override}"
            options.append((label, row.upload_id))
        self.uploads_select.options = options
        self.uploads_select.value = tuple(uid for _label, uid in options if uid in keep)
        self.new_author.options = known_authors(self.samples, self.overrides)
        self._show_counts()
        self._show_pending()

    def _show_counts(self):
        shown = len(self.uploads_select.options)
        if self.samples.empty:
            self.shown_html.value = (
                "<p style='color:#666'>Load the samples to list the uploads.</p>"
            )
            return
        self.shown_html.value = (
            f"<p style='margin:4px 0'>{shown} uploads shown, "
            f"{len(self.uploads_select.value)} selected.</p>"
        )

    def _select(self, all_shown):
        values = [uid for _label, uid in self.uploads_select.options] if all_shown else []
        self.uploads_select.value = tuple(values)

    def _assign(self, credit):
        selected = list(self.uploads_select.value)
        if not selected:
            raise ValueError("Select at least one upload in the list.")
        author = self.new_author.value.strip() if credit else ""
        if credit and not author:
            raise ValueError("Enter the name the uploads should be credited to.")
        self.overrides = set_override(self.overrides, selected, author)
        what = f"credited to {author}" if credit else "back to their NOMAD author"
        self._set_status(
            self.attr_status, f"{len(selected)} uploads {what} (not saved yet).", "#a60"
        )
        self.status_html.value = ""
        self._refresh_uploads()
        self._update_plots()

    def _show_pending(self):
        changed = changed_uploads(self.loaded.overrides, self.overrides)
        if changed:
            self.pending_html.value = (
                f"<p style='color:#a60;margin:4px 0'><b>{len(changed)} unsaved changes.</b> "
                "Save overrides keeps them for everyone; closing the page discards them.</p>"
            )
        else:
            self.pending_html.value = (
                f"<p style='color:#666;margin:4px 0'>{len(self.overrides)} overrides, all "
                f"saved in <code>{_esc(self.loaded.path)}</code>.</p>"
            )

    def _save(self):
        changed = changed_uploads(self.loaded.overrides, self.overrides)
        if not changed:
            self._set_status(self.attr_status, "Nothing to save.")
            return
        try:
            self.loaded = save_overrides(self.loaded, self.overrides)
        except OverridesChangedError as exc:
            self._set_status(self.attr_status, str(exc), "red")
            return
        self._set_status(
            self.attr_status,
            f"Saved ({len(changed)} uploads changed); the previous file is kept as "
            f"{self.loaded.path.name}.bak.",
            "green",
        )
        self._refresh_uploads()

    def _discard(self):
        self.loaded = read_overrides(self.loaded.path)
        self.overrides = dict(self.loaded.overrides)
        self._set_status(self.attr_status, "Overrides loaded again from the file.")
        self._refresh_uploads()
        self._update_plots()

    def _download_overrides(self):
        content = overrides_csv(self.overrides)
        start_download(
            self.download_output, content, f"attribution_overrides_{_stamp()}.csv", "text/csv"
        )

    def _import(self):
        files = self.import_upload.value
        if not files:
            return
        upload = files[0]
        try:
            imported = parse_overrides_csv(bytes(upload["content"]).decode("utf-8-sig"))
        finally:
            self.import_upload.value = ()
        if not imported:
            raise ValueError(f"No overrides found in {upload['name']}.")
        self.overrides = {**self.overrides, **imported}
        self._set_status(
            self.attr_status,
            f"Imported {len(imported)} overrides from {upload['name']} (not saved yet).",
            "#a60",
        )
        self._refresh_uploads()
        self._update_plots()
