"""Reprocess Uploads: let the current experiment parser write process entries again.

Admin tool. nomad_perotf's experiment parser never overwrites a process entry it already
created, so a parser fix only reaches existing uploads once those entries are gone. This app
finds them (by default: evaporation steps stored without sources), shows them per upload,
and after a confirmation deletes their files and reprocesses each selected upload.
"""

import html
import logging
import os
import threading
from datetime import datetime

import ipywidgets as widgets
from data_manager import PROCESS_TYPES, find_plans, repair_upload

from perotf_utils.auth_manager import AuthenticationManager
from perotf_utils.auth_ui import AuthenticationUI
from perotf_utils.config import ADMIN_USERS, API_ENDPOINT, URL_BASE

logger = logging.getLogger(__name__)

OWNERS = {
    "All unpublished uploads (NOMAD admin account)": "admin",
    "My uploads": "user",
}
DEFAULT_TYPE = "Evaporation (incl. Co- and Seq-Evaporation)"

INTRO = """
<h3 style="margin:0 0 6px 0">Reprocess Uploads</h3>
<p style="margin:0 0 4px 0">The experiment parser never overwrites a process entry it already
created. To let the current parser write entries again, this app deletes their files and
reprocesses the upload; the parser then recreates them from the experiment Excel under the
same file name and entry id.</p>
<ul style="margin:0 0 4px 18px;padding:0">
<li>Only entries the experiment entry lists as created by the parser are touched, never
entries made by hand in the ELN.</li>
<li>Changes made by hand in the ELN to a recreated entry are lost.</li>
<li>Published uploads are skipped (NOMAD does not allow deleting their files).</li>
<li>The fixed parser must already run on this Oasis, otherwise the entries come back
unchanged.</li>
</ul>
"""


def _escape(text):
    return html.escape(str(text))


class UploadRow:
    """One upload in the result list: a checkbox plus its files."""

    def __init__(self, plan, on_change):
        self.plan = plan
        self.checkbox = widgets.Checkbox(
            value=True,
            description=f"{plan.upload_name}  ({len(plan.files)} files)",
            indent=False,
            layout=widgets.Layout(width="auto"),
        )
        self.checkbox.observe(lambda _change: on_change(), names="value")
        items = "".join(
            f"<li><code>{_escape(entry.mainfile)}</code> {_escape(entry.name)}"
            + (" <i>(no sources)</i>" if entry.has_sources is False else "")
            + "</li>"
            for entry in sorted(plan.entries, key=lambda entry: entry.mainfile)
        )
        self.details = widgets.HTML(
            f"<details style='margin:0 0 6px 22px'><summary>upload id "
            f"<code>{_escape(plan.upload_id)}</code></summary>"
            f"<ul style='margin:2px 0 0 0'>{items}</ul></details>"
        )
        self.widget = widgets.VBox([self.checkbox, self.details])


