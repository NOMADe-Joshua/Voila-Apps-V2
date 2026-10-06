"""
Resizable Plot Utility for AbsPL Analysis Application.

This is a self-contained local copy so AbsPL can render plots independently
from the JV application and its folder layout.
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
            self.filename_base = safe[:60] if safe else "abspl_plot"

    def display(self):
        """Display the resizable plot with an external title block."""
        self.fig.update_layout(
            autosize=True,
            margin=dict(l=80, r=50, t=80, b=120, autoexpand=True),
            xaxis=dict(
                autorange=False if self.fig.layout.xaxis.range else True,
                constrain="domain",
                automargin=True,
            ),
            yaxis=dict(automargin=True),
            legend=dict(),
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
            if (document.getElementById('abspl-plotly-cdn')) return;
            var script = document.createElement('script');
            script.id = 'abspl-plotly-cdn';
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
                min-height: 380px;
                max-width: 1400px;
                max-height: 1000px;
                background-color: white;
                position: relative;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                transition: border-color 0.2s;
            ">
                <div id="{self.plot_id}" style="
                    width: 100% !important;
                    height: 100% !important;
                    position: absolute !important;
                    top: 0 !important;
                    left: 0 !important;
                    right: 0 !important;
                    bottom: 0 !important;
                "></div>

                <div style="
                    position: absolute;
                    bottom: 2px;
                    right: 2px;
                    width: 16px;
                    height: 16px;
                    background: linear-gradient(-45deg, transparent 30%, #999 30%, #999 40%, transparent 40%, transparent 60%, #999 60%, #999 70%, transparent 70%);
                    cursor: se-resize;
                    z-index: 1000;
                    pointer-events: none;
                "></div>
            </div>
        </div>

        <style>
        #container-{self.plot_id}:hover {{
            border-color: #007bff;
        }}
        #container-{self.plot_id} .plotly {{
            width: 100% !important;
            height: 100% !important;
        }}
        #container-{self.plot_id} .main-svg {{
            position: absolute !important;
            top: 0 !important;
            left: 0 !important;
        }}
        </style>

        <script>
        (function() {{
            const figureData = {fig_json};

            const config = {{
                responsive: true,
                displayModeBar: true,
                displaylogo: false,
                modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d', 'toImage'],
                autosizable: false,
                edits: {{
                    legendPosition: true
                }}
            }};

            if (figureData.layout) {{
                figureData.layout.autosize = true;
                if (!figureData.layout.margin) {{
                    figureData.layout.margin = {{}};
                }}
                figureData.layout.margin.autoexpand = true;

                Object.keys(figureData.layout).forEach(function(key) {{
                    if (key.startsWith('xaxis') || key.startsWith('yaxis')) {{
                        if (!figureData.layout[key]) {{
                            figureData.layout[key] = {{}};
                        }}
                        figureData.layout[key].automargin = true;
                    }}
                }});
            }}

            let originalXRange = null;
            if (figureData.layout && figureData.layout.xaxis && figureData.layout.xaxis.range) {{
                originalXRange = [...figureData.layout.xaxis.range];
            }}

            function initPlot() {{
                const plotDiv = document.getElementById('{self.plot_id}');
                const container = document.getElementById('container-{self.plot_id}');

                function getDynamicBottomMargin(gd) {{
                    try {{
                        const tickNodes = gd.querySelectorAll('.xtick text');
                        if (!tickNodes || tickNodes.length === 0) {{
                            return 120;
                        }}

                        let maxProjectedHeight = 0;
                        const angleRad = Math.PI / 4;

                        tickNodes.forEach(function(node) {{
                            if (!node.textContent || !node.textContent.trim()) return;
                            const bb = node.getBBox();
                            const projected = Math.abs(Math.sin(angleRad) * bb.width) + Math.abs(Math.cos(angleRad) * bb.height);
                            if (projected > maxProjectedHeight) maxProjectedHeight = projected;
                        }});

                        return Math.max(120, Math.ceil(maxProjectedHeight + 40));
                    }} catch (e) {{
                        return 120;
                    }}
                }}

                function triggerBlobDownload(blob, filename) {{
                    const objectUrl = URL.createObjectURL(blob);
                    const link = document.createElement('a');
                    link.href = objectUrl;
                    link.download = filename;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    setTimeout(function() {{
                        URL.revokeObjectURL(objectUrl);
                    }}, 1000);
                }}

                function downloadSvgViaPlotly(gd, filename) {{
                    const width = gd.clientWidth || gd.offsetWidth || 1200;
                    const height = gd.clientHeight || gd.offsetHeight || 800;

                    return Plotly.toImage(gd, {{
                        format: 'svg',
                        width: width,
                        height: height
                    }}).then(function(dataUri) {{
                        let svgText;

                        const base64Prefix = 'data:image/svg+xml;base64,';
                        const plainPrefix = 'data:image/svg+xml,';

                        if (dataUri.startsWith(base64Prefix)) {{
                            svgText = atob(dataUri.slice(base64Prefix.length));
                        }} else if (dataUri.startsWith(plainPrefix)) {{
                            svgText = decodeURIComponent(dataUri.slice(plainPrefix.length));
                        }} else {{
                            throw new Error('Unexpected data URI format: ' + dataUri.slice(0, 40));
                        }}

                        const blob = new Blob([svgText], {{ type: 'image/svg+xml;charset=utf-8' }});
                        triggerBlobDownload(blob, filename);
                    }});
                }}

                function downloadPngViaPlotly(gd, filename, scale) {{
                    const width = gd.clientWidth || gd.offsetWidth || 1200;
                    const height = gd.clientHeight || gd.offsetHeight || 800;

                    return Plotly.toImage(gd, {{
                        format: 'png',
                        width: width,
                        height: height,
                        scale: scale || 6
                    }}).then(function(dataUri) {{
                        const base64Prefix = 'data:image/png;base64,';
                        if (!dataUri.startsWith(base64Prefix)) {{
                            throw new Error('Unexpected PNG data URI format');
                        }}
                        const byteString = atob(dataUri.slice(base64Prefix.length));
                        const buf = new Uint8Array(byteString.length);
                        for (let i = 0; i < byteString.length; i++) {{
                            buf[i] = byteString.charCodeAt(i);
                        }}
                        const blob = new Blob([buf], {{ type: 'image/png' }});
                        triggerBlobDownload(blob, filename);
                    }});
                }}

                function getTimestamp() {{
                    const now = new Date();
                    const pad = n => String(n).padStart(2, '0');
                    return `${{now.getFullYear()}}${{pad(now.getMonth()+1)}}${{pad(now.getDate())}}_${{pad(now.getHours())}}-${{pad(now.getMinutes())}}-${{pad(now.getSeconds())}}_`;
                }}

                const svgDownloadButton = {{
                    name: 'Download SVG',
                    icon: Plotly.Icons.camera,
                    click: function(gd) {{
                        downloadSvgViaPlotly(gd, getTimestamp() + '{self.filename_base}.svg').catch(function(err) {{
                            console.error('SVG download failed:', err);
                        }});
                    }}
                }};

                const pngDownloadButton = {{
                    name: 'Download PNG (~600dpi)',
                    icon: Plotly.Icons.camera,
                    click: function(gd) {{
                        downloadPngViaPlotly(gd, getTimestamp() + '{self.filename_base}_600dpi.png', 6).catch(function(err) {{
                            console.error('PNG download failed:', err);
                        }});
                    }}
                }};

                config.modeBarButtonsToAdd = [svgDownloadButton, pngDownloadButton];

                if (!plotDiv || !container) {{
                    setTimeout(initPlot, 100);
                    return;
                }}

                const containerRect = container.getBoundingClientRect();
                figureData.layout.width = containerRect.width;
                figureData.layout.height = containerRect.height;

                Plotly.newPlot(plotDiv, figureData.data, figureData.layout, config).then(function() {{
                    plotDiv.on('plotly_relayout', function(eventData) {{
                        if (eventData['xaxis.autorange'] === true && originalXRange) {{
                            Plotly.relayout(plotDiv, {{
                                'xaxis.range': originalXRange,
                                'xaxis.autorange': false,
                                'xaxis.automargin': true
                            }});
                        }}
                    }});

                    if (window.ResizeObserver) {{
                        let resizeTimeout;
                        const observer = new ResizeObserver(function() {{
                            clearTimeout(resizeTimeout);
                            resizeTimeout = setTimeout(function() {{
                                if (!container || !plotDiv || !container.isConnected || !plotDiv.isConnected) {{
                                    return;
                                }}

                                const rect = container.getBoundingClientRect();
                                if (!rect || !isFinite(rect.width) || !isFinite(rect.height) || rect.width <= 0 || rect.height <= 0) {{
                                    return;
                                }}

                                const dynamicBottom = getDynamicBottomMargin(plotDiv);
                                const updateLayout = {{
                                    width: rect.width,
                                    height: rect.height,
                                    'margin.autoexpand': true,
                                    'margin.b': dynamicBottom
                                }};

                                if (originalXRange) {{
                                    updateLayout['xaxis.range'] = originalXRange;
                                    updateLayout['xaxis.autorange'] = false;
                                    updateLayout['xaxis.automargin'] = true;
                                }}

                                if (typeof Plotly !== 'undefined' && plotDiv && plotDiv.data) {{
                                    Plotly.relayout(plotDiv, updateLayout);
                                }}
                            }}, 100);
                        }});
                        observer.observe(container);
                    }}
                }}).catch(function(err) {{
                    console.error('Plot creation failed:', err);
                }});
            }}

            if (typeof Plotly !== 'undefined') {{
                initPlot();
            }} else {{
                let checkCount = 0;
                const checkPlotly = setInterval(function() {{
                    if (typeof Plotly !== 'undefined' || checkCount > 50) {{
                        clearInterval(checkPlotly);
                        if (typeof Plotly !== 'undefined') {{
                            initPlot();
                        }} else {{
                            console.error('Plotly failed to load');
                        }}
                    }}
                    checkCount++;
                }}, 100);
            }}
        }})();
        </script>
        '''

        display(HTML(resizable_html))


def create_resizable_plot(fig, title="Plot", width=800, height=600, subtitle=None, filename=None):
    """Create a resizable plot from a Plotly figure."""
    return ResizablePlotWidget(fig, title, width, height, subtitle, filename)


def display_resizable_plot(fig, title="Plot", width=800, height=600, subtitle=None, filename=None):
    """Create and immediately display a resizable plot."""
    create_resizable_plot(fig, title, width, height, subtitle, filename).display()


class ResizablePlotManager:
    """Display multiple Plotly figures as resizable widgets."""

    @staticmethod
    def display_plots_resizable(
        figs,
        filenames,
        titles=None,
        subtitles=None,
        container_widget=None,
        jv_legend_table=False,
        legend_table_flags=None,
    ):
        if container_widget:
            with container_widget:
                ResizablePlotManager._display_plots_internal(
                    figs, filenames, titles, subtitles, jv_legend_table, legend_table_flags
                )
        else:
            ResizablePlotManager._display_plots_internal(
                figs, filenames, titles, subtitles, jv_legend_table, legend_table_flags
            )

    @staticmethod
    def _build_legend_table(fig):
        entries = []
        seen = set()
        for trace in fig.data:
            name = getattr(trace, "name", None) or ""
            if not name or name in seen:
                continue
            showlegend = getattr(trace, "showlegend", None)
            if showlegend is False:
                continue
            seen.add(name)
            color = "#888"
            line = getattr(trace, "line", None)
            if line and getattr(line, "color", None):
                color = line.color
            elif hasattr(trace, "marker") and getattr(trace.marker, "color", None):
                color = trace.marker.color
            entries.append((name, color))

        if not entries:
            return ""

        rows_html = ""
        for entry_name, entry_color in entries:
            swatch = (
                f'<span style="display:inline-block;width:24px;height:3px;'
                f"background:{entry_color};vertical-align:middle;"
                f'border-radius:2px;margin-right:6px;"></span>'
            )
            rows_html += (
                f'<tr><td style="padding:3px 0;white-space:nowrap;font-size:12px;">'
                f"{swatch}{entry_name}</td></tr>"
            )

        return (
            f'<div style="margin:4px 0 24px 0;padding:8px 14px;'
            f"background:#fafafa;border:1px solid #ddd;border-radius:6px;"
            f'display:inline-block;font-family:sans-serif;">'
            f'<div style="font-weight:bold;font-size:12px;color:#666;margin-bottom:6px;">Legend</div>'
            f'<table style="border-collapse:collapse;">{rows_html}</table>'
            f"</div>"
        )

    @staticmethod
    def _display_plots_internal(
        figs, names, titles=None, subtitles=None, jv_legend_table=False, legend_table_flags=None
    ):
        clear_output(wait=True)

        print(f"✅ Successfully created {len(figs)} resizable plots")
        print("💡 Drag the bottom-right corner of each plot to resize")
        print()

        for i, (fig, name) in enumerate(zip(figs, names)):
            try:
                display_title = titles[i] if titles and i < len(titles) else name
                subtitle = subtitles[i] if subtitles and i < len(subtitles) else None

                is_jv_curve = name.lower().startswith("jv_")
                show_legend_table = (
                    bool(legend_table_flags[i])
                    if legend_table_flags and i < len(legend_table_flags)
                    else False
                )

                if is_jv_curve and jv_legend_table:
                    fig.update_layout(showlegend=False)

                if show_legend_table:
                    fig.update_layout(showlegend=False)

                if is_jv_curve:
                    width, height = 800, 600
                elif "boxplot" in name.lower():
                    width, height = 900, 600
                else:
                    width, height = 800, 600

                display_resizable_plot(fig, display_title, width, height, subtitle, filename=name)

                if is_jv_curve and jv_legend_table:
                    legend_html = ResizablePlotManager._build_legend_table(fig)
                    if legend_html:
                        display(HTML(legend_html))

                if show_legend_table:
                    legend_html = ResizablePlotManager._build_legend_table(fig)
                    if legend_html:
                        display(HTML(legend_html))

            except Exception as e:
                print(f"❌ Error displaying plot {i + 1} ({name}): {e}")
                try:
                    display(widgets.HTML(f"<h4>{name} (Fallback Display)</h4>"))
                    if hasattr(fig, "show"):
                        fig.show()
                    else:
                        display(fig)
                except Exception as e2:
                    print(f"❌ Could not display plot {name}: {e2}")
