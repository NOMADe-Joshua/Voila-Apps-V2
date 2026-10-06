"""
Resizable Plot Utility for UVVis Analysis Application
Adds resizable containers to Plotly figures in Jupyter notebooks
Copied from JV-Analysis for UVVis Analyzer.
"""

__author__ = "Joshua Damm"
__institution__ = "KIT"
__created__ = "December 2025"

import json
import uuid

import ipywidgets as widgets
import plotly.graph_objects as go
import plotly.utils
from IPython.display import HTML, display


class ResizablePlotWidget:
    """Creates resizable Plotly plots for Jupyter notebooks"""

    def __init__(self, fig, title="Plot", initial_width=800, initial_height=600, subtitle=None):
        self.fig = fig
        self.title = title
        self.subtitle = subtitle
        self.initial_width = initial_width
        self.initial_height = initial_height
        self.plot_id = f"plot_{uuid.uuid4().hex[:8]}"

    def display(self):
        """Display the resizable plot with external title"""
        # Update figure layout
        self.fig.update_layout(
            autosize=True,
            margin=dict(l=80, r=50, t=80, b=80, autoexpand=False),
            xaxis=dict(
                autorange=False if self.fig.layout.xaxis.range else True,
                constrain="domain",
                automargin=False,
            ),
            yaxis=dict(automargin=False),
            legend=dict(),  # Draggable legend enabled automatically
        )

        # Convert figure to JSON
        fig_json = json.dumps(self.fig, cls=plotly.utils.PlotlyJSONEncoder)

        # Create title HTML
        title_html = f'<h3 style="margin: 20px 0 5px 0; color: #2c3e50;">{self.title}</h3>'
        if self.subtitle:
            title_html += (
                f'<p style="margin: 0 0 10px 0; color: #666; font-size: 12px;">{self.subtitle}</p>'
            )

        # Resizable HTML container
        resizable_html = f'''
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        
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
                figureData.layout.margin.autoexpand = false;
                
                if (figureData.layout.xaxis) {{
                    figureData.layout.xaxis.automargin = false;
                }}
                if (figureData.layout.yaxis) {{
                    figureData.layout.yaxis.automargin = false;
                }}
            }}
            
            let originalXRange = null;
            if (figureData.layout && figureData.layout.xaxis && figureData.layout.xaxis.range) {{
                originalXRange = [...figureData.layout.xaxis.range];
            }}
            
            function initPlot() {{
                const plotDiv = document.getElementById('{self.plot_id}');
                const container = document.getElementById('container-{self.plot_id}');

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
                        const plainPrefix  = 'data:image/svg+xml,';

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

                const svgDownloadButton = {{
                    name: 'Save as SVG',
                    icon: Plotly.Icons.camera,
                    click: function(gd) {{
                        downloadSvgViaPlotly(gd, 'uvvis_plot_export.svg').catch(function(err) {{
                            console.error('❌ SVG download failed:', err);
                        }});
                    }}
                }};

                const pngDownloadButton = {{
                    name: 'Download PNG (~600dpi)',
                    icon: Plotly.Icons.camera,
                    click: function(gd) {{
                        downloadPngViaPlotly(gd, 'uvvis_plot_export_600dpi.png', 6).catch(function(err) {{
                            console.error('❌ PNG download failed:', err);
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
                                'xaxis.automargin': false
                            }});
                        }}
                    }});
                    
                    if (window.ResizeObserver) {{
                        let resizeTimeout;
                        const observer = new ResizeObserver(function(entries) {{
                            clearTimeout(resizeTimeout);
                            resizeTimeout = setTimeout(function() {{
                                const rect = container.getBoundingClientRect();
                                
                                const updateLayout = {{
                                    width: rect.width,
                                    height: rect.height,
                                    'margin.autoexpand': false
                                }};
                                
                                if (originalXRange) {{
                                    updateLayout['xaxis.range'] = originalXRange;
                                    updateLayout['xaxis.autorange'] = false;
                                    updateLayout['xaxis.automargin'] = false;
                                }}
                                
                                Plotly.relayout(plotDiv, updateLayout);
                            }}, 100);
                        }});
                        observer.observe(container);
                    }}
                }}).catch(function(err) {{
                    console.error('❌ Plot creation failed:', err);
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
                        }}
                    }}
                    checkCount++;
                }}, 100);
            }}
        }})();
        </script>
        '''

        display(HTML(resizable_html))


def create_resizable_plot(fig, title="Plot", width=800, height=600, subtitle=None):
    """Create a resizable plot from a Plotly figure"""
    return ResizablePlotWidget(fig, title, width, height, subtitle)


def display_resizable_plot(fig, title="Plot", width=800, height=600, subtitle=None):
    """Convenience function to create and immediately display a resizable plot"""
    resizable_plot = create_resizable_plot(fig, title, width, height, subtitle)
    resizable_plot.display()


class ResizablePlotManager:
    """Enhanced plot manager that creates resizable plots"""

    @staticmethod
    def display_plots_resizable(figs, names, titles=None, subtitles=None, container_widget=None):
        """Display multiple plots as resizable widgets"""
        if container_widget:
            with container_widget:
                ResizablePlotManager._display_plots_internal(figs, names, titles, subtitles)
        else:
            ResizablePlotManager._display_plots_internal(figs, names, titles, subtitles)

    @staticmethod
    def _display_plots_internal(figs, names, titles=None, subtitles=None):
        """Internal method to display plots"""
        from IPython.display import clear_output

        clear_output(wait=True)

        print(f"✅ Successfully created {len(figs)} resizable plots")
        print("💡 Drag the bottom-right corner of each plot to resize")
        print()

        for i, (fig, name) in enumerate(zip(figs, names)):
            try:
                display_title = titles[i] if titles and i < len(titles) else name
                subtitle = subtitles[i] if subtitles and i < len(subtitles) else None

                # Determine size based on plot type
                if "histogram" in name.lower():
                    width, height = 700, 500
                elif "spectra" in name.lower() or "uvvis" in name.lower():
                    width, height = 800, 600
                else:
                    width, height = 800, 600

                display_resizable_plot(fig, display_title, width, height, subtitle)

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
