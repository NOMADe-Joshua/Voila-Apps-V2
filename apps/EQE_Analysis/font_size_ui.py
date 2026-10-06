"""
Font size and line-width controls for EQE plots.
"""

import ipywidgets as widgets


class FontSizeUI:
    """UI component for font size and EQE line width settings."""

    def __init__(self, callback=None):
        self.callback = callback
        self._create_widgets()

    def _create_widgets(self):
        self.title = widgets.HTML(
            "<h3 style='margin-top: 20px; margin-bottom: 10px;'>Plot Font Sizes</h3>"
        )

        self.axis_size_input = widgets.BoundedIntText(
            value=12,
            min=8,
            max=24,
            step=1,
            description="Axis Labels:",
            style={"description_width": "120px"},
            layout=widgets.Layout(width="220px"),
        )
        self.axis_size_input.observe(self._on_change, names="value")

        self.legend_size_input = widgets.BoundedIntText(
            value=10,
            min=6,
            max=20,
            step=1,
            description="Legend:",
            style={"description_width": "120px"},
            layout=widgets.Layout(width="220px"),
        )
        self.legend_size_input.observe(self._on_change, names="value")

        self.eqe_line_width_input = widgets.BoundedFloatText(
            value=2.0,
            min=1.0,
            max=8.0,
            step=0.5,
            description="EQE Line Width:",
            style={"description_width": "120px"},
            layout=widgets.Layout(width="220px"),
        )
        self.eqe_line_width_input.observe(self._on_change, names="value")

        self.vline_width_input = widgets.BoundedFloatText(
            value=1.5,
            min=0.5,
            max=6.0,
            step=0.5,
            description="Eg Line Width:",
            style={"description_width": "120px"},
            layout=widgets.Layout(width="220px"),
        )
        self.vline_width_input.observe(self._on_change, names="value")

        self.jsc_line_width_input = widgets.BoundedFloatText(
            value=1.5,
            min=0.5,
            max=6.0,
            step=0.5,
            description="Jsc Line Width:",
            style={"description_width": "120px"},
            layout=widgets.Layout(width="220px"),
        )
        self.jsc_line_width_input.observe(self._on_change, names="value")

        self.reset_button = widgets.Button(
            description="Reset to Default",
            button_style="info",
            tooltip="Reset all settings to defaults",
            layout=widgets.Layout(width="150px"),
        )
        self.reset_button.on_click(self._on_reset)

        self.widget = widgets.VBox(
            [
                self.title,
                self.axis_size_input,
                self.legend_size_input,
                self.eqe_line_width_input,
                self.vline_width_input,
                self.jsc_line_width_input,
                widgets.HBox([self.reset_button]),
            ]
        )

    def _on_change(self, _change):
        if self.callback:
            self.callback(
                axis_size=self.axis_size_input.value,
                legend_size=self.legend_size_input.value,
                jv_line_width=self.eqe_line_width_input.value,
                vline_width=self.vline_width_input.value,
                jsc_line_width=self.jsc_line_width_input.value,
            )

    def _on_reset(self, _button):
        self.axis_size_input.value = 12
        self.legend_size_input.value = 10
        self.eqe_line_width_input.value = 2.0
        self.vline_width_input.value = 1.5
        self.jsc_line_width_input.value = 1.5

    def get_widget(self):
        return self.widget

    def get_font_sizes(self):
        return {
            "font_size_axis": self.axis_size_input.value,
            "font_size_legend": self.legend_size_input.value,
            "jv_line_width": self.eqe_line_width_input.value,
            "vline_width": self.vline_width_input.value,
            "jsc_line_width": self.jsc_line_width_input.value,
        }
