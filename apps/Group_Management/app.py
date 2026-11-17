"""Group Management (admin): NOMAD user groups in a Voila app.

Replaces the group dashboard notebook of the old admin scripts, which stopped working with
NOMAD 1.4 (password login by GET removed, member roles added). Lists every group with its
members and roles; adds and removes members, creates and deletes groups. Each change is
checked and shown first and runs only after a second click; data_manager describes what
happens then (fresh read, change log first, read back).
"""

import html
import logging
import os

import ipywidgets as widgets
from data_manager import (
    ASSIGNABLE_ROLES,
    OWNER,
    AddPlan,
    CreatePlan,
    DeletePlan,
    RemovePlan,
    apply_add,
    apply_create,
    apply_delete,
    apply_remove,
    change_log_path,
    display_name,
    get_users,
    list_groups,
    plan_add,
    plan_create,
    plan_delete,
    plan_remove,
    read_log,
)

from perotf_utils.auth_manager import AuthenticationManager
from perotf_utils.auth_ui import AuthenticationUI
from perotf_utils.config import API_ENDPOINT, URL_BASE
from perotf_utils.manual import manual_panel

logger = logging.getLogger(__name__)

INTRO = """
<h3 style="margin:0 0 6px 0">Group Management</h3>
<p style="margin:0 0 4px 0">NOMAD user groups: who is in which group, and adding or removing
members, creating and deleting groups. Every change is checked and shown first and only runs
after a second click; the app then reads the group again, writes, and reads it back.</p>
"""

TAB_TITLES = ("Add members", "Remove members", "Create group", "Delete group")


def _esc(text):
    return html.escape(str(text))


def _list(items):
    return "<ul style='margin:2px 0 6px 0'>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


