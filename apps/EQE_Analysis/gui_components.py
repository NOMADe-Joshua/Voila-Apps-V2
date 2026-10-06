"""
Minimal GUI components for the EQE dashboard.
"""

import base64
import io
import json
import zipfile

import ipywidgets as widgets
import plotly.express as px
import requests
from IPython.display import HTML, clear_output, display

from perotf_utils.config import API_ENDPOINT, URL_BASE


class AuthenticationUI:
    """Authentication panel compatible with SimpleAuthManager."""

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

        self.username_input = widgets.Text(
            placeholder="Enter Username (e.g., email)",
            description="Username:",
            style={"description_width": "initial"},
        )
        self.password_input = widgets.Password(
            placeholder="Enter Password",
            description="Password:",
            style={"description_width": "initial"},
        )
        self.token_input = widgets.Password(
            placeholder="Token will be read from ENV",
            description="Token:",
            style={"description_width": "initial"},
        )
        self.token_input.disabled = True

        self.auth_button = widgets.Button(
            description="Authenticate",
            button_style="info",
            layout=widgets.Layout(min_width="150px"),
        )
        self.auth_status_label = widgets.Label(value="Status: Not Authenticated")

        self.local_auth_box = widgets.VBox([self.username_input, self.password_input])
        self.token_auth_box = widgets.VBox([self.token_input])
        self.token_auth_box.layout.display = "none"

        self.settings_toggle_button = widgets.Button(
            description="Ôû╝ Connection Settings", layout=widgets.Layout(width="200px")
        )
        self.settings_content = widgets.VBox(
            [
                widgets.HTML(f"<p><strong>Oasis API:</strong> {URL_BASE}{API_ENDPOINT}</p>"),
                self.auth_method_selector,
                self.local_auth_box,
                self.token_auth_box,
                widgets.VBox([self.auth_button, self.auth_status_label]),
            ],
            layout=widgets.Layout(padding="10px", margin="0 0 10px 0"),
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

    def _on_auth_button_clicked(self, _b):
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
            self._update_status(f"Status: Authenticated as {user_display} on SE Oasis.", "green")
            if self.success_callback:
                self.success_callback()
        except Exception as e:
            if (
                isinstance(e, requests.exceptions.RequestException)
                and getattr(e, "response", None) is not None
            ):
                try:
                    detail = e.response.json().get("detail", e.response.text)
                except Exception:
                    detail = e.response.text
                req = getattr(e.response, "request", None)
                req_method = getattr(req, "method", "?") if req else "?"
                req_url = getattr(req, "url", "?") if req else "?"
                self._update_status(
                    f"Status: API Error ({e.response.status_code}) [{req_method} {req_url}]: {detail}",
                    "red",
                )
            else:
                self._update_status(f"Status: Error - {e}", "red")
            self.auth_manager.clear_authentication()

    def _update_status(self, message, color=None):
        self.auth_status_label.value = message
        self.auth_status_label.style.text_color = color

    def _toggle_settings(self, _b):
        if self.settings_content.layout.display == "none":
            self.settings_content.layout.display = "flex"
            self.settings_toggle_button.description = "Ôû╝ Connection Settings"
        else:
            self.settings_content.layout.display = "none"
            self.settings_toggle_button.description = "ÔûÂ Connection Settings"

    def set_success_callback(self, callback):
        self.success_callback = callback

    def close_settings(self):
        self.settings_content.layout.display = "none"
        self.settings_toggle_button.description = "ÔûÂ Connection Settings"

    def get_widget(self):
        return self.settings_box


class SaveUI:
    """Download helpers and optional buttons."""

    def __init__(self):
        self.save_plots_button = widgets.Button(
            description="Save All Plots", button_style="primary"
        )
        self.save_data_button = widgets.Button(description="Save Data", button_style="info")
        self.save_all_button = widgets.Button(
            description="Save Data & Plots", button_style="success"
        )
        self.download_output = widgets.Output(
            layout=widgets.Layout(border="1px solid #eee", padding="10px", margin="10px 0 0 0")
        )

    def trigger_download(self, content, filename, content_type="text/json"):
        content_b64 = base64.b64encode(
            content if isinstance(content, bytes) else content.encode()
        ).decode()
        data_url = f"data:{content_type};charset=utf-8;base64,{content_b64}"
        js_code = (
            "var a = document.createElement('a');"
            f"a.setAttribute('download', '{filename}');"
            f"a.setAttribute('href', '{data_url}');"
            "a.click();"
        )
        with self.download_output:
            clear_output()
            display(HTML(f"<script>{js_code}</script>"))

    def create_plots_zip(self, figures, names):
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for fig, name in zip(figures, names):
                safe_name = str(name).replace(" ", "_")
                if not safe_name.endswith(".html"):
                    safe_name = f"{safe_name}.html"
                html_str = fig.to_html(include_plotlyjs="cdn")
                zip_file.writestr(safe_name, html_str)

        zip_buffer.seek(0)
        self.trigger_download(
            zip_buffer.getvalue(), "eqe_plots.zip", content_type="application/zip"
        )
        return zip_buffer.getvalue()

    def set_save_callbacks(self, plots_callback, data_callback, all_callback):
        self.save_plots_button.on_click(plots_callback)
        self.save_data_button.on_click(data_callback)
        self.save_all_button.on_click(all_callback)

    def get_widget(self):
        return widgets.VBox(
            [
                widgets.HTML("<h3>Save Plots and Data</h3>"),
                widgets.HBox([self.save_plots_button, self.save_data_button, self.save_all_button]),
                self.download_output,
            ]
        )


class ColorSchemeSelector:
    """Color palette selector with preview for EQE curves."""

    def __init__(self):
        self.color_schemes = {
            "Viridis": px.colors.sequential.Viridis,
            "Plasma": px.colors.sequential.Plasma,
            "Inferno": px.colors.sequential.Inferno,
            "Magma": px.colors.sequential.Magma,
            "Plotly": px.colors.qualitative.Plotly,
            "D3": px.colors.qualitative.D3,
            "Set2": px.colors.qualitative.Set2,
        }
        self.selected_scheme = "Viridis"
        self.num_colors = 8
        self._create_widgets()

    def _create_widgets(self):
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

        self.widget = widgets.VBox(
            [
                widgets.HBox([self.color_dropdown, self.sampling_dropdown]),
                self.num_colors_slider,
                self.preview_output,
            ]
        )
        self._update_preview()

    def _on_color_change(self, change):
        self.selected_scheme = change["new"]
        self._update_preview()

    def _on_sampling_change(self, _change):
        self._update_preview()

    def _on_num_colors_change(self, change):
        self.num_colors = int(change["new"])
        self._update_preview()

    def set_num_colors(self, n):
        """Update slider and internal count without triggering redundant previews."""
        n = max(self.num_colors_slider.min, min(self.num_colors_slider.max, int(n)))
        self.num_colors = n
        self.num_colors_slider.value = n

    def _interpolate_hex(self, c1, c2, t):
        c1 = c1.lstrip("#")
        c2 = c2.lstrip("#")
        r1, g1, b1 = int(c1[0:2], 16), int(c1[2:4], 16), int(c1[4:6], 16)
        r2, g2, b2 = int(c2[0:2], 16), int(c2[2:4], 16), int(c2[4:6], 16)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _ensure_hex(self, color):
        if isinstance(color, str) and color.startswith("#") and len(color) >= 7:
            return color[:7]
        if isinstance(color, str) and color.startswith("rgb"):
            nums = color[color.find("(") + 1 : color.find(")")].split(",")[:3]
            try:
                r, g, b = [int(float(n.strip())) for n in nums]
                return f"#{r:02x}{g:02x}{b:02x}"
            except Exception:
                return "#808080"
        return "#808080"

    def _generate_continuous_colors(self, num_colors):
        palette = [self._ensure_hex(c) for c in self.color_schemes[self.selected_scheme]]
        if num_colors <= len(palette):
            step = (len(palette) - 1) / max(1, (num_colors - 1))
            return [palette[int(round(i * step))] for i in range(num_colors)]

        out = []
        for i in range(num_colors):
            pos = i / max(1, (num_colors - 1))
            p_idx = pos * (len(palette) - 1)
            lo = int(p_idx)
            hi = min(lo + 1, len(palette) - 1)
            t = p_idx - lo
            out.append(
                self._interpolate_hex(palette[lo], palette[hi], t) if lo != hi else palette[lo]
            )
        return out

    def get_colors(self, num_colors=None, sampling="sequential"):
        if num_colors is None:
            num_colors = self.num_colors
        palette = self.color_schemes[self.selected_scheme]
        if sampling == "even" and len(palette) >= num_colors:
            if num_colors == 1:
                return [palette[len(palette) // 2]]
            idxs = [
                int(round(i * (len(palette) - 1) / (num_colors - 1))) for i in range(num_colors)
            ]
            return [palette[i] for i in idxs]
        return self._generate_continuous_colors(num_colors)

    def set_num_colors(self, num_colors):
        self.num_colors_slider.value = int(max(2, min(20, num_colors)))

    def _update_preview(self):
        colors = self.get_colors(num_colors=self.num_colors, sampling=self.sampling_dropdown.value)
        with self.preview_output:
            clear_output(wait=True)
            html_preview = '<div style="display:flex;align-items:center;gap:4px;padding:4px;">'
            for color in colors[:20]:
                html_preview += f'<span style="background:{color};width:20px;height:20px;display:inline-block;border:1px solid #333;"></span>'
            html_preview += "</div>"
            display(HTML(html_preview))

    def get_widget(self):
        return widgets.VBox(
            [
                widgets.HTML("<h4>Color Scheme Selection</h4>"),
                widgets.HTML(
                    "<p style='font-size: 12px; color: #666;'>Select a palette and number of colors.</p>"
                ),
                self.widget,
            ]
        )
