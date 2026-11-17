"""Samples Dashboard plots: samples per author, and per author over time. No widgets."""

import html

import pandas as pd
import plotly.graph_objects as go

GROUPINGS = {
    "Daily": ("D", "%Y-%m-%d", "Day"),
    "Weekly": ("W", "%Y-%m-%d", "Week (Monday)"),
    "Monthly": ("M", "%Y-%m", "Month"),
    "Yearly": ("Y", "%Y", "Year"),
}
"""Label: (pandas period, label format, axis title). A week is labelled with its Monday."""


def filter_by_date(samples, start=None, end=None):
    """Samples uploaded between start and end (dates, both included; None = open)."""
    days = samples["upload_date"].dt.normalize()
    mask = pd.Series(True, index=samples.index)
    if start is not None:
        mask &= days >= pd.Timestamp(start)
    if end is not None:
        mask &= days <= pd.Timestamp(end)
    return samples[mask]


def author_counts(authors) -> pd.DataFrame:
    """Samples per author, most first: columns Author, Samples."""
    counts = authors.value_counts()
    return pd.DataFrame({"Author": counts.index, "Samples": counts.to_numpy()})


def time_counts(dates, authors, grouping="Monthly") -> pd.DataFrame:
    """Samples per period (rows, labelled as text) and author (columns)."""
    period, label, axis = GROUPINGS[grouping]
    frame = pd.DataFrame({"date": dates, "author": authors}).dropna(subset=["date"])
    if frame.empty:
        return pd.DataFrame()
    frame["period"] = frame["date"].dt.to_period(period).dt.start_time
    table = frame.groupby(["period", "author"]).size().unstack(fill_value=0).sort_index()
    table.index = pd.Index([stamp.strftime(label) for stamp in table.index], name=axis)
    order = table.sum().sort_values(ascending=False).index
    return table[order]


def _escape(text):
    return html.escape(str(text))


def author_figure(counts, title="Samples by author") -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=[_escape(a) for a in counts["Author"]],
            y=counts["Samples"],
            text=counts["Samples"],
            textposition="auto",
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="Author",
        yaxis_title="Number of samples",
        xaxis={"tickangle": 45, "type": "category"},
        height=550,
        margin={"b": 140},
    )
    return fig


def time_figure(table, stacked=True, title="Samples over time") -> go.Figure:
    fig = go.Figure()
    for author in table.columns:
        fig.add_trace(
            go.Bar(
                name=_escape(author),
                x=list(table.index),
                y=table[author],
                hovertemplate="<b>%{fullData.name}</b><br>%{x}<br>Samples: %{y}<extra></extra>",
            )
        )
    fig.update_layout(
        title=title,
        barmode="stack" if stacked else "group",
        xaxis_title=table.index.name or "Period",
        yaxis_title="Number of samples",
        xaxis={"type": "category"},
        legend_title_text="Author",
        height=550,
    )
    return fig