class GroupManagementApp:
    def __init__(self):
        self.auth_manager = AuthenticationManager(URL_BASE, API_ENDPOINT)
        self.groups = []
        self.users: dict[str, dict] = {}
        self._pending = None  # the plan shown in the confirmation box
        self._busy = False

        self._create_widgets()
        self._setup_callbacks()
        self._auto_authenticate()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _create_widgets(self):
        self.auth_ui = AuthenticationUI(self.auth_manager)
        self.status_html = widgets.HTML()
        self.account_html = widgets.HTML()

        self.reload_button = widgets.Button(
            description="Reload groups", icon="refresh", button_style="info", disabled=True
        )
        self.filter_text = widgets.Text(
            placeholder="Filter by name",
            description="Filter:",
            layout=widgets.Layout(width="320px"),
        )
        self.group_select = widgets.Select(
            options=[], rows=10, layout=widgets.Layout(width="100%", max_width="760px")
        )
        self.group_html = widgets.HTML()

        role_options = [(role, role) for role in ASSIGNABLE_ROLES]
        self.add_emails = widgets.Textarea(
            placeholder="Email addresses of the new members, one per line",
            layout=widgets.Layout(width="100%", max_width="560px", height="110px"),
        )
        self.add_role = widgets.Dropdown(options=role_options, value="member", description="Role:")
        self.add_check = widgets.Button(description="Check ...", icon="search")
        add_tab = widgets.VBox(
            [
                widgets.HTML("Add to the group selected above:"),
                self.add_emails,
                self.add_role,
                self.add_check,
            ]
        )

        self.remove_select = widgets.SelectMultiple(
            options=[], rows=8, layout=widgets.Layout(width="100%", max_width="560px")
        )
        self.remove_check = widgets.Button(description="Check ...", icon="search")
        remove_tab = widgets.VBox(
            [
                widgets.HTML(
                    "Members of the selected group to remove (Ctrl or Shift for several; "
                    "the owner is not listed and cannot be removed):"
                ),
                self.remove_select,
                self.remove_check,
            ]
        )

        self.create_name = widgets.Text(
            description="Name:", layout=widgets.Layout(width="100%", max_width="560px")
        )
        self.create_description = widgets.Text(
            description="Description:",
            placeholder="optional",
            layout=widgets.Layout(width="100%", max_width="560px"),
        )
        self.create_emails = widgets.Textarea(
            placeholder="Optional: email addresses of the first members, one per line",
            layout=widgets.Layout(width="100%", max_width="560px", height="90px"),
        )
        self.create_role = widgets.Dropdown(
            options=role_options, value="member", description="Role:"
        )
        self.create_check = widgets.Button(description="Check ...", icon="search")
        create_tab = widgets.VBox(
            [
                widgets.HTML("A new group; you become its owner."),
                self.create_name,
                self.create_description,
                self.create_emails,
                self.create_role,
                self.create_check,
            ]
        )

        self.delete_name = widgets.Text(
            description="Confirm name:",
            placeholder="type the group name exactly",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="100%", max_width="560px"),
        )
        self.delete_check = widgets.Button(description="Check ...", icon="search")
        delete_tab = widgets.VBox(
            [
                widgets.HTML(
                    "Deletes the group selected above. Uploads shared with the group lose "
                    "that access; this cannot be undone."
                ),
                self.delete_name,
                self.delete_check,
            ]
        )

        self.tabs = widgets.Tab(children=[add_tab, remove_tab, create_tab, delete_tab])
        self.tabs.titles = TAB_TITLES

        self.confirm_html = widgets.HTML()
        self.confirm_button = widgets.Button(description="Yes", button_style="danger")
        self.cancel_button = widgets.Button(description="Cancel")
        self.confirm_box = widgets.VBox(
            [self.confirm_html, widgets.HBox([self.confirm_button, self.cancel_button])],
            layout=widgets.Layout(display="none", border="1px solid #e0a800", padding="8px"),
        )
        self.result_html = widgets.HTML()

        self.log_button = widgets.Button(description="Show change log", icon="list")
        self.log_html = widgets.HTML()

        self.dashboard = widgets.VBox(
            [
                widgets.HTML(INTRO),
                manual_panel(__file__),
                self.auth_ui.get_widget(),
                self.account_html,
                self.status_html,
                widgets.HTML("<h4 style='margin:10px 0 4px 0'>Groups</h4>"),
                widgets.HBox([self.reload_button, self.filter_text]),
                self.group_select,
                self.group_html,
                widgets.HTML("<h4 style='margin:10px 0 4px 0'>Change</h4>"),
                self.tabs,
                self.confirm_box,
                self.result_html,
                widgets.HTML("<h4 style='margin:10px 0 4px 0'>Change log</h4>"),
                self.log_button,
                self.log_html,
            ],
            layout=widgets.Layout(max_width="1000px"),
        )
        self._set_actions_enabled(False)

    def _setup_callbacks(self):
        self.auth_ui.set_success_callback(self._on_auth_success)
        self.reload_button.on_click(lambda _b: self._guarded(self._load_groups))
        self.filter_text.observe(lambda _c: self._refresh_group_options(), names="value")
        self.group_select.observe(self._on_group_change, names="value")
        self.add_check.on_click(lambda _b: self._guarded(self._check_add))
        self.remove_check.on_click(lambda _b: self._guarded(self._check_remove))
        self.create_check.on_click(lambda _b: self._guarded(self._check_create))
        self.delete_check.on_click(lambda _b: self._guarded(self._check_delete))
        self.confirm_button.on_click(lambda _b: self._guarded(self._confirm))
        self.cancel_button.on_click(lambda _b: self._cancel_pending())
        self.log_button.on_click(lambda _b: self._guarded(self._show_log))
        # A plan is only valid for what was checked: any change of the input drops it.
        for widget in (
            self.add_emails,
            self.add_role,
            self.remove_select,
            self.create_name,
            self.create_description,
            self.create_emails,
            self.create_role,
            self.delete_name,
        ):
            widget.observe(lambda _c: self._cancel_pending(), names="value")
        self.tabs.observe(lambda _c: self._cancel_pending(), names="selected_index")

    def get_dashboard(self):
        return self.dashboard

    # ── Helpers ──────────────────────────────────────────────────────────────

    @property
    def _url(self):
        return self.auth_manager.url

    @property
    def _token(self):
        return self.auth_manager.current_token

    def _actor(self):
        info = self.auth_manager.current_user_info or {}
        return info.get("username") or os.environ.get("NOMAD_CLIENT_USER") or "unknown"

    def _set_status(self, message, color="#333"):
        self.status_html.value = f"<p style='color:{color};margin:4px 0'>{_esc(message)}</p>"

    def _guarded(self, action):
        """Run a callback; show its error in the app (Voila would swallow it)."""
        if self._busy:
            return
        self._busy = True
        try:
            action()
        except Exception as exc:
            logger.exception("Group Management action failed")
            self._set_status(f"{type(exc).__name__}: {exc}", "red")
        finally:
            self._busy = False

    def _set_actions_enabled(self, enabled):
        for button in (self.add_check, self.remove_check, self.create_check, self.delete_check):
            button.disabled = not enabled

    def _name(self, user_id):
        return display_name(self.users.get(user_id), user_id)

    def _user_label(self, user):
        username = user.get("username")
        email = user.get("email")
        extra = ", ".join(_esc(part) for part in (username, email) if part)
        return f"{_esc(display_name(user))}" + (f" <small>({extra})</small>" if extra else "")

    def _selected_group(self):
        group_id = self.group_select.value
        return next((group for group in self.groups if group.group_id == group_id), None)

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
        self.reload_button.disabled = False
        self._set_actions_enabled(True)
        info = self.auth_manager.current_user_info or {}
        who = _esc(info.get("username") or display_name(info))
        if info.get("is_admin"):
            note = "NOMAD treats this account as the admin: every group can be changed."
        else:
            note = (
                "This is not the NOMAD admin account: NOMAD lets you change only groups you "
                "own or maintain, and delete only groups you own."
            )
        self.account_html.value = f"<p style='margin:4px 0'>Signed in as <b>{who}</b>. {note}</p>"
        self._guarded(self._load_groups)

    # ── Groups ───────────────────────────────────────────────────────────────

    def _load_groups(self, select_id=None):
        self._set_status("Loading groups ...")
        keep = select_id or self.group_select.value
        self.groups = list_groups(self._url, self._token)
        ids = {uid for group in self.groups for uid in group.member_ids}
        missing = ids - set(self.users)
        if missing:
            self.users.update(get_users(self._url, self._token, sorted(missing)))
        self._refresh_group_options(keep)
        count = len(self.groups)
        self._set_status(f"{count} group{'' if count == 1 else 's'} loaded.", "green")

    def _refresh_group_options(self, keep=None):
        keep = keep or self.group_select.value
        text = self.filter_text.value.strip().lower()
        shown = [g for g in self.groups if not text or text in g.group_name.lower()]
        options = [
            (f"{g.group_name}  ({len(g.members)} members, owner {self._name(g.owner)})", g.group_id)
            for g in shown
        ]
        self.group_select.options = options
        ids = [group_id for _label, group_id in options]
        self.group_select.value = keep if keep in ids else None
        self._show_group()

    def _on_group_change(self, _change):
        self._cancel_pending()
        self.delete_name.value = ""
        self._show_group()

    def _show_group(self):
        group = self._selected_group()
        if group is None:
            self.group_html.value = "<p style='color:#666'>No group selected.</p>"
            self.remove_select.options = []
            return
        rows = "".join(
            f"<tr><td>{_esc(self._name(m.user_id))}</td>"
            f"<td>{_esc((self.users.get(m.user_id) or {}).get('username', ''))}</td>"
            f"<td>{'<b>owner</b>' if m.role == OWNER else _esc(m.role)}</td></tr>"
            for m in sorted(group.members, key=lambda m: (m.role != OWNER, self._name(m.user_id)))
        )
        description = (
            f"<p style='margin:2px 0'>{_esc(group.description)}</p>" if group.description else ""
        )
        roles_note = (
            ""
            if group.has_roles
            else "<p style='color:red'>NOMAD reports no member roles: this app will not "
            "change the group.</p>"
        )
        self.group_html.value = (
            f"<div style='border:1px solid #ddd;padding:6px 10px;margin:6px 0'>"
            f"<b>{_esc(group.group_name)}</b> <small>id <code>{_esc(group.group_id)}</code>"
            f"</small>{description}{roles_note}"
            f"<table style='border-collapse:collapse;margin-top:4px'>"
            f"<tr><th style='text-align:left;padding-right:16px'>Name</th>"
            f"<th style='text-align:left;padding-right:16px'>Username</th>"
            f"<th style='text-align:left'>Role</th></tr>{rows}</table></div>"
        )
        self.remove_select.options = [
            (f"{self._name(m.user_id)}  ({m.role})", m.user_id)
            for m in sorted(group.members, key=lambda m: self._name(m.user_id))
            if m.role != OWNER
        ]

    def _require_group(self):
        group = self._selected_group()
        if group is None:
            raise ValueError("Select a group in the list above first.")
        return group

    # ── Checks (nothing is written here) ─────────────────────────────────────

    def _lookup_notes(self, lookup):
        notes = ""
        if lookup.not_found:
            notes += "<p style='margin:4px 0'>No NOMAD account with these addresses:</p>"
            notes += _list(_esc(email) for email in lookup.not_found)
        if lookup.invalid:
            notes += "<p style='margin:4px 0'>Not an email address, ignored:</p>"
            notes += _list(_esc(text) for text in lookup.invalid)
        return notes

    def _check_add(self):
        group = self._require_group()
        self._set_status("Looking up the addresses ...")
        plan = plan_add(self._url, self._token, group, self.add_emails.value, self.add_role.value)
        for user in plan.lookup.found:
            self.users.setdefault(user["user_id"], user)
        text = ""
        if plan.to_add:
            text += (
                f"<p style='margin:4px 0'>Add to <b>{_esc(group.group_name)}</b> as "
                f"<b>{_esc(plan.role)}</b>:</p>" + _list(self._user_label(u) for u in plan.to_add)
            )
        if plan.already:
            text += "<p style='margin:4px 0'>Members already (left as they are):</p>"
            text += _list(self._user_label(u) for u in plan.already)
        text += self._lookup_notes(plan.lookup)
        self._set_status("")
        if not plan.to_add:
            self.result_html.value = text or "<p>Enter at least one email address.</p>"
            return
        self._ask(plan, text, f"Yes, add {len(plan.to_add)}", "warning")

    def _check_remove(self):
        group = self._require_group()
        plan = plan_remove(group, list(self.remove_select.value))
        text = f"<p style='margin:4px 0'>Remove from <b>{_esc(group.group_name)}</b>:</p>"
        text += _list(
            f"{_esc(self._name(uid))} <small>({_esc(group.role_of(uid))})</small>"
            for uid in plan.user_ids
        )
        self._ask(plan, text, f"Yes, remove {len(plan.user_ids)}", "danger")

    def _check_create(self):
        info = self.auth_manager.current_user_info or {}
        self._set_status("Checking ...")
        plan = plan_create(
            self._url,
            self._token,
            self.create_name.value,
            self.create_description.value,
            self.create_emails.value,
            self.create_role.value,
            info.get("user_id"),
            self.groups,
        )
        for user in plan.lookup.found:
            self.users.setdefault(user["user_id"], user)
        text = (
            f"<p style='margin:4px 0'>Create the group <b>{_esc(plan.group_name)}</b>"
            + (f" ({_esc(plan.description)})" if plan.description else "")
            + f" with you ({_esc(self._actor())}) as owner"
        )
        others = [u for u in plan.lookup.found if u["user_id"] != plan.owner_id]
        if others:
            text += f" and these {_esc(plan.role)}s:</p>" + _list(
                self._user_label(u) for u in others
            )
        else:
            text += " and no other members.</p>"
        text += self._lookup_notes(plan.lookup)
        self._set_status("")
        self._ask(plan, text, "Yes, create the group", "warning")

    def _check_delete(self):
        group = self._require_group()
        plan = plan_delete(group, self.delete_name.value)
        text = (
            f"<p style='margin:4px 0'>Delete the group <b>{_esc(group.group_name)}</b> "
            f"(id <code>{_esc(group.group_id)}</code>, owner {_esc(self._name(group.owner))}, "
            f"{len(group.members)} members).</p>"
            "<p style='margin:4px 0;color:#a00'>Uploads shared with this group lose that "
            "access. A group created again gets a new id, so they would have to be shared "
            "again. The change log keeps the member list.</p>"
        )
        self._ask(plan, text, "Yes, delete the group", "danger")

    # ── Confirmation and writing ─────────────────────────────────────────────

    def _ask(self, plan, text, button_label, style):
        self._pending = plan
        self.result_html.value = ""
        self.confirm_html.value = text
        self.confirm_button.description = button_label
        self.confirm_button.button_style = style
        self.confirm_box.layout.display = "flex"

    def _cancel_pending(self):
        self._pending = None
        self.confirm_box.layout.display = "none"

    def _confirm(self):
        plan = self._pending
        self._cancel_pending()
        if plan is None:
            return
        self._set_actions_enabled(False)
        self._set_status("Writing to NOMAD ...")
        try:
            result = self._apply(plan)
        finally:
            self._set_actions_enabled(True)
        color = "green" if result.ok else "red"
        self.result_html.value = f"<p style='color:{color};margin:4px 0'>{_esc(result.message)}</p>"
        self._set_status("")
        if result.ok:
            self._clear_inputs(plan)
        select_id = result.group.group_id if result.group else None
        self._load_groups(select_id)

    def _apply(self, plan):
        actor = self._actor()
        if isinstance(plan, AddPlan):
            return apply_add(self._url, self._token, plan, actor)
        if isinstance(plan, RemovePlan):
            return apply_remove(self._url, self._token, plan, actor)
        if isinstance(plan, CreatePlan):
            return apply_create(self._url, self._token, plan, actor)
        if isinstance(plan, DeletePlan):
            return apply_delete(self._url, self._token, plan, actor)
        raise TypeError(f"Unknown plan {type(plan).__name__}")

    def _clear_inputs(self, plan):
        if isinstance(plan, AddPlan):
            self.add_emails.value = ""
        elif isinstance(plan, CreatePlan):
            self.create_name.value = ""
            self.create_description.value = ""
            self.create_emails.value = ""
        elif isinstance(plan, DeletePlan):
            self.delete_name.value = ""

    # ── Change log ───────────────────────────────────────────────────────────

    def _show_log(self):
        records = read_log()
        if not records:
            self.log_html.value = f"<p>No changes logged yet ({_esc(change_log_path())}).</p>"
            return
        rows = "".join(
            f"<tr><td>{_esc(r.get('time', ''))}</td><td>{_esc(r.get('actor', ''))}</td>"
            f"<td>{_esc(r.get('action', ''))}</td><td>{_esc(r.get('group_name', ''))}</td>"
            f"<td>{_esc(r.get('stage', ''))}</td>"
            f"<td>{_esc(r.get('error') or '; '.join(r.get('problems') or []))}</td></tr>"
            for r in records
        )
        self.log_html.value = (
            f"<p style='margin:4px 0'>Last {len(records)} entries, newest first "
            f"(<code>{_esc(change_log_path())}</code>; each line also holds the member lists "
            "before and after):</p>"
            "<table style='border-collapse:collapse;font-size:90%'>"
            "<tr><th align='left'>Time (UTC)</th><th align='left'>By</th>"
            "<th align='left'>Action</th><th align='left'>Group</th>"
            "<th align='left'>Stage</th><th align='left'>Note</th></tr>"
            f"{rows}</table>"
        )
