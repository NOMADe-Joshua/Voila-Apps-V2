"""
SEM Plot Manager
================
Plotly figures, no widgets. The GUI wraps them in go.FigureWidget.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image

OVERLAY_WIDTH = 900  # px on screen; the image keeps its aspect ratio


def png_source(rgb: np.ndarray) -> str:
    """RGB array -> PNG data URI. Sent to the browser instead of the raw array: about ten
    times smaller, which matters because the overlay is re-sent after every click."""
    buffer = io.BytesIO()
    Image.fromarray(rgb.astype(np.uint8)).save(buffer, format="PNG", optimize=False)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def overlay_figure(rgb: np.ndarray, title: str = "") -> go.Figure:
    """The image with outlines as one Image trace. Click events report pixel coordinates
    (x = column, y = row), which the GUI turns into grain/hole clicks or edits."""
    height, width = rgb.shape[:2]
    fig = go.Figure(go.Image(source=png_source(rgb), hoverinfo="x+y"))
    fig.update_layout(
        title=title,
        width=OVERLAY_WIDTH,
        height=int(OVERLAY_WIDTH * height / width) + (40 if title else 10),
        margin=dict(l=0, r=0, t=40 if title else 0, b=0),
        # autorange, not fixed ranges: a double-click restores the ranges the figure was
        # created with, which must be the current image's full extent
        xaxis=dict(visible=False, autorange=True),
        yaxis=dict(visible=False, autorange="reversed", scaleanchor="x"),
        # zoom, not pan: in pan mode Plotly sends no click event for Ctrl+click
        dragmode="zoom",
    )
    return fig


def size_histogram(grains: pd.DataFrame) -> go.Figure:
    """Equivalent-diameter distribution per sample (grains cut by the image edge excluded,
    as in the statistics)."""
    if grains.empty:
        return _empty("No analysed grains yet")
    interior = grains[~grains["touches_edge"].astype(bool)]
    fig = px.histogram(
        interior,
        x="eq_diameter_nm",
        color="sample",
        barmode="overlay",
        histnorm="probability",
        nbins=40,
        opacity=0.65,
        labels={"eq_diameter_nm": "Equivalent grain diameter (nm)"},
    )
    fig.update_layout(title="Grain size distribution", yaxis_title="Fraction of grains", height=380)
    return fig


def sample_bars(samples: pd.DataFrame) -> go.Figure:
    """Mean equivalent diameter per sample, error bars = spread between images."""
    if samples.empty:
        return _empty("No analysed samples yet")
    fig = go.Figure(
        go.Bar(
            x=samples["sample"],
            y=samples["mean_eq_diameter_nm_mean"],
            error_y=dict(type="data", array=samples["mean_eq_diameter_nm_std"].fillna(0)),
            text=[f"{n} img" for n in samples["n_images"]],
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Mean grain diameter per sample (error bar: spread between images)",
        yaxis_title="Mean equivalent diameter (nm)",
        height=380,
    )
    return fig


def thickness_histogram(profiles: pd.DataFrame, by: str = "image") -> go.Figure:
    """Distribution of the film thickness over the image columns (one count per column), per
    image or per sample: narrow for a uniform film, wide or with several peaks otherwise."""
    if profiles.empty:
        return _empty("No analysed cross-sections yet")
    fig = px.histogram(
        profiles[profiles["thickness_nm"] > 0],
        x="thickness_nm",
        color=by,
        barmode="overlay",
        histnorm="probability",
        nbins=50,
        opacity=0.65,
        labels={"thickness_nm": "Film thickness (nm)"},
    )
    fig.update_layout(
        title=f"Film thickness distribution per {by} (every image column)",
        yaxis_title="Fraction of the film width",
        height=380,
    )
    return fig


def thickness_profile(profiles: pd.DataFrame) -> go.Figure:
    """Thickness along the image width, one line per cross-section."""
    if profiles.empty:
        return _empty("No analysed cross-sections yet")
    fig = px.line(
        profiles,
        x="x_nm",
        y="thickness_nm",
        color="image",
        labels={"x_nm": "Position along the image (nm)", "thickness_nm": "Film thickness (nm)"},
        # SVG, not WebGL: plotly express picks WebGL above 1000 points (an image has 1024
        # columns), and browsers without WebGL then show only "WebGL is not supported"
        render_mode="svg",
    )
    fig.update_layout(title="Film thickness along each cross-section", height=380)
    return fig


def _empty(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper")
    fig.update_layout(height=200, xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


def scalebar_script(container_class: str, nm_per_px: float) -> str:
    """JavaScript for a scale bar below the overlay figure inside the element with
    container_class. It runs in the browser and follows every zoom, pan and double-click
    reset: Python is not told about those, so the bar is computed from the figure's current
    x range. Length about 1/10 of the visible width, rounded to 1, 2 or 5 x 10^n nm."""
    return f"""
