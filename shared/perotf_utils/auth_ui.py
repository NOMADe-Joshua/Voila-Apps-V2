"""
Shared authentication UI for NOMAD-based notebooks and voila apps.
"""

import json

import ipywidgets as widgets
import requests

from perotf_utils.config import API_ENDPOINT, URL_BASE
from perotf_utils.plotting_utils import WidgetFactory


class AuthenticationUI:
    """Handles authentication-related UI components on top of AuthenticationManager."""

    def __init__(self, auth_manager):
        self.auth_manager = auth_manager
        self.auth_manager.set_status_callback(self._update_status)
        self.success_callback = None
        self._create_widgets()
        self._setup_observers()

    def _create_widgets(self):
        self.auth_method_selector = widgets.RadioButtons(
            options=["Username/Password", "Token (from ENV)"],
            description="Auth Method:",
            style={"description_width": "initial"},
            layout=widgets.Layout(margin="10px 0 0 0"),
        )

        self.username_input = WidgetFactory.create_text_input(
            placeholder="Enter Username (e.g., email)",
            description="Username:",
        )
        self.password_input = WidgetFactory.create_text_input(
            placeholder="Enter Password",
            description="Password:",
            password=True,
        )
        self.token_input = WidgetFactory.create_text_input(
            placeholder="Token will be read from ENV",
            description="Token:",
            width="wide",
            password=True,
        )
        self.token_input.disabled = True

        self.auth_button = WidgetFactory.create_button(
            description="Authenticate",
            button_style="info",
            tooltip="Authenticate using the selected method",
        )

        self.auth_status_label = widgets.Label(
            value="Status: Not Authenticated",
            layout=widgets.Layout(margin="5px 0 0 0"),
        )

        self.local_auth_box = widgets.VBox([self.username_input, self.password_input])
        self.token_auth_box = widgets.VBox([self.token_input])
        self.token_auth_box.layout.display = "none"

        self.auth_action_box = widgets.VBox([self.auth_button, self.auth_status_label])

        self.settings_toggle_button = WidgetFactory.create_button(
            description="▶ Connection Settings",
            min_width=False,
        )
        self.settings_toggle_button.layout.width = "200px"

        self.settings_content = widgets.VBox(
            [
                widgets.HTML(f"<p><strong>Oasis API:</strong> {URL_BASE}{API_ENDPOINT}</p>"),
                self.auth_method_selector,
                self.local_auth_box,
                self.token_auth_box,
                self.auth_action_box,
            ],
            layout=widgets.Layout(padding="10px", margin="0 0 10px 0", display="none"),
        )

        self.settings_box = widgets.VBox(
            [self.settings_toggle_button, self.settings_content],
            layout=widgets.Layout(border="1px solid #ccc", padding="10px", margin="0 0 20px 0"),
        )

    def _setup_observers(self):
        self.auth_method_selector.observe(self._on_auth_method_change, names="value")
        self.auth_button.on_click(self._on_auth_button_clicked)
        self.settings_toggle_button.on_click(self._toggle_settings)

    def _on_auth_method_change(self, change):
        if change["new"] == "Username/Password":
            self.local_auth_box.layout.display = "flex"
            self.token_auth_box.layout.display = "none"
        else:
            self.local_auth_box.layout.display = "none"
            self.token_auth_box.layout.display = "none"

        self.auth_status_label.value = "Status: Not Authenticated (Method changed)"
        self.auth_manager.clear_authentication()

    def _on_auth_button_clicked(self, _button):
        self._update_status("Status: Authenticating...", "orange")

        try:
            if self.auth_method_selector.value == "Username/Password":
                self.auth_manager.authenticate_with_credentials(
                    self.username_input.value, self.password_input.value
                )
                self.password_input.value = ""
            else:
                self.auth_manager.authenticate_with_token()

            user_info = self.auth_manager.verify_token()
            user_display = user_info.get("name", user_info.get("username", "Unknown User"))
            self._update_status(f"Status: Authenticated as {user_display} on NOMAD Oasis.", "green")

            if self.success_callback:
                self.success_callback()

        except Exception as exc:
            if isinstance(exc, ValueError):
                self._update_status(f"Status: Error - {exc}", "red")
            elif isinstance(exc, requests.exceptions.RequestException):
                error_message = f"Network/API Error: {exc}"
                if exc.response is not None:
                    try:
                        error_detail = exc.response.json().get("detail", exc.response.text)
                        if isinstance(error_detail, list):
                            error_message = f"API Error ({exc.response.status_code}): {json.dumps(error_detail)}"
                        else:
                            error_message = f"API Error ({exc.response.status_code}): {error_detail or exc.response.text}"
                    except Exception:
                        error_message = (
                            f"API Error ({exc.response.status_code}): {exc.response.text}"
                        )
                self._update_status(f"Status: {error_message}", "red")
            else:
                self._update_status(f"Status: Unexpected Error - {exc}", "red")

            self.auth_manager.clear_authentication()

    def _update_status(self, message, color=None):
        self.auth_status_label.value = message
        self.auth_status_label.style.text_color = color if color else None

    def _toggle_settings(self, _button):
        if self.settings_content.layout.display == "none":
            self.settings_content.layout.display = "flex"
            self.settings_toggle_button.description = "▼ Connection Settings"
        else:
            self.settings_content.layout.display = "none"
            self.settings_toggle_button.description = "▶ Connection Settings"

    def close_settings(self):
        self.settings_content.layout.display = "none"
        self.settings_toggle_button.description = "▶ Connection Settings"

    def set_success_callback(self, callback):
        self.success_callback = callback

    def get_widget(self):
        return self.settings_box
