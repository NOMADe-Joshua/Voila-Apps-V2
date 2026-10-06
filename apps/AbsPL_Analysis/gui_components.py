"""
GUI components for modular AbsPL analysis app.
"""

import html
import json
import uuid

import ipywidgets as widgets
import plotly.express as px
from IPython.display import HTML, Javascript, clear_output, display


class AbsPLGUIComponents:
    def __init__(self):
        self.data_loaded = False
        self.filter_options = {
            "measurement_types": [],
            "samples": [],
            "laser_spot_sizes": [],
            "cycles": [],
            "numeric_columns": [],
        }
        self._filter_rows = []
        self.selection_rows = []
        self._auto_apply_callback = None
        self._suspend_auto_apply = False

        self.output_messages = widgets.Output(
            layout=widgets.Layout(border="1px solid #d0d5dd", padding="8px")
        )
        self.output_plots = widgets.Output()
        self.output_diagnostics = widgets.HTML(value="")

        self._build_filter_widgets()
        self._build_plot_widgets()

    def _build_filter_widgets(self):
        self.selection_rows_container = widgets.VBox([])
        self.add_filter_row_button = widgets.Button(
            description="Add Selection", button_style="info"
        )
        self.clear_filter_rows_button = widgets.Button(description="Clear Selections")
        self.apply_filters_button = widgets.Button(
            description="Apply Filters", button_style="primary"
        )
        self.auto_apply_toggle = widgets.Checkbox(value=False, description="Apply instantly")

        self.add_filter_row_button.on_click(self._add_selection_row)
        self.clear_filter_rows_button.on_click(self._clear_selection_rows)

        self.filter_panel = widgets.VBox(
            [
                widgets.HTML("<h3>Filter Measurements</h3>"),
                widgets.HTML(
                    "<p style='margin: 0 0 8px 0;'>Define optional dropdown filters per row: Sample -> Type -> Spot size -> Cycle.</p>"
                ),
                widgets.HTML(
                    "<p style='margin: 0 0 8px 0; color: #666;'>If no specific filter is selected, all loaded data is used.</p>"
                ),
                widgets.HBox(
                    [
                        self.add_filter_row_button,
                        self.clear_filter_rows_button,
                        self.apply_filters_button,
                        self.auto_apply_toggle,
                    ]
                ),
                self.selection_rows_container,
            ]
        )

    def set_auto_apply_callback(self, callback):
        self._auto_apply_callback = callback

    def _trigger_auto_apply(self):
        if self._suspend_auto_apply:
            return
        if not self.auto_apply_toggle.value:
            return
        if self._auto_apply_callback is not None:
            self._auto_apply_callback()

    def _build_plot_widgets(self):
        self.plot_rows = []
        self.plot_rows_container = widgets.VBox([])
        self.trace_order_values = []

        # Define plot presets for AbsPL
        self.plot_presets = {
            "Default": [
                ("PL (only)", "", ""),
                ("PL + PL (sweep ~1 sun)", "", ""),
                ("Sweep", "", ""),
                ("LuQY vs Laser Intensity", "", ""),
            ],
            "PL": [
                ("PL (only)", "", ""),
                ("PL + PL (sweep ~1 sun)", "", ""),
            ],
            "Sweep Analysis": [
                ("Sweep", "", ""),
                ("LuQY vs Laser Intensity", "", ""),
            ],
        }

        self.add_plot_button = widgets.Button(description="Add Plot", button_style="success")
        self.clear_plots_button = widgets.Button(description="Clear Plot Rows")
        self.create_plots_button = widgets.Button(
            description="Create Plots", button_style="primary"
        )

        self.preset_dropdown = widgets.Dropdown(
            options=list(self.plot_presets.keys()),
            value="Default",
            description="Presets:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="200px"),
        )
        self.load_preset_button = widgets.Button(description="Load Preset", button_style="info")

        self.color_selector = ColorSchemeSelector()
        self._create_trace_order_section()

        self.add_plot_button.on_click(self._add_plot_row)
        self.clear_plots_button.on_click(self._clear_plot_rows)
        self.load_preset_button.on_click(self._load_preset)

        self.plot_panel = widgets.VBox(
            [
                widgets.HTML("<h3>Select Plots</h3>"),
                widgets.HBox([self.preset_dropdown, self.load_preset_button]),
                widgets.HBox(
                    [self.add_plot_button, self.clear_plots_button, self.create_plots_button]
                ),
                self.color_selector.get_widget(),
                self.trace_order_section,
                self.plot_rows_container,
                self.output_plots,
            ]
        )

        self._load_preset(None)

    def _create_trace_order_section(self):
        self.trace_order_state = widgets.Text(value="[]", layout=widgets.Layout(display="none"))
        self.trace_order_state.add_class("abspl-trace-order-state")
        self.trace_order_container = widgets.HTML(value="")

        self.trace_order_section = widgets.VBox(
            [
                widgets.HTML("<b>Trace Order (Drag & Drop)</b>"),
                widgets.HTML(
                    "<p style='margin: 0 0 8px 0; color: #666;'>Reorder samples to control plotting order and legend order.</p>"
                ),
                self.trace_order_container,
                self.trace_order_state,
            ],
            layout=widgets.Layout(
                border="1px solid #ddd",
                padding="10px",
                margin="8px 0",
                display="none",
            ),
        )

    def _update_trace_order_widget(self, values):
        self.trace_order_values = [str(v) for v in values if v not in (None, "")]
        if not self.trace_order_values:
            self.trace_order_section.layout.display = "none"
            self.trace_order_state.value = "[]"
            self.trace_order_container.value = ""
            return

        self.trace_order_section.layout.display = "flex"
        self.trace_order_state.value = json.dumps(self.trace_order_values)

        table_id = f"abspl-order-tbody-{uuid.uuid4().hex[:8]}"

        rows = ""
        for idx, value in enumerate(self.trace_order_values):
            escaped_value = html.escape(value, quote=True)
            rows += (
                f"<tr class='abspl-order-row' draggable='true' data-index='{idx}'>"
                f"<td style='width:24px;text-align:center;color:#999;cursor:grab;'>≡</td>"
                f"<td style='padding:8px 10px;'><span class='abspl-order-idx'>{idx + 1}</span></td>"
                f"<td style='padding:8px 10px;'>{escaped_value}</td>"
                "</tr>"
            )

        self.trace_order_container.value = (
            "<style>"
            ".abspl-order-table{width:100%;border-collapse:collapse;}"
            ".abspl-order-table td{border-bottom:1px solid #eee;}"
            ".abspl-order-row.drag-over{background:#eef6ff;border-top:2px solid #3b82f6;}"
            "</style>"
            f"<table class='abspl-order-table'><tbody id='{table_id}'>"
            f"{rows}"
            "</tbody></table>"
        )

        js_code = """
        (function(){
            function initDragDrop(attempt){
                const tbody = document.querySelector('#__TABLE_ID__');
                if(!tbody){
                    if(attempt < 20){
                        setTimeout(function(){ initDragDrop(attempt + 1); }, 120);
                    }
                    return;
                }
                const rows = Array.from(tbody.querySelectorAll('tr.abspl-order-row'));
                let dragged = null;
                const sourceValues = __SOURCE_VALUES__;

                function syncState(){
                    const ordered = Array.from(tbody.querySelectorAll('tr.abspl-order-row'))
                        .map(r => {
                            const idx = parseInt(r.getAttribute('data-index'), 10);
                            if(Number.isNaN(idx) || idx < 0 || idx >= sourceValues.length) return null;
                            return sourceValues[idx];
                        })
                        .filter(v => !!v);
                    const stateInput = document.querySelector('.abspl-trace-order-state input, .abspl-trace-order-state textarea');
                    if(stateInput){
                        stateInput.value = JSON.stringify(ordered);
                        stateInput.dispatchEvent(new Event('input', { bubbles: true }));
                        stateInput.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    Array.from(tbody.querySelectorAll('tr.abspl-order-row')).forEach((row, i) => {
                        const idx = row.querySelector('.abspl-order-idx');
                        if(idx) idx.textContent = String(i+1);
                    });
                }

                rows.forEach(row => {
                    row.addEventListener('dragstart', function(e){ dragged=this; this.style.opacity='0.5'; e.dataTransfer.effectAllowed='move'; });
                    row.addEventListener('dragend', function(){ this.style.opacity='1'; rows.forEach(r => r.classList.remove('drag-over')); });
                    row.addEventListener('dragover', function(e){ e.preventDefault(); this.classList.add('drag-over'); });
                    row.addEventListener('dragleave', function(){ this.classList.remove('drag-over'); });
                    row.addEventListener('drop', function(e){
                        e.preventDefault(); this.classList.remove('drag-over');
                        if(!dragged || dragged===this) return;
                        const all = Array.from(tbody.querySelectorAll('tr.abspl-order-row'));
                        const di = all.indexOf(dragged); const ti = all.indexOf(this);
                        if(di < ti) this.parentNode.insertBefore(dragged, this.nextSibling);
                        else this.parentNode.insertBefore(dragged, this);
                        syncState();
                    });
                });
                syncState();
            }
            initDragDrop(0);
        })();
        """
        js_code = js_code.replace("__TABLE_ID__", table_id)
        js_code = js_code.replace("__SOURCE_VALUES__", json.dumps(self.trace_order_values))
        display(Javascript(js_code))

    def _with_all_option(self, values):
        return [("All", "__all__")] + [(str(v), v) for v in values]

    def _add_selection_row(self, _):
        sample_options = self._with_all_option(self.filter_options.get("samples", []))
        sample_dd = widgets.Dropdown(
            options=sample_options,
            value="__all__",
            description="Sample",
            layout=widgets.Layout(width="320px"),
        )
        type_dd = widgets.Dropdown(
            options=[("All", "__all__")],
            value="__all__",
            description="Type",
            layout=widgets.Layout(width="260px"),
        )
        spot_dd = widgets.Dropdown(
            options=[("All", "__all__")],
            value="__all__",
            description="Spot",
            layout=widgets.Layout(width="240px"),
        )
        cycle_dd = widgets.Dropdown(
            options=[("All", "__all__")],
            value="__all__",
            description="Cycle",
            layout=widgets.Layout(width="200px"),
        )
        remove_btn = widgets.Button(
            description="Remove", button_style="danger", layout=widgets.Layout(width="90px")
        )

        row = {
            "sample": sample_dd,
            "type": type_dd,
            "spot": spot_dd,
            "cycle": cycle_dd,
            "remove": remove_btn,
        }

        sample_dd.observe(
            lambda _c, r=row: self._on_selection_row_changed(r, source="sample"), names="value"
        )
        type_dd.observe(
            lambda _c, r=row: self._on_selection_row_changed(r, source="type"), names="value"
        )
        spot_dd.observe(
            lambda _c, r=row: self._on_selection_row_changed(r, source="spot"), names="value"
        )
        cycle_dd.observe(lambda _c: self._trigger_auto_apply(), names="value")

        def _remove(_btn):
            self.selection_rows = [x for x in self.selection_rows if x is not row]
            self._render_selection_rows()

        remove_btn.on_click(_remove)

        self.selection_rows.append(row)
        self._update_row_options(row, source="sample")
        self._render_selection_rows()
        self._trigger_auto_apply()

    def _clear_selection_rows(self, _):
        self.selection_rows = []
        self._render_selection_rows()
        self._trigger_auto_apply()

    def _on_selection_row_changed(self, row, source="sample"):
        self._update_row_options(row, source=source)
        self._trigger_auto_apply()

    def _render_selection_rows(self):
        boxes = []
        for row in self.selection_rows:
            boxes.append(
                widgets.HBox([row["sample"], row["type"], row["spot"], row["cycle"], row["remove"]])
            )
        self.selection_rows_container.children = tuple(boxes)

    def _update_row_options(self, row, source="sample"):
        rows = self._filter_rows
        if not rows:
            row["type"].options = [("All", "__all__")]
            row["spot"].options = [("All", "__all__")]
            row["cycle"].options = [("All", "__all__")]
            row["type"].value = "__all__"
            row["spot"].value = "__all__"
            row["cycle"].value = "__all__"
            return

        sample_val = row["sample"].value
        type_val = row["type"].value
        spot_val = row["spot"].value

        if sample_val != "__all__":
            rows_after_sample = [r for r in rows if r["sample_id"] == sample_val]
        else:
            rows_after_sample = rows

        type_values = sorted({r["measurement_type"] for r in rows_after_sample})
        type_options = self._with_all_option(type_values)
        row["type"].options = type_options
        row["type"].value = type_val if any(v == type_val for _, v in type_options) else "__all__"

        type_selected = row["type"].value
        if type_selected != "__all__":
            rows_after_type = [
                r for r in rows_after_sample if r["measurement_type"] == type_selected
            ]
        else:
            rows_after_type = rows_after_sample

        spot_values = sorted({r["laser_spot_size"] for r in rows_after_type})
        spot_options = self._with_all_option(spot_values)
        row["spot"].options = spot_options
        row["spot"].value = spot_val if any(v == spot_val for _, v in spot_options) else "__all__"

        spot_selected = row["spot"].value
        if spot_selected != "__all__":
            rows_after_spot = [r for r in rows_after_type if r["laser_spot_size"] == spot_selected]
        else:
            rows_after_spot = rows_after_type

        cycle_values = sorted({r["cycle_number"] for r in rows_after_spot})
        cycle_options = self._with_all_option(cycle_values)
        current_cycle = row["cycle"].value
        row["cycle"].options = cycle_options
        row["cycle"].value = (
            current_cycle if any(v == current_cycle for _, v in cycle_options) else "__all__"
        )

    def _add_plot_row(self, _):
        kind = widgets.Dropdown(
            options=[
                "PL (only)",
                "PL + PL (sweep ~1 sun)",
                "Sweep",
                "LuQY vs Laser Intensity",
                "QFLS vs Laser Intensity",
                "PLQY + QFLS vs Laser Intensity",
            ],
            value="PL (only)",
            description="Plot",
            layout=widgets.Layout(width="300px"),
        )
        opt_a = widgets.Dropdown(description="A", layout=widgets.Layout(width="240px"))
        opt_b = widgets.Dropdown(description="B", layout=widgets.Layout(width="240px"))
        opt_c = widgets.Dropdown(description="C", layout=widgets.Layout(width="240px"))
        include_sweep = widgets.Checkbox(
            value=True,
            description="Show nearest sweep (~1 sun)",
            indent=False,
            layout=widgets.Layout(width="260px"),
        )
        legend_table = widgets.Checkbox(
            value=False,
            description="Legend as table below",
            indent=False,
            layout=widgets.Layout(width="220px"),
        )
        fit_enabled = widgets.Checkbox(
            value=False,
            description="Linear fit",
            indent=False,
            layout=widgets.Layout(width="130px"),
        )
        fit_model = widgets.Dropdown(
            options=[("Gaussian", "gaussian"), ("Voigt", "voigt")],
            value="gaussian",
            description="Peak fit",
            layout=widgets.Layout(width="220px", display="none"),
        )
        fit_mode = widgets.Dropdown(
            options=[("Auto", "auto"), ("Manual", "manual")],
            value="auto",
            description="Fit mode",
            layout=widgets.Layout(width="220px", display="none"),
        )
        fit_xmin = widgets.Text(value="", description="xmin", layout=widgets.Layout(width="170px"))
        fit_xmax = widgets.Text(value="", description="xmax", layout=widgets.Layout(width="170px"))
        fit_curve_dropdown = widgets.Dropdown(
            options=[("All curves", "__all__")],
            value="__all__",
            description="Curve",
            layout=widgets.Layout(width="280px", display="none"),
        )
        fit_curve_min = widgets.Text(
            value="", description="xmin", layout=widgets.Layout(width="170px", display="none")
        )
        fit_curve_max = widgets.Text(
            value="", description="xmax", layout=widgets.Layout(width="170px", display="none")
        )
        fit_curve_set = widgets.Button(
            description="Set range",
            button_style="info",
            layout=widgets.Layout(width="110px", display="none"),
        )
        fit_curve_ranges_html = widgets.HTML(value="", layout=widgets.Layout(display="none"))
        remove_btn = widgets.Button(
            description="Remove", button_style="danger", layout=widgets.Layout(width="100px")
        )

        row = {
            "kind": kind,
            "a": opt_a,
            "b": opt_b,
            "c": opt_c,
            "include_sweep": include_sweep,
            "legend_table": legend_table,
            "fit_enabled": fit_enabled,
            "fit_model": fit_model,
            "fit_mode": fit_mode,
            "fit_xmin": fit_xmin,
            "fit_xmax": fit_xmax,
            "fit_curve_dropdown": fit_curve_dropdown,
            "fit_curve_min": fit_curve_min,
            "fit_curve_max": fit_curve_max,
            "fit_curve_set": fit_curve_set,
            "fit_curve_ranges_html": fit_curve_ranges_html,
            "fit_curve_ranges": {},
            "remove": remove_btn,
        }

        def _render_fit_curve_ranges():
            ranges = row["fit_curve_ranges"]
            if not ranges:
                fit_curve_ranges_html.value = "<span style='color:#667085;font-size:12px;'>No per-curve fit ranges set.</span>"
                return
            lines = [
                "<div style='font-size:12px;color:#334155;'><b>Per-curve fit ranges:</b></div>"
            ]
            for key in sorted(ranges.keys()):
                cfg = ranges[key]
                xmin_text = "-" if cfg.get("fit_min") is None else str(cfg.get("fit_min"))
                xmax_text = "-" if cfg.get("fit_max") is None else str(cfg.get("fit_max"))
                lines.append(
                    f"<div style='font-size:12px;color:#334155;'>{html.escape(str(key))}: xmin={xmin_text}, xmax={xmax_text}</div>"
                )
            fit_curve_ranges_html.value = "".join(lines)

        def _parse_curve_bound(text):
            s = str(text).strip()
            if not s:
                return None
            try:
                return float(s)
            except Exception:
                return None

        def _set_curve_range(_btn):
            curve_key = fit_curve_dropdown.value
            if not curve_key or curve_key == "__all__":
                return
            vmin = _parse_curve_bound(fit_curve_min.value)
            vmax = _parse_curve_bound(fit_curve_max.value)
            if vmin is None and vmax is None:
                if curve_key in row["fit_curve_ranges"]:
                    del row["fit_curve_ranges"][curve_key]
            else:
                row["fit_curve_ranges"][curve_key] = {"fit_min": vmin, "fit_max": vmax}
            _render_fit_curve_ranges()

        fit_curve_set.on_click(_set_curve_range)
        _render_fit_curve_ranges()

        def refresh_options(*_args):
            if kind.value in ["PL (only)", "PL + PL (sweep ~1 sun)"]:
                include_sweep.layout.display = "none"
                fit_enabled.description = "Peak fit"
                fit_enabled.layout.display = "flex"
                fit_model.layout.display = "flex"
                fit_mode.layout.display = "flex"
                fit_xmin.layout.display = "none"
                fit_xmax.layout.display = "none"
                fit_curve_dropdown.layout.display = "flex"
                fit_curve_min.layout.display = "flex"
                fit_curve_max.layout.display = "flex"
                fit_curve_set.layout.display = "flex"
                fit_curve_ranges_html.layout.display = "flex"
                opt_a.description = "Color by"
                opt_b.description = "Source"
                opt_c.description = "-"
                opt_a.options = [
                    ("Sample", "sample_id"),
                    ("Condition", "condition"),
                    ("Batch", "batch"),
                    ("Spot size", "laser_spot_size"),
                ]
                opt_a.value = "sample_id"
                opt_b.options = [
                    ("Auto", "auto"),
                    ("Flux density", "luminescence_flux_density"),
                    ("Raw counts", "raw_spectrum_counts"),
                ]
                opt_c.options = [("-", "-")]
                opt_c.value = "-"
            elif kind.value == "Sweep":
                include_sweep.layout.display = "none"
                fit_enabled.description = "Peak fit"
                fit_enabled.layout.display = "flex"
                fit_model.layout.display = "flex"
                fit_mode.layout.display = "flex"
                fit_xmin.layout.display = "none"
                fit_xmax.layout.display = "none"
                fit_curve_dropdown.layout.display = "flex"
                fit_curve_min.layout.display = "flex"
                fit_curve_max.layout.display = "flex"
                fit_curve_set.layout.display = "flex"
                fit_curve_ranges_html.layout.display = "flex"
                opt_a.description = "Mode"
                opt_b.description = "Color by"
                opt_c.description = "Source"
                opt_a.options = [
                    ("Combined", "combined"),
                    ("Separate substrates", "separate_substrates"),
                ]
                opt_a.value = "combined"
                opt_b.options = [
                    ("Sample", "sample_id"),
                    ("Condition", "condition"),
                    ("Batch", "batch"),
                    ("Spot size", "laser_spot_size"),
                ]
                opt_b.value = "condition"
                opt_c.options = [("Flux density", "luminescence_flux_density")]
                opt_c.value = "luminescence_flux_density"
            elif kind.value in [
                "LuQY vs Laser Intensity",
                "QFLS vs Laser Intensity",
                "PLQY + QFLS vs Laser Intensity",
            ]:
                include_sweep.layout.display = "none"
                fit_enabled.description = "Linear fit"
                fit_enabled.layout.display = "flex"
                fit_model.layout.display = "none"
                fit_mode.layout.display = "none"
                fit_xmin.layout.display = "flex"
                fit_xmax.layout.display = "flex"
                fit_curve_dropdown.layout.display = "none"
                fit_curve_min.layout.display = "none"
                fit_curve_max.layout.display = "none"
                fit_curve_set.layout.display = "none"
                fit_curve_ranges_html.layout.display = "none"
                opt_a.description = "Mode"
                opt_b.description = "Color by"
                opt_c.description = "X scale"
                opt_a.options = [("Combined (all files)", "combined"), ("Per sample", "per_sample")]
                opt_a.value = "combined"
                opt_b.options = [
                    ("Sample", "sample_id"),
                    ("Condition", "condition"),
                    ("Batch", "batch"),
                    ("Measurement type", "measurement_type"),
                ]
                opt_b.value = "sample_id"
                opt_c.options = [("Linear", "linear"), ("Log", "log")]
                opt_c.value = "linear"
                if kind.value == "LuQY vs Laser Intensity":
                    fit_enabled.value = False
                    fit_enabled.disabled = True
                else:
                    fit_enabled.disabled = False

        kind.observe(refresh_options, names="value")

        def remove_row(_btn):
            self.plot_rows = [r for r in self.plot_rows if r is not row]
            self._render_plot_rows()

        remove_btn.on_click(remove_row)

        self.plot_rows.append(row)
        refresh_options()
        self._render_plot_rows()

    def _clear_plot_rows(self, _):
        self.plot_rows = []
        self._render_plot_rows()

    def _load_preset(self, _):
        """Load selected preset"""
        selected_preset = self.preset_dropdown.value
        self.plot_rows = []

        if selected_preset in self.plot_presets:
            for plot_type, option_a, option_b in self.plot_presets[selected_preset]:
                self._add_plot_row(None)
                # Set the values for the new row
                if self.plot_rows:
                    row = self.plot_rows[-1]
                    row["kind"].value = plot_type
                    if option_a and any(val == option_a for _, val in row["a"].options):
                        row["a"].value = option_a
                    if option_b and any(val == option_b for _, val in row["b"].options):
                        row["b"].value = option_b
        else:
            self._add_plot_row(None)

        self._render_plot_rows()

    def _render_plot_rows(self):
        widget_rows = []
        for row in self.plot_rows:
            top_row = widgets.HBox(
                [
                    row["kind"],
                    row["a"],
                    row["b"],
                    row["c"],
                    row["remove"],
                ]
            )
            bottom_row = widgets.HBox(
                [
                    row["include_sweep"],
                    row["legend_table"],
                    row["fit_enabled"],
                    row["fit_model"],
                    row["fit_mode"],
                    row["fit_xmin"],
                    row["fit_xmax"],
                ]
            )
            per_curve_row = widgets.HBox(
                [
                    row["fit_curve_dropdown"],
                    row["fit_curve_min"],
                    row["fit_curve_max"],
                    row["fit_curve_set"],
                ]
            )
            widget_rows.append(
                widgets.VBox(
                    [
                        top_row,
                        bottom_row,
                        per_curve_row,
                        row["fit_curve_ranges_html"],
                    ],
                    layout=widgets.Layout(
                        border="1px solid #d0d5dd",
                        padding="10px",
                        margin="8px 0",
                        border_radius="6px",
                        background_color="#fcfcfd",
                    ),
                )
            )
        self.plot_rows_container.children = tuple(widget_rows)

    def update_filter_options(self, options):
        self._suspend_auto_apply = True
        self.filter_options = options
        self._filter_rows = options.get("filter_rows", [])

        for row in self.selection_rows:
            sample_values = self.filter_options.get("samples", [])
            sample_options = self._with_all_option(sample_values)
            current_sample = row["sample"].value
            row["sample"].options = sample_options
            row["sample"].value = (
                current_sample if any(v == current_sample for _, v in sample_options) else "__all__"
            )
            self._update_row_options(row, source="sample")

        if not self.selection_rows:
            self._add_selection_row(None)

        self._update_trace_order_widget(options.get("samples", []))
        max_required_colors = int(options.get("max_required_colors", 8) or 8)
        self.color_selector.set_num_colors(max_required_colors)

        curve_options = self._fit_curve_options()
        for row in self.plot_rows:
            current_curve = row["fit_curve_dropdown"].value
            row["fit_curve_dropdown"].options = curve_options
            row["fit_curve_dropdown"].value = (
                current_curve if any(v == current_curve for _, v in curve_options) else "__all__"
            )

        for row in self.plot_rows:
            try:
                row["kind"].value = row["kind"].value
            except Exception:
                pass
        self._suspend_auto_apply = False

    def get_filter_config(self):
        row_filters = []
        for row in self.selection_rows:
            row_filters.append(
                {
                    "sample": row["sample"].value,
                    "measurement_type": row["type"].value,
                    "laser_spot_size": row["spot"].value,
                    "cycle": row["cycle"].value,
                }
            )

        return {
            "row_filters": row_filters,
        }

    def get_plot_specs(self):
        def _parse_optional_float(value):
            text = str(value).strip() if value is not None else ""
            if not text:
                return None
            try:
                return float(text)
            except Exception:
                return None

        specs = []
        trace_order = []
        try:
            parsed = json.loads(self.trace_order_state.value or "[]")
            if isinstance(parsed, list):
                trace_order = [str(v) for v in parsed]
        except Exception:
            trace_order = []

        for row in self.plot_rows:
            plot_type_value = row["kind"].value
            include_sweep_pl = plot_type_value == "PL + PL (sweep ~1 sun)"

            normalized_plot_type = plot_type_value
            if plot_type_value in ["PL (only)", "PL + PL (sweep ~1 sun)"]:
                normalized_plot_type = "PL"

            specs.append(
                {
                    "plot_type": normalized_plot_type,
                    "option_a": row["a"].value,
                    "option_b": row["b"].value,
                    "option_c": row["c"].value,
                    "include_sweep_pl": include_sweep_pl,
                    "plot_type_ui": plot_type_value,
                    "legend_table_below": bool(row["legend_table"].value),
                    "fit_enabled": bool(row["fit_enabled"].value)
                    and (plot_type_value != "LuQY vs Laser Intensity"),
                    "fit_model": row["fit_model"].value,
                    "fit_mode": row["fit_mode"].value,
                    "fit_min": _parse_optional_float(row["fit_xmin"].value),
                    "fit_max": _parse_optional_float(row["fit_xmax"].value),
                    "fit_curve_ranges": row.get("fit_curve_ranges", {}),
                    "color_scheme": self.color_selector.selected_scheme,
                    "color_sampling": "sequential",
                    "color_count": int(self.color_selector.num_colors),
                    "trace_order": trace_order,
                }
            )
        return specs

    def _fit_curve_options(self):
        option_rows = self.filter_options.get("fit_curve_options", []) or []
        options = [("All curves", "__all__")]
        for item in option_rows:
            label = str(item.get("label", "")).strip()
            value = str(item.get("value", "")).strip()
            if label and value:
                options.append((label, value))
        return options


