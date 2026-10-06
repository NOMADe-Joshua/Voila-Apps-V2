"""
Resizable Plot Utility for EQE Analysis Application
Adds resizable containers to Plotly figures in Jupyter notebooks / Voila.
Ported from JV-Analysis resizable_plot_utility.py.
"""

import json
import uuid

import ipywidgets as widgets
import plotly.graph_objects as go
import plotly.utils
from IPython.display import HTML, clear_output, display


class ResizablePlotWidget:
    """Creates resizable Plotly plots for Jupyter notebooks / Voila."""

    def __init__(
        self, fig, title="Plot", initial_width=800, initial_height=600, subtitle=None, filename=None
    ):
        self.fig = fig
        self.title = title
        self.subtitle = subtitle
        self.initial_width = initial_width
        self.initial_height = initial_height
        self.plot_id = f"plot_{uuid.uuid4().hex[:8]}"
        if filename:
            base = filename
            for ext in [".html", ".svg", ".png", ".pdf"]:
                if base.lower().endswith(ext):
                    base = base[: -len(ext)]
                    break
            self.filename_base = base
        else:
            safe = str(title).replace(" ", "_").replace("/", "_").replace("\\", "_")
            safe = "".join(c for c in safe if c.isalnum() or c in "_-")
            self.filename_base = safe[:60] if safe else "eqe_plot"

    def display(self):
        """Display the resizable plot."""
        self.fig.update_layout(
            autosize=True,
            margin=dict(l=80, r=50, t=80, b=80, autoexpand=False),
            xaxis=dict(
                autorange=False if self.fig.layout.xaxis.range else True,
                constrain="domain",
                automargin=False,
            ),
            yaxis=dict(automargin=False),
        )

        fig_json = json.dumps(self.fig, cls=plotly.utils.PlotlyJSONEncoder)

        title_html = f'<h3 style="margin: 20px 0 5px 0; color: #2c3e50;">{self.title}</h3>'
        if self.subtitle:
            title_html += (
                f'<p style="margin: 0 0 10px 0; color: #666; font-size: 12px;">{self.subtitle}</p>'
            )

        resizable_html = f'''
        <script>
        (function() {{
            if (typeof window.Plotly !== 'undefined') return;
            if (document.getElementById('eqe-plotly-cdn')) return;
            var script = document.createElement('script');
            script.id = 'eqe-plotly-cdn';
            script.src = 'https://cdn.plot.ly/plotly-2.35.2.min.js';
            document.head.appendChild(script);
        }})();
        </script>

        <div style="margin: 20px 0;">
            {title_html}
            <p style="color: #666; font-size: 12px; margin: 5px 0;">
                💡 Drag the bottom-right corner to resize |
                🖱️ <strong>Drag the legend</strong> to reposition it
            </p>

            <div id="container-{self.plot_id}" style="
                width: {self.initial_width}px;
                height: {self.initial_height}px;
                border: 2px solid #ddd;
                border-radius: 8px;
                resize: both;
                overflow: hidden;
                min-width: 400px;
                min-height: 300px;
                max-width: 1400px;
                max-height: 1000px;
                background-color: white;
                position: relative;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            ">
                <div id="{self.plot_id}" style="
                    width: 100% !important;
                    height: 100% !important;
                    position: absolute !important;
                    top: 0; left: 0; right: 0; bottom: 0;
                "></div>
                <div style="
                    position: absolute; bottom: 2px; right: 2px;
                    width: 16px; height: 16px;
                    background: linear-gradient(-45deg, transparent 30%, #999 30%, #999 40%, transparent 40%, transparent 60%, #999 60%, #999 70%, transparent 70%);
                    pointer-events: none; z-index: 1000;
                "></div>
            </div>
        </div>

        <style>
        #container-{self.plot_id}:hover {{ border-color: #007bff; }}
        #container-{self.plot_id} .plotly {{ width: 100% !important; height: 100% !important; }}
        #container-{self.plot_id} .main-svg {{ position: absolute !important; top: 0 !important; left: 0 !important; }}
        </style>

        <script>
        (function() {{
            const figureData = {fig_json};
            let originalXRange = null;
            if (figureData.layout && figureData.layout.xaxis && figureData.layout.xaxis.range) {{
                originalXRange = [...figureData.layout.xaxis.range];
            }}

            function triggerBlobDownload(blob, filename) {{
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = filename;
                document.body.appendChild(a); a.click();
                document.body.removeChild(a);
                setTimeout(() => URL.revokeObjectURL(url), 1000);
            }}

            function getTimestamp() {{
                const n = new Date();
                const p = x => String(x).padStart(2, '0');
                return `${{n.getFullYear()}}${{p(n.getMonth()+1)}}${{p(n.getDate())}}_${{p(n.getHours())}}-${{p(n.getMinutes())}}-${{p(n.getSeconds())}}_`;
            }}

            function downloadViaPlotly(gd, format, filename, scale) {{
                const w = gd.clientWidth || 1200, h = gd.clientHeight || 800;
                return Plotly.toImage(gd, {{ format, width: w, height: h, scale: scale || 1 }}).then(dataUri => {{
                    if (format === 'svg') {{
                        const prefix = 'data:image/svg+xml;base64,';
                        const plain = 'data:image/svg+xml,';
                        let svgText = dataUri.startsWith(prefix)
                            ? atob(dataUri.slice(prefix.length))
                            : decodeURIComponent(dataUri.slice(plain.length));
                        triggerBlobDownload(new Blob([svgText], {{ type: 'image/svg+xml;charset=utf-8' }}), filename);
                    }} else {{
                        const b64 = dataUri.slice('data:image/png;base64,'.length);
                        const raw = atob(b64);
                        const buf = new Uint8Array(raw.length);
                        for (let i = 0; i < raw.length; i++) buf[i] = raw.charCodeAt(i);
                        triggerBlobDownload(new Blob([buf], {{ type: 'image/png' }}), filename);
                    }}
                }});
            }}

            function initPlot() {{
                const plotDiv = document.getElementById('{self.plot_id}');
                const container = document.getElementById('container-{self.plot_id}');
                if (!plotDiv || !container) {{ setTimeout(initPlot, 100); return; }}

                const config = {{
                    responsive: true,
                    displayModeBar: true,
                    displaylogo: false,
                    modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d', 'toImage'],
                    autosizable: false,
                    edits: {{ legendPosition: true }},
                    modeBarButtonsToAdd: [
                        {{
                            name: 'Download SVG',
                            icon: Plotly.Icons.camera,
                            click: gd => downloadViaPlotly(gd, 'svg', getTimestamp() + '{self.filename_base}.svg').catch(console.error)
                        }},
                        {{
                            name: 'Download PNG (~600dpi)',
                            icon: Plotly.Icons.camera,
                            click: gd => downloadViaPlotly(gd, 'png', getTimestamp() + '{self.filename_base}_600dpi.png', 6).catch(console.error)
                        }}
                    ]
                }};

                if (figureData.layout) {{
                    figureData.layout.autosize = true;
                    figureData.layout.margin = figureData.layout.margin || {{}};
                    figureData.layout.margin.autoexpand = false;
                    if (figureData.layout.xaxis) figureData.layout.xaxis.automargin = false;
                    if (figureData.layout.yaxis) figureData.layout.yaxis.automargin = false;
                    const rect = container.getBoundingClientRect();
                    figureData.layout.width = rect.width;
                    figureData.layout.height = rect.height;
                }}

                Plotly.newPlot(plotDiv, figureData.data, figureData.layout, config).then(() => {{
                    plotDiv.on('plotly_relayout', eventData => {{
                        if (eventData['xaxis.autorange'] === true && originalXRange) {{
                            Plotly.relayout(plotDiv, {{
                                'xaxis.range': originalXRange,
                                'xaxis.autorange': false,
                                'xaxis.automargin': false
                            }});
                        }}
                    }});

                    if (window.ResizeObserver) {{
                        let t;
                        new ResizeObserver(() => {{
                            clearTimeout(t);
                            t = setTimeout(() => {{
                                if (!container.isConnected || !plotDiv.isConnected) return;
                                const r = container.getBoundingClientRect();
                                if (!isFinite(r.width) || r.width <= 0) return;
                                const upd = {{ width: r.width, height: r.height, 'margin.autoexpand': false }};
                                if (originalXRange) {{
                                    upd['xaxis.range'] = originalXRange;
                                    upd['xaxis.autorange'] = false;
                                    upd['xaxis.automargin'] = false;
                                }}
                                if (typeof Plotly !== 'undefined' && plotDiv.data) Plotly.relayout(plotDiv, upd);
                            }}, 100);
                        }}).observe(container);
                    }}
                }}).catch(console.error);
            }}

            if (typeof Plotly !== 'undefined') {{
                initPlot();
            }} else {{
                let n = 0;
                const iv = setInterval(() => {{
                    if (typeof Plotly !== 'undefined' || n++ > 50) {{
                        clearInterval(iv);
                        if (typeof Plotly !== 'undefined') initPlot();
                    }}
                }}, 100);
            }}
        }})();
        </script>
        '''
        display(HTML(resizable_html))


