"""
Common Widgets Module
Contains the app's generic, reusable UI components - copied from JV-Analysis.
"""

__author__ = "Joshua Damm"
__institution__ = "KIT"
__created__ = "December 2025"

import base64
import io
import json
import zipfile

import ipywidgets as widgets
import requests
from IPython.display import HTML, clear_output, display

from perotf_utils.config import API_ENDPOINT, URL_BASE


class AuthenticationUI:
    """Handles all authentication-related UI components"""

    def __init__(self, auth_manager):
        self.auth_manager = auth_manager
        self.auth_manager.set_status_callback(self._update_status)
        self._create_widgets()
        self._setup_observers()

    def _create_widgets(self):
        """Create all authentication widgets"""
        self.auth_method_selector = widgets.RadioButtons(
            options=["Username/Password", "Token (from ENV)"],
            description="Auth Method:",
            style={"description_width": "initial"},
            layout=widgets.Layout(margin="10px 0 0 0"),
        )

        self.username_input = widgets.Text(
            placeholder="Enter Username (e.g., email)", description="Username:"
        )

        self.password_input = widgets.Password(
            placeholder="Enter Password", description="Password:"
        )

        self.token_input = widgets.Text(
            placeholder="Token will be read from ENV", description="Token:", password=True
        )
        self.token_input.disabled = True

        self.auth_button = widgets.Button(
            description="Authenticate",
            button_style="info",
            layout=widgets.Layout(min_width="150px"),
        )

        self.auth_status_label = widgets.Label(
            value="Status: Not Authenticated", layout=widgets.Layout(margin="5px 0 0 0")
        )

        self.local_auth_box = widgets.VBox([self.username_input, self.password_input])
        self.token_auth_box = widgets.VBox([self.token_input])
        self.token_auth_box.layout.display = "none"

        self.auth_action_box = widgets.VBox([self.auth_button, self.auth_status_label])

        self.settings_toggle_button = widgets.Button(
            description="Ôû╝ Connection Settings", layout=widgets.Layout(width="200px")
        )

        self.settings_content = widgets.VBox(
            [
                widgets.HTML(f"<p><strong>Oasis API:</strong> {URL_BASE}{API_ENDPOINT}</p>"),
                self.auth_method_selector,
                self.local_auth_box,
                self.token_auth_box,
                self.auth_action_box,
            ],
            layout=widgets.Layout(padding="10px", margin="0 0 10px 0"),
        )

        self.settings_box = widgets.VBox(
            [self.settings_toggle_button, self.settings_content],
            layout=widgets.Layout(border="1px solid #ccc", padding="10px", margin="0 0 20px 0"),
        )

    def _setup_observers(self):
        """Setup event observers"""
        self.auth_method_selector.observe(self._on_auth_method_change, names="value")
        self.auth_button.on_click(self._on_auth_button_clicked)
        self.settings_toggle_button.on_click(self._toggle_settings)

    def _on_auth_method_change(self, change):
        """Handle authentication method change"""
        if change["new"] == "Username/Password":
            self.local_auth_box.layout.display = "flex"
            self.token_auth_box.layout.display = "none"
        else:
            self.local_auth_box.layout.display = "none"
            self.token_auth_box.layout.display = "none"

        self.auth_status_label.value = "Status: Not Authenticated (Method changed)"
        self.auth_manager.clear_authentication()

    def _on_auth_button_clicked(self, b):
        """Handle authentication button click"""
        self._update_status("Status: Authenticating...", "orange")

        try:
            if self.auth_method_selector.value == "Username/Password":
                token = self.auth_manager.authenticate_with_credentials(
                    self.username_input.value, self.password_input.value
                )
                self.password_input.value = ""
            else:
                token = self.auth_manager.authenticate_with_token()

            user_info = self.auth_manager.verify_token()
            user_display = user_info.get("name", user_info.get("username", "Unknown User"))
            self._update_status(f"Status: Authenticated as {user_display} on SE Oasis.", "green")

            if hasattr(self, "success_callback") and self.success_callback:
                self.success_callback()

        except Exception as e:
            if isinstance(e, ValueError):
                self._update_status(f"Status: Error - {e}", "red")
            elif isinstance(e, requests.exceptions.RequestException):
                error_message = f"Network/API Error: {e}"
                self._update_status(f"Status: {error_message}", "red")
            else:
                self._update_status(f"Status: Unexpected Error - {e}", "red")

            self.auth_manager.clear_authentication()

    def _update_status(self, message, color=None):
        """Update status label"""
        self.auth_status_label.value = message
        if color:
            self.auth_status_label.style.text_color = color

    def _toggle_settings(self, b):
        """Toggle settings visibility"""
        if self.settings_content.layout.display == "none":
            self.settings_content.layout.display = "flex"
            self.settings_toggle_button.description = "Ôû╝ Connection Settings"
        else:
            self.settings_content.layout.display = "none"
            self.settings_toggle_button.description = "ÔûÂ Connection Settings"

    def close_settings(self):
        """Close settings panel"""
        self.settings_content.layout.display = "none"
        self.settings_toggle_button.description = "ÔûÂ Connection Settings"

    def set_success_callback(self, callback):
        """Set callback to execute on successful authentication"""
        self.success_callback = callback

    def get_widget(self):
        """Get the main settings widget"""
        return self.settings_box