(function () {{
  window.semScale = window.semScale || {{}};
  window.semScale["{container_class}"] = {nm_per_px};
  function nice(v) {{
    var p = Math.pow(10, Math.floor(Math.log10(v)));
    var m = v / p;
    return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p;
  }}
  function label(nm) {{
    return nm >= 1000 ? (nm / 1000) + " \u00b5m" : nm + " nm";
  }}
  function install(tries) {{
    var box = document.querySelector(".{container_class}");
    var gd = box && box.querySelector(".js-plotly-plot");
    if (!gd || !gd._fullLayout || !gd._fullLayout.xaxis) {{
      if (tries > 0) setTimeout(function () {{ install(tries - 1); }}, 300);
      return;
    }}
    var bar = box.querySelector(".sem-scalebar");
    if (!bar) {{
      bar = document.createElement("div");
      bar.className = "sem-scalebar";
      bar.style.cssText = "margin:4px 0 6px 0;font:13px sans-serif;";
      box.appendChild(bar);  // the wrapper stacks vertically: the bar goes below the image
    }}
    function update() {{
      var xa = gd._fullLayout.xaxis, px = window.semScale["{container_class}"];
      if (!xa || !xa.range || !px) return;
      var visible = Math.abs(xa.range[1] - xa.range[0]);
      var nm = nice(visible * px / 10);
      var width = nm / px / visible * xa._length;
      bar.innerHTML = '<div style="margin-left:' + xa._offset + 'px;width:' + width.toFixed(1) +
        'px;height:5px;background:#000"></div><div class="sem-scalebar-label" style="margin-left:' +
        xa._offset + 'px">' + label(nm) + '</div>';
    }}
    if (!gd._semScalebar) {{
      gd.on("plotly_relayout", update);
      gd.on("plotly_afterplot", update);
      gd._semScalebar = true;
    }}
    update();
  }}
  install(40);
}})();
"""


# ---------------------------------------------------------------------------
# Image exports (PNG files): no plotly, plain pixels
# ---------------------------------------------------------------------------
SCALE_BAR_CORNERS = ("bottom left", "bottom right")
TOP_COLOR, BOTTOM_COLOR = (255, 60, 60), (40, 210, 255)  # film top/bottom, as cross_section.overlay


def draw_rows(rgb: np.ndarray, rows: np.ndarray, color) -> None:
    """A line given as one row per column, 2 px thick (as in cross_section.overlay)."""
    xs = np.arange(rgb.shape[1])
    for dy in (0, 1):
        rgb[np.clip(rows + dy, 0, rgb.shape[0] - 1), xs] = color


def nice_length_nm(target_nm: float) -> float:
    """target rounded to 1, 2 or 5 x 10^n nm (the same rule as the scale bar on screen)."""
    power = 10 ** np.floor(np.log10(target_nm))
    m = target_nm / power
    return float((1 if m < 1.5 else 2 if m < 3.5 else 5 if m < 7.5 else 10) * power)


def length_label(nm: float, micro: str = "µ") -> str:
    """'500 nm', '1 µm', '20 µm' (micro: the sign to use, 'u' when the font has no µ)."""
    if nm >= 1000:
        return f"{nm / 1000:g} {micro}m"
    return f"{nm:g} nm"


def _font(size: int):
    """(font, micro sign). DejaVu Sans from matplotlib has the µ; Pillow's own font does not,
    so without matplotlib the label says 'um'."""
    from PIL import ImageFont

    try:
        import matplotlib

        path = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
        return ImageFont.truetype(str(path), size), "µ"
    except (ImportError, OSError):
        pass
    try:
        return ImageFont.load_default(size=size), "u"
    except TypeError:  # Pillow < 10.1: one small bitmap font only
        return ImageFont.load_default(), "u"


def draw_scale_bar(rgb: np.ndarray, nm_per_px: float, corner: str = "bottom left") -> np.ndarray:
    """A copy of rgb with a classic scale bar |-----| in one bottom corner: a white line with an
    upright tick at each end, about a fifth of the image width long (outer edge of one tick to
    outer edge of the other), rounded to 1, 2 or 5 x 10^n nm, its length written above it, on a
    black box so it reads on bright and dark films. nm_per_px is the pixel size of rgb (from the
    TIFF metadata or entered by hand, divided by any upscaling)."""
    from PIL import ImageDraw

    if corner not in SCALE_BAR_CORNERS:
        raise ValueError(f"corner must be one of {SCALE_BAR_CORNERS}")
    height, width = rgb.shape[:2]
    nm = nice_length_nm(width * nm_per_px / 5)
    bar_px = max(int(round(nm / nm_per_px)), 3)
    font, micro = _font(max(12, height // 28))
    label = length_label(nm, micro)
    image = Image.fromarray(rgb.astype(np.uint8))
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
    text_w, text_h = right - left, bottom - top
    pad = max(4, height // 100)
    line = max(2, round(height / 300))  # line and tick width
    tick = max(6, 5 * line)  # tick height
    box_w = max(bar_px, text_w) + 2 * pad
    box_h = text_h + tick + 3 * pad
    x0 = pad if corner == "bottom left" else width - pad - box_w
    y0 = height - pad - box_h
    draw.rectangle([x0, y0, x0 + box_w, y0 + box_h], fill=(0, 0, 0))
    draw.text((x0 + (box_w - text_w) // 2 - left, y0 + pad - top), label, font=font, fill="white")
    bar_x0 = x0 + (box_w - bar_px) // 2
    bar_x1 = bar_x0 + bar_px - 1
    tick_y0 = y0 + 2 * pad + text_h
    tick_y1 = tick_y0 + tick - 1
    mid = (tick_y0 + tick_y1) // 2
    white = (255, 255, 255)
    draw.rectangle([bar_x0, mid - line // 2, bar_x1, mid - line // 2 + line - 1], fill=white)
    draw.rectangle([bar_x0, tick_y0, bar_x0 + line - 1, tick_y1], fill=white)
    draw.rectangle([bar_x1 - line + 1, tick_y0, bar_x1, tick_y1], fill=white)
    return np.asarray(image).copy()


EXPORT_SCALES = (1, 2, 4)
"""Export sizes: each SEM pixel becomes an n x n block (no smoothing, so no detail is invented
or blurred); the scale bar and its text are drawn afterwards at the larger size, so they are
sharp."""


def upscale(array: np.ndarray, factor: int) -> np.ndarray:
    if factor == 1:
        return array
    return np.repeat(np.repeat(array, factor, axis=0), factor, axis=1)


def png_bytes(rgb: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(rgb.astype(np.uint8)).save(buffer, format="PNG")
    return buffer.getvalue()


def compose_export(
    image_rgb: np.ndarray,
    nm_per_px: float | None,
    banner: np.ndarray | None = None,
    scale_bar: str | None = None,
    scale: int = 1,
) -> np.ndarray:
    """The image as it is exported: enlarged by scale (see EXPORT_SCALES), an optional scale
    bar in a bottom corner of the image itself, then the SEM software's info banner put back
    below it (enlarged the same way)."""
    if scale not in EXPORT_SCALES:
        raise ValueError(f"scale must be one of {EXPORT_SCALES}")
    rgb = upscale(image_rgb, scale)
    if scale_bar and nm_per_px:
        rgb = draw_scale_bar(rgb, nm_per_px / scale, scale_bar)
    if banner is not None and banner.size:
        strip = banner if banner.ndim == 3 else np.repeat(banner[..., None], 3, axis=2)
        strip = upscale(strip[:, : image_rgb.shape[1]].astype(np.uint8), scale)
        rgb = np.vstack([rgb, strip])
    return rgb
