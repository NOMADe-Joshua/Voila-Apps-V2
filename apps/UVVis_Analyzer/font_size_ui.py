"""
Font Size Control UI Component
Allows users to adjust font sizes for plots dynamically
"""

import ipywidgets as widgets
from IPython.display import HTML


class FontSizeUI:
    """Handles font size adjustment UI components"""

    def __init__(self, callback=None):
        """
        Initialize FontSizeUI

        Parameters:
        -----------
        callback : callable, optional
            Callback function to call when font sizes change
            Function signature: callback(axis_size, title_size, legend_size)
        """
        self.callback = callback
        self.create_widgets()

    def create_widgets(self):
        """Create font size adjustment widgets"""

        # Title
        self.title = widgets.HTML(
            "<h3 style='margin-top: 20px; margin-bottom: 10px;'>📝 Plot Font Sizes</h3>"
        )

        # Axis label font size
        self.axis_size_slider = widgets.IntSlider(
            value=12,
            min=8,
            max=24,
            step=1,
            description="Axis Labels:",
            style={"description_width": "120px"},
            layout=widgets.Layout(width="350px"),
        )
        self.axis_size_slider.observe(self._on_font_size_change, names="value")

        # Title font size
        self.title_size_slider = widgets.IntSlider(
            value=16,
            min=10,
            max=32,
            step=1,
            description="Title:",
            style={"description_width": "120px"},
            layout=widgets.Layout(width="350px"),
        )
        self.title_size_slider.observe(self._on_font_size_change, names="value")

        # Legend font size
        self.legend_size_slider = widgets.IntSlider(
            value=10,
            min=6,
            max=20,
            step=1,
            description="Legend:",
            style={"description_width": "120px"},
            layout=widgets.Layout(width="350px"),
        )
        self.legend_size_slider.observe(self._on_font_size_change, names="value")

        # Reset button
        self.reset_button = widgets.Button(
            description="Reset to Default",
            button_style="info",
            tooltip="Reset all font sizes to default values",
            layout=widgets.Layout(width="150px"),
        )
        self.reset_button.on_click(self._on_reset_click)

        # Info text
        self.info_text = widgets.HTML(
            "<p style='font-size: 11px; color: #666; margin-top: 10px;'>"
            "💡 Adjust these sliders to make plot labels more readable. "
            "Changes apply to all new plots.</p>"
        )

        # Container
        self.widget = widgets.VBox(
            [
                self.title,
                self.axis_size_slider,
                self.title_size_slider,
                self.legend_size_slider,
                widgets.HBox([self.reset_button]),
                self.info_text,
            ]
        )

    def _on_font_size_change(self, change):
        """Handle font size change"""
        if self.callback:
            self.callback(
                axis_size=self.axis_size_slider.value,
                title_size=self.title_size_slider.value,
                legend_size=self.legend_size_slider.value,
            )

    def _on_reset_click(self, button):
        """Reset font sizes to defaults"""
        self.axis_size_slider.value = 12
        self.title_size_slider.value = 16
        self.legend_size_slider.value = 10

    def get_widget(self):
        """Get the font size UI widget"""
        return self.widget

    def get_font_sizes(self):
        """Get current font size settings as a dictionary"""
        return {
            "font_size_axis": self.axis_size_slider.value,
            "font_size_title": self.title_size_slider.value,
            "font_size_legend": self.legend_size_slider.value,
        }