class SaveUI:
    """Handles save functionality UI"""

    def __init__(self):
        self._create_widgets()

    def _create_widgets(self):
        """Create save widgets"""
        self.save_plots_button = widgets.Button(
            description="Save All Plots",
            button_style="primary",
            layout=widgets.Layout(min_width="150px"),
        )

        self.save_data_button = widgets.Button(
            description="Save Data", button_style="info", layout=widgets.Layout(min_width="150px")
        )

        self.save_all_button = widgets.Button(
            description="Save Data & Plots",
            button_style="success",
            layout=widgets.Layout(min_width="150px"),
        )

        self.download_output = widgets.Output(
            layout=widgets.Layout(border="1px solid #eee", padding="10px")
        )

    def trigger_download(self, content, filename, content_type="text/json"):
        """Trigger file download"""
        content_b64 = base64.b64encode(
            content if isinstance(content, bytes) else content.encode()
        ).decode()
        data_url = f"data:{content_type};charset=utf-8;base64,{content_b64}"
        js_code = f"""
            var a = document.createElement('a');
            a.setAttribute('download', '{filename}');
            a.setAttribute('href', '{data_url}');
            a.click()
        """
        with self.download_output:
            clear_output()
            display(HTML(f"<script>{js_code}</script>"))

    def create_plots_zip(self, figures, names):
        """Create zip file with plots"""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for fig, name in zip(figures, names):
                try:
                    html_str = fig.to_html(include_plotlyjs="cdn")
                    zip_file.writestr(name, html_str)

                    try:
                        import plotly.io as pio

                        img_bytes = pio.to_image(fig, format="png")
                        zip_file.writestr(name.replace(".html", ".png"), img_bytes)
                    except:
                        pass
                except Exception as e:
                    print(f"Error saving {name}: {e}")

        zip_buffer.seek(0)
        return zip_buffer.getvalue()

    def set_save_callbacks(self, plots_callback, data_callback, all_callback):
        """Set callbacks for save buttons"""
        self.save_plots_button.on_click(plots_callback)
        self.save_data_button.on_click(data_callback)
        self.save_all_button.on_click(all_callback)

    def get_widget(self):
        """Get the main save widget"""
        return widgets.VBox(
            [
                widgets.HTML("<h3>Save Plots and Data</h3>"),
                widgets.HBox([self.save_plots_button, self.save_data_button, self.save_all_button]),
                self.download_output,
            ]
        )