class ColorSchemeSelector:
    """Color scheme selector with preview"""

    def __init__(self):
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
            "Set2": px.colors.qualitative.Set2,
            "Default (old)": [
                "rgba(93, 164, 214, 0.7)",
                "rgba(255, 144, 14, 0.7)",
                "rgba(44, 160, 101, 0.7)",
                "rgba(255, 65, 54, 0.7)",
                "rgba(207, 114, 255, 0.7)",
                "rgba(127, 96, 0, 0.7)",
                "rgba(255, 140, 184, 0.7)",
                "rgba(79, 90, 117, 0.7)",
            ],
        }

        self.selected_scheme = "Viridis"
        self.num_colors = 8
        self._create_widgets()

    def _create_widgets(self):
        """Create color scheme selector widgets"""
        self.color_dropdown = widgets.Dropdown(
            options=list(self.color_schemes.keys()),
            value=self.selected_scheme,
            description="Color Scheme:",
            style={"description_width": "initial"},
            layout=widgets.Layout(width="420px"),
        )

        self.color_dropdown.observe(self._on_color_change, names="value")

        self.widget = widgets.VBox(
            [
                self.color_dropdown,
            ],
            layout=widgets.Layout(width="100%"),
        )

    def _on_color_change(self, change):
        self.selected_scheme = change["new"]
        self._update_preview()

    def _on_num_colors_change(self, change):
        """Compatibility no-op: color count control removed from UI."""
        self.num_colors = (
            change.get("new", self.num_colors) if isinstance(change, dict) else self.num_colors
        )

    def _interpolate_color(self, hex_color1, hex_color2, factor):
        """Interpolate between two colors"""

        def hex_to_rgb(color):
            if isinstance(color, str):
                if color.startswith("rgba"):
                    import re

                    match = re.match(
                        r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", color
                    )
                    if match:
                        r, g, b, a = match.groups()
                        return (int(r) / 255.0, int(g) / 255.0, int(b) / 255.0)

                color = color.lstrip("#")
                if len(color) >= 6:
                    return tuple(int(color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))

            return (0.5, 0.5, 0.5)

        def rgb_to_hex(r, g, b):
            return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))

        rgb1 = hex_to_rgb(hex_color1)
        rgb2 = hex_to_rgb(hex_color2)

        r = rgb1[0] + (rgb2[0] - rgb1[0]) * factor
        g = rgb1[1] + (rgb2[1] - rgb1[1]) * factor
        b = rgb1[2] + (rgb2[2] - rgb1[2]) * factor

        return rgb_to_hex(r, g, b)

    def _ensure_hex_format(self, color):
        """Convert color to hex format"""
        if isinstance(color, str):
            if color.startswith("#"):
                return color

            if color.startswith("rgba"):
                import re

                match = re.match(
                    r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", color
                )
                if match:
                    r, g, b, a = match.groups()
                    return "#{:02x}{:02x}{:02x}".format(int(r), int(g), int(b))

        return "#808080"

    def _generate_continuous_colors(self, num_colors):
        """Generate smooth color gradient from continuous palette"""
        base_palette = self.color_schemes[self.selected_scheme]

        if num_colors <= len(base_palette):
            step = (len(base_palette) - 1) / (num_colors - 1) if num_colors > 1 else 0
            selected_colors = [base_palette[int(i * step)] for i in range(num_colors)]
            return [self._ensure_hex_format(color) for color in selected_colors]
        else:
            colors = []

            for i in range(num_colors):
                position = i / (num_colors - 1) if num_colors > 1 else 0
                palette_index = position * (len(base_palette) - 1)
                lower_index = int(palette_index)
                upper_index = min(lower_index + 1, len(base_palette) - 1)
                factor = palette_index - lower_index

                color1 = base_palette[lower_index]
                color2 = base_palette[upper_index]

                if factor == 0 or lower_index == upper_index:
                    interpolated = self._ensure_hex_format(color1)
                else:
                    interpolated = self._interpolate_color(color1, color2, factor)

                colors.append(interpolated)

            return colors

    def get_colors(self, num_colors=None, sampling="sequential"):
        """Get colors from selected scheme"""
        if num_colors is None:
            num_colors = self.num_colors

        colors = self.color_schemes[self.selected_scheme]

        if sampling == "even" and len(colors) > num_colors:
            if num_colors == 1:
                return [colors[len(colors) // 2]]

            indices = []
            for i in range(num_colors):
                index = int(round(i * (len(colors) - 1) / (num_colors - 1)))
                indices.append(index)

            return [colors[i] for i in indices]
        else:
            return self._generate_continuous_colors(num_colors)

    def set_num_colors(self, num_colors):
        """Set the number of colors to generate"""
        num_colors = max(2, min(120, num_colors))
        self.num_colors = num_colors

    def get_widget(self):
        """Get the color scheme selector widget"""
        return self.widget