class ReprocessUploadsApp:
    def __init__(self):
        self.auth_manager = AuthenticationManager(URL_BASE, API_ENDPOINT)
        self.rows: list[UploadRow] = []
        self.owner = "admin"
        self._stop = threading.Event()
        self._worker = None
        self._log_lines: list[str] = []

        self._create_widgets()
        self._setup_callbacks()
        self._auto_authenticate()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _create_widgets(self):
        self.auth_ui = AuthenticationUI(self.auth_manager)
        self.status_html = widgets.HTML()

        is_admin = os.environ.get("NOMAD_CLIENT_USER", "") in ADMIN_USERS
        self.owner_select = widgets.RadioButtons(
            options=list(OWNERS),
            value=list(OWNERS)[0 if is_admin else 1],
            description="Search in:",
            style={"description_width": "initial"},
        )
        self.type_checks = {
            label: widgets.Checkbox(value=label == DEFAULT_TYPE, description=label, indent=False)
            for label in PROCESS_TYPES
        }
        self.only_without_sources = widgets.Checkbox(
            value=True,
            description="Evaporation: only entries without stored sources",
            indent=False,
        )
        self.search_button = widgets.Button(
            description="Search", button_style="info", icon="search", disabled=True
        )

        self.results_html = widgets.HTML()
        self.rows_box = widgets.VBox([])
        self.select_all_button = widgets.Button(description="Select all")
        self.select_none_button = widgets.Button(description="Select none")
        self.selection_html = widgets.HTML()
        self.timeout_input = widgets.BoundedIntText(
            value=15,
            min=1,
            max=240,
            description="Wait per step [min]:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="230px"),
        )
        self.repair_button = widgets.Button(
            description="Repair selected ...", button_style="warning", disabled=True
        )
        self.confirm_html = widgets.HTML()
        self.confirm_button = widgets.Button(
            description="Yes, delete and reprocess", button_style="danger", icon="trash"
        )
        self.cancel_button = widgets.Button(description="Cancel")
        self.confirm_box = widgets.VBox(
            [self.confirm_html, widgets.HBox([self.confirm_button, self.cancel_button])],
            layout=widgets.Layout(display="none", border="1px solid #e0a800", padding="8px"),
        )

        self.progress = widgets.IntProgress(value=0, min=0, max=1, description="Uploads:")
        self.stop_button = widgets.Button(
            description="Stop after this upload", icon="stop", disabled=True
        )
        self.log_html = widgets.HTML()
        self.summary_html = widgets.HTML()
        self.run_box = widgets.VBox(
            [
                widgets.HBox([self.progress, self.stop_button]),
                self.log_html,
                self.summary_html,
            ],
            layout=widgets.Layout(display="none"),
        )

        self.dashboard = widgets.VBox(
            [
                widgets.HTML(INTRO),
                self.auth_ui.get_widget(),
                self.status_html,
                widgets.HTML("<h4 style='margin:10px 0 4px 0'>1. Search</h4>"),
                self.owner_select,
                widgets.VBox(list(self.type_checks.values())),
                self.only_without_sources,
                self.search_button,
                widgets.HTML("<h4 style='margin:10px 0 4px 0'>2. Choose uploads</h4>"),
                self.results_html,
                widgets.HBox([self.select_all_button, self.select_none_button]),
                self.rows_box,
                self.selection_html,
                widgets.HTML("<h4 style='margin:10px 0 4px 0'>3. Repair</h4>"),
                widgets.HBox([self.timeout_input, self.repair_button]),
                self.confirm_box,
                self.run_box,
            ],
            layout=widgets.Layout(max_width="1100px"),
        )

    def _setup_callbacks(self):
        self.auth_ui.set_success_callback(self._on_auth_success)
        self.search_button.on_click(self._on_search)
        self.select_all_button.on_click(lambda _b: self._select_all(True))
        self.select_none_button.on_click(lambda _b: self._select_all(False))
        self.repair_button.on_click(self._on_repair_clicked)
        self.confirm_button.on_click(self._on_confirm)
        self.cancel_button.on_click(self._on_cancel)
        self.stop_button.on_click(self._on_stop)

    def get_dashboard(self):
        return self.dashboard

    # ── Authentication ───────────────────────────────────────────────────────

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
        self.search_button.disabled = False
        self._set_status("Signed in. Choose what to search for and press Search.")

    def _set_status(self, message, color="#333"):
        self.status_html.value = f"<p style='color:{color};margin:4px 0'>{_escape(message)}</p>"

    # ── Search ───────────────────────────────────────────────────────────────

    def _selected_types(self):
        return [PROCESS_TYPES[label] for label, check in self.type_checks.items() if check.value]

    def _on_search(self, _button):
        entry_types = self._selected_types()
        if not entry_types:
            self._set_status("Choose at least one process type.", "red")
            return
        self.owner = OWNERS[self.owner_select.value]
        self.search_button.disabled = True
        self.repair_button.disabled = True
        self.confirm_box.layout.display = "none"
        self.rows_box.children = ()
        self.results_html.value = ""
        self._set_status("Searching ...")
        try:
            result = find_plans(
                self.auth_manager.url,
                self.auth_manager.current_token,
                entry_types,
                self.owner,
                only_without_sources=self.only_without_sources.value,
            )
        except Exception as exc:
            logger.exception("Search failed")
            hint = (
                " The 'All uploads' search only works with the NOMAD admin account."
                if self.owner == "admin"
                else ""
            )
            self._set_status(f"Search failed: {exc}.{hint}", "red")
            return
        finally:
            self.search_button.disabled = False

        self.rows = [UploadRow(plan, self._update_selection) for plan in result.plans]
        self.rows_box.children = tuple(row.widget for row in self.rows)
        notes = []
        if result.skipped_with_sources:
            notes.append(f"{result.skipped_with_sources} evaporation entries with sources left out")
        if result.skipped_not_from_parser:
            notes.append(
                f"{result.skipped_not_from_parser} entries not created by the experiment parser "
                "left out"
            )
        found = sum(len(plan.files) for plan in result.plans)
        self.results_html.value = (
            f"<p style='margin:4px 0'><b>{found} files in {len(result.plans)} uploads.</b> "
            + (_escape("; ".join(notes)) + "." if notes else "")
            + "</p>"
        )
        self._set_status("Search done." if result.plans else "Nothing to repair.")
        self._update_selection()

    def _select_all(self, value):
        for row in self.rows:
            row.checkbox.value = value
        self._update_selection()

    def _selected_plans(self):
        return [row.plan for row in self.rows if row.checkbox.value]

    def _update_selection(self):
        plans = self._selected_plans()
        files = sum(len(plan.files) for plan in plans)
        self.selection_html.value = (
            f"<p style='margin:4px 0'>Selected: {files} files in {len(plans)} uploads</p>"
            if self.rows
            else ""
        )
        busy = self._worker is not None and self._worker.is_alive()
        self.repair_button.disabled = busy or not plans

    # ── Repair ───────────────────────────────────────────────────────────────

    def _on_repair_clicked(self, _button):
        plans = self._selected_plans()
        files = sum(len(plan.files) for plan in plans)
        self.confirm_html.value = (
            f"<p style='margin:0 0 6px 0'><b>Delete {files} files in {len(plans)} uploads and "
            "reprocess these uploads?</b><br>The experiment parser then writes the entries "
            "again. Manual changes to these entries in the ELN are lost.</p>"
        )
        self.confirm_box.layout.display = "flex"

    def _on_cancel(self, _button):
        self.confirm_box.layout.display = "none"

    def _on_stop(self, _button):
        self._stop.set()
        self.stop_button.disabled = True
        self._log("Stopping after the current upload ...")

    def _on_confirm(self, _button):
        plans = self._selected_plans()
        self.confirm_box.layout.display = "none"
        if not plans:
            return
        for widget in (self.search_button, self.repair_button, self.select_all_button):
            widget.disabled = True
        self.select_none_button.disabled = True
        for row in self.rows:
            row.checkbox.disabled = True
        self._stop.clear()
        self._log_lines = []
        self.summary_html.value = ""
        self.progress.max, self.progress.value = len(plans), 0
        self.stop_button.disabled = False
        self.run_box.layout.display = "flex"
        # a thread keeps the page responsive (stop button) during the long waits
        self._worker = threading.Thread(target=self._run, args=(plans,), daemon=True)
        self._worker.start()

    def _run(self, plans):
        url, token = self.auth_manager.url, self.auth_manager.current_token
        timeout_s = self.timeout_input.value * 60
        results = []
        try:
            for plan in plans:
                if self._stop.is_set():
                    self._log("Stopped.")
                    break
                self._log(f"<b>{_escape(plan.upload_name)}</b> ({len(plan.files)} files)")
                result = repair_upload(
                    url,
                    token,
                    plan,
                    self.owner,
                    timeout_s=timeout_s,
                    log=lambda message: self._log("&nbsp;&nbsp;" + _escape(message)),
                )
                results.append(result)
                self._log("&nbsp;&nbsp;" + self._result_text(result))
                self.progress.value += 1
        except Exception as exc:  # never let the thread die silently
            logger.exception("Repair run failed")
            self._log(f"<span style='color:red'>Run aborted: {_escape(exc)}</span>")
        finally:
            self.summary_html.value = self._summary(results)
            self.stop_button.disabled = True
            for widget in (self.search_button, self.select_all_button, self.select_none_button):
                widget.disabled = False
            for row in self.rows:
                row.checkbox.disabled = False
            self._update_selection()

    def _log(self, line_html):
        stamp = datetime.now().strftime("%H:%M:%S")
        self._log_lines.append(f"<span style='color:#888'>{stamp}</span> {line_html}")
        self.log_html.value = (
            "<div style='max-height:320px;overflow:auto;font-family:monospace;font-size:12px;"
            "border:1px solid #ddd;padding:6px'>" + "<br>".join(self._log_lines) + "</div>"
        )

    @staticmethod
    def _result_text(result):
        if result.error:
            return f"<span style='color:red'>failed: {_escape(result.error)}</span>"
        parts = [f"{len(result.deleted)} deleted, reprocess {_escape(result.process_status)}"]
        if result.missing:
            parts.append(f"{len(result.missing)} not written again")
        if result.without_sources:
            parts.append(f"{len(result.without_sources)} evaporation still without sources")
        color = "green" if result.ok and not result.without_sources else "#b8860b"
        return f"<span style='color:{color}'>{_escape(', '.join(parts))}</span>"

    @staticmethod
    def _summary(results):
        if not results:
            return ""
        rows = "".join(
            "<tr>"
            f"<td>{_escape(result.upload_name)}</td>"
            f"<td>{len(result.deleted)}</td>"
            f"<td>{_escape(result.process_status or '-')}</td>"
            f"<td>{_escape(', '.join(result.missing) or '-')}</td>"
            f"<td>{_escape(', '.join(result.without_sources) or '-')}</td>"
            f"<td>{_escape(result.error or result.status_message or '')}</td>"
            "</tr>"
            for result in results
        )
        return (
            "<h4 style='margin:10px 0 4px 0'>Result</h4>"
            "<table style='border-collapse:collapse;font-size:12px' border='1' cellpadding='4'>"
            "<tr><th>Upload</th><th>Deleted</th><th>Reprocess</th><th>Not written again</th>"
            "<th>Still without sources</th><th>Message</th></tr>"
            f"{rows}</table>"
        )