class ColorSchemeSelector:
    """Color scheme selector with preview and dynamic color generation - copied from JV-Analysis"""

    def __init__(self):
        import plotly.express as px

        self.color_schemes = {
            "Viridis": px.colors.sequential.Viridis,
            "Plasma": px.colors.sequential.Plasma,
            "Inferno": px.colors.sequential.Inferno,
            "Magma": px.colors.sequential.Magma,
            "Blues": px.colors.sequential.Blues,
            "Reds": px.colors.sequential.Reds,
            "Greens": px.colors.sequential.Greens,
            "Plotly": px.colors.qualitative.Plotly,
            "D3": px.colors.qualitative.D3,
            "Set1": px.colors.qualitative.Set1,
            "Default (Current)": [
                "rgba(93, 164, 214, 0.7)",
                "rgba(255, 144, 14, 0.7)",
                "rgba(44, 160, 101, 0.7)",
                "rgba(255, 65, 54, 0.7)",
                "rgba(207, 114, 255, 0.7)",
                "rgba(127, 96, 0, 0.7)",
            ],
        }

        self.selected_scheme = "Default (Current)"
        self.num_colors = 6  # NEW: User can specify number of colors
        self._create_widgets()

    def _create_widgets(self):
        """Create widgets"""
        self.color_dropdown = widgets.Dropdown(
            options=list(self.color_schemes.keys()),
            value=self.selected_scheme,
            description="Color Scheme:",
            style={"description_width": "initial"},
        )

        # NEW: Slider to select number of colors
        self.num_colors_slider = widgets.IntSlider(
            value=6,
            min=2,
            max=20,
            step=1,
            description="# Colors:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="300px"),
        )

        self.preview_output = widgets.Output()
        self.color_dropdown.observe(self._on_color_change, names="value")
        self.num_colors_slider.observe(self._on_num_colors_change, names="value")  # NEW
        self._update_preview()

        # NEW: Reorganized layout with slider
        self.widget = widgets.VBox(
            [widgets.HBox([self.color_dropdown, self.num_colors_slider]), self.preview_output]
        )

    def _on_color_change(self, change):
        """Handle color change"""
        self.selected_scheme = change["new"]
        self._update_preview()

    # NEW: Handle number of colors change
    def _on_num_colors_change(self, change):
        """Handle number of colors change"""
        self.num_colors = change["new"]
        self._update_preview()

    def _update_preview(self):
        """Update preview"""
        with self.preview_output:
            clear_output(wait=True)
            colors = self.get_colors(num_colors=self.num_colors)

            # NEW: Show number of colors being used
            html = f'<p style="margin: 5px 0; font-size: 12px; color: #666;">Generating {len(colors)} colors</p>'
            html += '<div style="display: flex; flex-wrap: wrap;">'
            for color in colors:
                html += f'<span style="background-color: {color}; width: 40px; height: 30px; display: inline-block; margin: 2px; border: 1px solid #ccc;"></span>'
            html += "</div>"
            display(HTML(html))

    def _interpolate_color(self, hex_color1, hex_color2, factor):
        """
        NEW: Interpolate between two colors (supports both hex and rgba formats)
        factor: 0.0 = color1, 1.0 = color2
        """

        # Convert hex to RGB
        def hex_to_rgb(color):
            """Convert color from hex or rgba format to RGB tuple"""
            if isinstance(color, str):
                # Handle rgba(r, g, b, a) format
                if color.startswith("rgba"):
                    # Extract RGBA values: rgba(93, 164, 214, 0.7)
                    import re

                    match = re.match(
                        r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", color
                    )
                    if match:
                        r, g, b, a = match.groups()
                        return (int(r) / 255.0, int(g) / 255.0, int(b) / 255.0)

                # Handle hex format: #RRGGBB
                color = color.lstrip("#")
                if len(color) >= 6:
                    return tuple(int(color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))

            # Fallback: return neutral color if parsing fails
            return (0.5, 0.5, 0.5)

        # Convert RGB to hex
        def rgb_to_hex(r, g, b):
            return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))

        rgb1 = hex_to_rgb(hex_color1)
        rgb2 = hex_to_rgb(hex_color2)

        # Linear interpolation
        r = rgb1[0] + (rgb2[0] - rgb1[0]) * factor
        g = rgb1[1] + (rgb2[1] - rgb1[1]) * factor
        b = rgb1[2] + (rgb2[2] - rgb1[2]) * factor

        return rgb_to_hex(r, g, b)

    def _generate_continuous_colors(self, num_colors):
        """
        NEW: Generate smooth color gradient from continuous palette

        Args:
            num_colors: Number of colors to generate

        Returns:
            List of hex colors evenly distributed across the palette
        """
        # Get base palette for the selected scheme
        base_palette = self.color_schemes[self.selected_scheme]

        if num_colors <= len(base_palette):
            # If requested colors <= available colors, just select evenly
            step = (len(base_palette) - 1) / (num_colors - 1) if num_colors > 1 else 0
            # NEW: Ensure all colors are converted to hex format
            selected_colors = [base_palette[int(i * step)] for i in range(num_colors)]
            return [self._ensure_hex_format(color) for color in selected_colors]
        else:
            # If requested colors > available colors, interpolate between palette colors
            colors = []

            for i in range(num_colors):
                # Position in the palette (0.0 to 1.0)
                position = i / (num_colors - 1) if num_colors > 1 else 0

                # Map position to base palette
                palette_index = position * (len(base_palette) - 1)
                lower_index = int(palette_index)
                upper_index = min(lower_index + 1, len(base_palette) - 1)

                # Interpolation factor between the two neighboring palette colors
                factor = palette_index - lower_index

                # Get the two colors from palette
                color1 = base_palette[lower_index]
                color2 = base_palette[upper_index]

                # Interpolate between them
                if factor == 0 or lower_index == upper_index:
                    interpolated = self._ensure_hex_format(color1)
                else:
                    interpolated = self._interpolate_color(color1, color2, factor)

                colors.append(interpolated)

            return colors

    # NEW: Helper method to ensure color is in hex format
    def _ensure_hex_format(self, color):
        """
        Convert color to hex format if it's in rgba format

        Args:
            color: Color string (hex or rgba format)

        Returns:
            Color in hex format (#RRGGBB)
        """
        if isinstance(color, str):
            # Already hex format
            if color.startswith("#"):
                return color

            # Convert rgba format to hex
            if color.startswith("rgba"):
                import re

                match = re.match(
                    r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", color
                )
                if match:
                    r, g, b, a = match.groups()
                    return "#{:02x}{:02x}{:02x}".format(int(r), int(g), int(b))

        # Fallback: return gray if conversion fails
        return "#808080"

    def get_colors(self, num_colors=None):
        """Get colors from selected scheme

        Args:
            num_colors: Number of colors to generate (if None, uses slider value)

        Returns:
            List of hex colors
        """
        if num_colors is None:
            num_colors = self.num_colors

        # NEW: Use continuous color generation for all palettes
        return self._generate_continuous_colors(num_colors)

    def get_widget(self):
        """Get widget"""
        return widgets.VBox(
            [
                widgets.HTML("<h4>Color Scheme Selection</h4>"),
                widgets.HTML(
                    "<p style='font-size: 12px; color: #666;'>Select a palette and adjust the number of colors. Continuous palettes will generate smooth gradients.</p>"
                ),
                self.widget,
            ]
        )

    # NEW: Method to programmatically set number of colors
    def set_num_colors(self, num_colors):
        """
        Set the number of colors to generate

        Args:
            num_colors: Number of colors (will be clamped to 2-20)
        """
        num_colors = max(2, min(20, num_colors))  # Clamp to valid range
        self.num_colors_slider.value = num_colors
        # Preview will update automatically via the observer