def create_resizable_plot(fig, title="Plot", width=800, height=600, subtitle=None, filename=None):
    return ResizablePlotWidget(fig, title, width, height, subtitle, filename)


def display_resizable_plot(fig, title="Plot", width=800, height=600, subtitle=None, filename=None):
    create_resizable_plot(fig, title, width, height, subtitle, filename).display()


class ResizablePlotManager:
    """Display multiple Plotly figures as resizable widgets."""

    @staticmethod
    def display_plots_resizable(figs, names, titles=None, subtitles=None, container_widget=None):
        if container_widget:
            with container_widget:
                ResizablePlotManager._display_plots_internal(figs, names, titles, subtitles)
        else:
            ResizablePlotManager._display_plots_internal(figs, names, titles, subtitles)

    @staticmethod
    def _display_plots_internal(figs, names, titles=None, subtitles=None):
        clear_output(wait=True)
        print(f"✅ {len(figs)} plot(s) created — drag the bottom-right corner to resize")
        for i, (fig, name) in enumerate(zip(figs, names)):
            display_title = titles[i] if titles and i < len(titles) else name
            subtitle = subtitles[i] if subtitles and i < len(subtitles) else None
            width, height = 900, 600
            display_resizable_plot(fig, display_title, width, height, subtitle, filename=name)
