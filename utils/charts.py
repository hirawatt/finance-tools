"""Reusable, deliberately-designed Plotly chart builders.

Every figure the dashboard renders is built here, so the visual grammar lives
in one place and the pages stay about *what* they show rather than *how* it is
drawn. The functions are pure — they take pandas objects and return
``plotly`` figures — so they can be unit-tested without Streamlit or a network.

Design references, and what each one contributed:

* **Financial Times Visual Vocabulary** — the chart type follows the
  relationship in the data: deviation is a diverging bar, a two-point
  comparison is a dumbbell, a part-to-whole is a donut, a range over time is a
  fan.
* **Stripe / Linear dashboards** — no chartjunk: hairline gridlines, muted
  axes, no boxed plot area, generous whitespace and one confident accent.
* **Bloomberg / TradingView terminals** — numbers first, and values labelled
  directly on the mark where it helps, so the eye does not chase a legend.
* **Koyfin / Simply Wall St** — donuts that carry a centre total, ranking bars
  sorted by size, and peer comparisons against a reference line.
* **Zerodha Console / Sensibull** — market semantics for Indian desks: gains
  green, losses red, and open interest split cleanly into calls and puts.

The colour constants mirror ``.streamlit/config.toml`` (Streamlit owns the
native theme, this module owns the figures it cannot reach), so a palette change
lands in both files together.
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# ---- Palette (mirrors .streamlit/config.toml) ---------------------------- #
FONT = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"

INK = "#0B1220"
MUTED = "#64748B"
LINE = "#E2E8F0"
GRID = "#EEF2F7"
SURFACE = "#FFFFFF"
ACCENT = "#1F6FEB"
GAIN = "#0FA678"
LOSS = "#E5484D"
WARN = "#E8A33D"

CATEGORICAL = [
    "#1F6FEB",
    "#12B886",
    "#F59F00",
    "#E03131",
    "#7048E8",
    "#1098AD",
    "#F76707",
    "#4C6EF5",
    "#868E96",
    "#D6336C",
]

DIVERGING = [
    "#7F1D1D",
    "#B91C1C",
    "#E03131",
    "#F1737F",
    "#F9C2C6",
    "#C6DBFB",
    "#8FB6F5",
    "#4F8BF0",
    "#1B5FD0",
    "#123A80",
]

#: Signed colours shared by every "up/down" mark, so green always means up.
SIGN_COLORS = (LOSS, GAIN)


def _rgba(hex_color: str, alpha: float) -> str:
    """``#RRGGBB`` with an alpha channel, for fills and shaded bands."""
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def _hover(fmt: str, ref: str) -> str:
    """A ``str.format`` number pattern as a Plotly hover token.

    ``"₹{:,.0f}"`` with ``ref="x"`` becomes ``"₹%{x:,.0f}"`` and ``"{:+.1%}"``
    becomes ``"%{x:+.1%}"`` — the same translation the table formatting uses, so
    chart labels and table cells read identically.
    """
    prefix, _, rest = fmt.partition("{")
    spec, _, suffix = rest.partition("}")
    return f"{prefix}%{{{ref}{spec}}}{suffix}"


def _labels(values: Sequence) -> list:
    return [str(v) for v in values]


def _as_array(values: Sequence):
    """A float array when the values are numeric, else the values untouched.

    Scatters plot dates and categorical labels on an axis too (an earnings
    timeline), so coercion has to be best-effort rather than assumed.
    """
    try:
        return np.asarray(list(values), dtype=float)
    except (TypeError, ValueError):
        return list(values)


def _axis_range(values: Sequence[float], pad: float = 1.25) -> list:
    """A tidy value-axis range that leaves room for directly-labelled marks."""
    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return [0, 1]
    bound = float(np.max(np.abs(array))) or 1.0
    if (array < 0).any():
        return [-bound * pad, bound * pad]
    return [0, bound * pad]


def style(
    fig: go.Figure,
    *,
    height: Optional[int] = None,
    x_title: Optional[str] = None,
    y_title: Optional[str] = None,
    x_grid: bool = False,
    y_grid: bool = True,
    x_tickformat: Optional[str] = None,
    y_tickformat: Optional[str] = None,
    x_range: Optional[Sequence[float]] = None,
    y_range: Optional[Sequence[float]] = None,
    legend: Optional[str] = "h",
    hovermode: str = "closest",
    zeroline: bool = False,
) -> go.Figure:
    """Apply the dashboard's shared chart grammar to ``fig``.

    ``legend`` is ``"h"`` (a row above the plot), ``"v"`` (a column at the
    right), or ``None`` to hide it. Gridlines are horizontal by default —
    values are read off the y-axis — and every surface is transparent so the
    surrounding card supplies the background.
    """
    traces = list(fig.data)

    if legend is None:
        showlegend = False
        legend_layout = dict()
        top = 8
    elif legend == "v":
        showlegend = True
        legend_layout = dict(
            orientation="v",
            x=1.02,
            xanchor="left",
            y=1,
            yanchor="top",
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=12),
        )
        top = 8
    else:
        visible = any(trace.showlegend is not False for trace in traces)
        showlegend = visible
        legend_layout = dict(
            orientation="h",
            x=0,
            xanchor="left",
            y=1.02,
            yanchor="bottom",
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=12),
        )
        top = 34 if visible else 8

    fig.update_layout(
        template="none",
        font=dict(family=FONT, size=13, color=INK),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=CATEGORICAL,
        margin=dict(l=8, r=8, t=top, b=8),
        height=height,
        showlegend=showlegend,
        legend=legend_layout,
        hovermode=hovermode,
        hoverlabel=dict(
            bgcolor=SURFACE,
            bordercolor=LINE,
            font=dict(family=FONT, size=12, color=INK),
            align="left",
        ),
        bargap=0.35,
    )

    axis = dict(
        showline=False,
        zeroline=zeroline,
        ticks="outside",
        ticklen=4,
        tickcolor=LINE,
        tickfont=dict(size=12, color=MUTED),
        title_font=dict(size=12, color=MUTED),
        automargin=True,
    )
    x_axis = {**axis, "showgrid": x_grid, "gridcolor": GRID, "gridwidth": 1}
    y_axis = {**axis, "showgrid": y_grid, "gridcolor": GRID, "gridwidth": 1}
    if x_title is not None:
        x_axis["title_text"] = x_title
    if y_title is not None:
        y_axis["title_text"] = y_title
    if x_tickformat is not None:
        x_axis["tickformat"] = x_tickformat
    if y_tickformat is not None:
        y_axis["tickformat"] = y_tickformat
    if x_range is not None:
        x_axis["range"] = list(x_range)
    if y_range is not None:
        y_axis["range"] = list(y_range)
    fig.update_xaxes(**x_axis)
    fig.update_yaxes(**y_axis)
    return fig


# ---- Part-to-whole ------------------------------------------------------- #
def donut(
    values: Mapping[str, float] | pd.Series,
    *,
    hole: float = 0.62,
    max_slices: int = 8,
    center_title: Optional[str] = None,
    center_value: Optional[str] = None,
    value_fmt: str = "{:,.0f}",
    hover_units: str = "",
    height: int = 320,
) -> go.Figure:
    """A donut for a part-to-whole split, with a centre total.

    The smallest slices are folded into ``Other`` past ``max_slices`` so the
    ring stays readable, and the legend (not on-slice text) carries the names
    once there are more than a handful of categories.
    """
    series = pd.Series(values).dropna()
    series = series[series > 0].sort_values(ascending=False)
    if series.empty:
        return style(go.Figure(), height=height, legend=None)

    if len(series) > max_slices:
        head = series.iloc[: max_slices - 1]
        tail = pd.Series(
            {f"Other ({len(series) - len(head)})": float(series.iloc[max_slices - 1 :].sum())}
        )
        series = pd.concat([head, tail])

    numbers = series.to_numpy(dtype=float)
    colors = [CATEGORICAL[i % len(CATEGORICAL)] for i in range(len(numbers))]

    fig = go.Figure(
        go.Pie(
            labels=_labels(series.index),
            values=numbers,
            hole=hole,
            sort=False,
            direction="clockwise",
            marker=dict(colors=colors, line=dict(color=SURFACE, width=2)),
            textinfo="percent",
            textposition="inside",
            insidetextorientation="radial",
            textfont=dict(size=12, color="#FFFFFF"),
            hovertemplate="<b>%{label}</b><br>"
            + _hover(value_fmt, "value")
            + hover_units
            + "<br>%{percent}<extra></extra>",
        )
    )

    if center_value is not None or center_title is not None:
        title_html = (
            f"<span style='font-size:11px;letter-spacing:.08em;color:{MUTED}'>"
            f"{center_title.upper()}</span><br>"
            if center_title
            else ""
        )
        value_html = (
            f"<b style='font-size:20px;color:{INK}'>{center_value}</b>"
            if center_value
            else ""
        )
        fig.add_annotation(
            text=title_html + value_html,
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            align="center",
        )
    return style(fig, height=height)


# ---- Ranking ------------------------------------------------------------- #
def barh(
    labels: Sequence,
    values: Sequence[float],
    *,
    value_fmt: str = "{:,.0f}",
    color: str = ACCENT,
    colors: Optional[Sequence[str]] = None,
    hover_units: str = "",
    x_title: Optional[str] = None,
    x_tickformat: Optional[str] = None,
    threshold: Optional[float] = None,
    threshold_label: Optional[str] = None,
    show_values: bool = True,
    height: Optional[int] = None,
    sort: bool = True,
) -> go.Figure:
    """A horizontal ranking bar: largest at the top, values on the marks.

    ``colors`` colours each bar individually (market red/green, a diverging
    scale), while ``color`` is a single fill. ``threshold`` draws a vertical
    reference line — a target, a policy cap, a signal level.
    """
    numbers = np.asarray(list(values), dtype=float)
    names = _labels(labels)
    order = np.argsort(numbers) if sort else np.arange(len(numbers))
    names = [names[i] for i in order]
    numbers = numbers[order]
    marker_colors = [colors[i] for i in order] if colors is not None else color

    fig = go.Figure(
        go.Bar(
            x=numbers,
            y=names,
            orientation="h",
            marker=dict(color=marker_colors),
            text=[value_fmt.format(v) for v in numbers] if show_values else None,
            textposition="outside",
            cliponaxis=False,
            textfont=dict(size=12, color=INK),
            hovertemplate="<b>%{y}</b><br>"
            + _hover(value_fmt, "x")
            + hover_units
            + "<extra></extra>",
        )
    )
    if threshold is not None:
        fig.add_vline(
            x=threshold,
            line=dict(color=MUTED, width=1.4, dash="dash"),
            annotation_text=threshold_label or f"{threshold:,.0f}",
            annotation_position="top",
            annotation_font=dict(size=11, color=MUTED),
        )
    span_values = list(numbers) + ([threshold] if threshold is not None else [])
    fig = style(
        fig,
        height=height,
        legend=None,
        x_title=x_title,
        x_tickformat=x_tickformat,
        x_grid=True,
        y_grid=False,
        x_range=_axis_range(span_values),
    )
    return fig


def diverging_barh(
    labels: Sequence,
    values: Sequence[float],
    *,
    value_fmt: str = "{:+,.0f}",
    hover_units: str = "",
    x_title: Optional[str] = None,
    height: Optional[int] = None,
) -> go.Figure:
    """A signed ranking bar — gains green, losses red, sorted by size."""
    numbers = np.asarray(list(values), dtype=float)
    names = _labels(labels)
    order = np.argsort(numbers)
    names = [names[i] for i in order]
    numbers = numbers[order]
    colors = [GAIN if v >= 0 else LOSS for v in numbers]

    fig = go.Figure(
        go.Bar(
            x=numbers,
            y=names,
            orientation="h",
            marker=dict(color=colors),
            text=[value_fmt.format(v) for v in numbers],
            textposition="outside",
            cliponaxis=False,
            textfont=dict(size=12, color=INK),
            hovertemplate="<b>%{y}</b><br>"
            + _hover(value_fmt, "x")
            + hover_units
            + "<extra></extra>",
        )
    )
    fig.add_vline(x=0, line=dict(color=LINE, width=1))
    return style(
        fig,
        height=height,
        legend=None,
        x_title=x_title,
        x_grid=True,
        y_grid=False,
        x_range=_axis_range(list(numbers) or [1.0]),
    )


# ---- Comparison ---------------------------------------------------------- #
def dumbbell(
    labels: Sequence,
    start: Sequence[float],
    end: Sequence[float],
    *,
    start_name: str = "Current",
    end_name: str = "Target",
    value_fmt: str = "{:.1f}%",
    height: Optional[int] = None,
    x_title: Optional[str] = None,
    sort: bool = True,
) -> go.Figure:
    """A dumbbell: two values per row joined by a connector.

    The clearest way to show a movement — here the gap between a current weight
    and a target weight — because the eye reads the length of the connector as
    the size of the change.
    """
    left = np.asarray(list(start), dtype=float)
    right = np.asarray(list(end), dtype=float)
    names = _labels(labels)
    if sort:
        order = np.argsort(right)
        names = [names[i] for i in order]
        left, right = left[order], right[order]

    line_x: list = []
    line_y: list = []
    for name, a, b in zip(names, left, right):
        line_x += [a, b, None]
        line_y += [name, name, None]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=line_x,
            y=line_y,
            mode="lines",
            line=dict(color=LINE, width=3),
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=left,
            y=names,
            mode="markers",
            name=start_name,
            marker=dict(color="#CBD5E1", size=11, line=dict(color=SURFACE, width=1)),
            hovertemplate="<b>%{y}</b><br>" + start_name + " " + _hover(value_fmt, "x") + "<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=right,
            y=names,
            mode="markers",
            name=end_name,
            marker=dict(color=ACCENT, size=11, line=dict(color=SURFACE, width=1)),
            hovertemplate="<b>%{y}</b><br>" + end_name + " " + _hover(value_fmt, "x") + "<extra></extra>",
        )
    )
    fig.add_vline(x=0, line=dict(color=LINE, width=1))
    return style(
        fig,
        height=height,
        legend="h",
        x_title=x_title,
        x_grid=True,
        y_grid=False,
        x_range=_axis_range(list(left) + list(right) + [0.0]),
    )


# ---- Relationship -------------------------------------------------------- #
def heatmap(
    matrix: pd.DataFrame,
    *,
    value_fmt: str = ".2f",
    colorbar_title: Optional[str] = None,
    height: Optional[int] = None,
    mask_upper: bool = True,
) -> go.Figure:
    """A diverging heatmap for a symmetric matrix such as correlations.

    The redundant upper triangle is masked so the eye is not asked to read the
    same cell twice; cell text is shown only while the labels stay legible.
    """
    frame = pd.DataFrame(matrix)
    values = frame.to_numpy(dtype=float)
    if mask_upper:
        values = np.where(np.triu(np.ones_like(values, dtype=bool), k=0), np.nan, values)
    text = [[f"{v:{value_fmt}}" if np.isfinite(v) else "" for v in row] for row in values]
    show_text = len(frame) <= 14

    fig = go.Figure(
        go.Heatmap(
            z=values,
            x=_labels(frame.columns),
            y=_labels(frame.index),
            zmin=-1,
            zmax=1,
            colorscale=[[i / (len(DIVERGING) - 1), c] for i, c in enumerate(DIVERGING)],
            text=text,
            texttemplate="%{text}" if show_text else None,
            textfont=dict(size=11),
            hovertemplate="%{y} · %{x}<br>%{z:.2f}<extra></extra>",
            colorbar=dict(
                orientation="h",
                y=-0.18,
                x=0.5,
                xanchor="center",
                len=0.55,
                thickness=10,
                outlinewidth=0,
                tickfont=dict(size=11, color=MUTED),
                title=dict(text=colorbar_title, font=dict(size=11, color=MUTED)),
            ),
            xgap=2,
            ygap=2,
        )
    )
    fig.update_xaxes(side="bottom")
    fig = style(fig, height=height, legend=None, x_grid=False, y_grid=False)
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(margin=dict(l=8, r=8, t=8, b=64))
    return fig


def scatter(
    x: Sequence[float],
    y: Sequence[float],
    *,
    labels: Optional[Sequence] = None,
    sizes: Optional[Sequence[float]] = None,
    color: Optional[Sequence[str] | str] = None,
    color_values: Optional[Sequence[float]] = None,
    colorbar_title: Optional[str] = None,
    x_title: Optional[str] = None,
    y_title: Optional[str] = None,
    x_ref: Optional[float] = None,
    y_ref: Optional[float] = None,
    x_fmt: str = "{:,.2f}",
    y_fmt: str = "{:,.2f}",
    name: Optional[str] = None,
    height: Optional[int] = None,
    hover: Optional[str] = None,
    customdata: Optional[Sequence] = None,
) -> go.Figure:
    """A scatter with optional sizing, colour and zero/reference guides.

    Used for relationships — volatility against return, volume against the
    day's move — where a quadrant or a reference line tells the story at a
    glance. ``hover`` overrides the generated template when a series needs
    dates or other custom fields (paired with ``customdata``).
    """
    x_values = _as_array(x)
    y_values = _as_array(y)
    label_text = _labels(labels) if labels is not None else None

    marker: dict = dict(
        line=dict(color=SURFACE, width=1),
        opacity=0.9,
    )
    if color_values is not None:
        marker.update(
            color=list(color_values),
            colorscale=[[i / (len(DIVERGING) - 1), c] for i, c in enumerate(DIVERGING)],
            cmid=0,
            showscale=True,
            colorbar=dict(
                orientation="v",
                thickness=10,
                outlinewidth=0,
                tickfont=dict(size=11, color=MUTED),
                title=dict(text=colorbar_title, font=dict(size=11, color=MUTED)),
            ),
        )
    else:
        marker["color"] = color if color is not None else ACCENT

    if sizes is not None:
        size_values = np.asarray(list(sizes), dtype=float)
        marker["size"] = size_values
        marker["sizemode"] = "area"
        peak = float(np.max(size_values)) if size_values.size else 1.0
        marker["sizeref"] = 2.0 * peak / (30.0**2) if peak > 0 else 1.0
    else:
        marker["size"] = 11

    if hover is None:
        hover = "<b>%{text}</b><br>" if label_text is not None else ""
        hover += (x_title or "x") + ": " + _hover(x_fmt, "x") + "<br>"
        hover += (y_title or "y") + ": " + _hover(y_fmt, "y") + "<extra></extra>"

    fig = go.Figure(
        go.Scatter(
            x=x_values,
            y=y_values,
            mode="markers+text" if label_text is not None and len(label_text) <= 26 else "markers",
            text=label_text,
            textposition="top center",
            textfont=dict(size=10, color=MUTED),
            marker=marker,
            name=name,
            customdata=customdata,
            hovertemplate=hover,
        )
    )
    if x_ref is not None:
        fig.add_vline(x=x_ref, line=dict(color=LINE, width=1, dash="dot"))
    if y_ref is not None:
        fig.add_hline(y=y_ref, line=dict(color=LINE, width=1, dash="dot"))
    return style(
        fig,
        height=height,
        legend=None,
        x_title=x_title,
        y_title=y_title,
        x_grid=True,
        y_grid=True,
    )


# ---- Time series --------------------------------------------------------- #
def fan(
    frame: pd.DataFrame,
    *,
    x: Optional[Sequence] = None,
    bands: Sequence[tuple[str, str]] = (("P5", "P95"), ("P25", "P75")),
    center: str = "P50",
    center_name: str = "Median",
    x_title: Optional[str] = None,
    y_title: Optional[str] = None,
    height: Optional[int] = None,
) -> go.Figure:
    """A forecast fan: nested percentile bands with the median in front.

    Each ``(low, high)`` band is a shaded region, widest first, so uncertainty
    reads as distance from the middle rather than a tangle of lines.
    """
    axis = list(x) if x is not None else list(frame.index)
    fig = go.Figure()
    shades = (0.10, 0.22, 0.32)
    for index, (low, high) in enumerate(bands):
        if low not in frame or high not in frame:
            continue
        alpha = shades[min(index, len(shades) - 1)]
        fig.add_trace(
            go.Scatter(
                x=axis,
                y=frame[high],
                mode="lines",
                line=dict(width=0),
                hoverinfo="skip",
                showlegend=False,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=axis,
                y=frame[low],
                mode="lines",
                line=dict(width=0),
                fill="tonexty",
                fillcolor=_rgba(ACCENT, alpha),
                name=f"{low[1:]}–{high[1:]} percentile",
                hovertemplate="%{y:,.0f}<extra></extra>",
            )
        )

    if center in frame:
        fig.add_trace(
            go.Scatter(
                x=axis,
                y=frame[center],
                mode="lines",
                line=dict(color=ACCENT, width=3),
                name=center_name,
                hovertemplate="%{y:,.0f}<extra></extra>",
            )
        )
    return style(
        fig,
        height=height,
        legend="h",
        x_title=x_title,
        y_title=y_title,
        x_grid=False,
        y_grid=True,
        hovermode="x unified",
    )


def lines(
    frame: pd.DataFrame,
    *,
    x: Optional[Sequence] = None,
    colors: Optional[Mapping[str, str] | Sequence[str]] = None,
    value_fmt: str = "{:,.2f}",
    x_title: Optional[str] = None,
    y_title: Optional[str] = None,
    height: Optional[int] = None,
    hovermode: str = "x unified",
    fill_first: bool = False,
    width: float = 2.4,
) -> go.Figure:
    """One line per column over a shared x-axis, with a hover that reads across."""
    axis = list(x) if x is not None else list(frame.index)
    fig = go.Figure()
    for index, column in enumerate(frame.columns):
        if isinstance(colors, Mapping):
            color = colors.get(column, CATEGORICAL[index % len(CATEGORICAL)])
        elif colors is not None:
            color = colors[index % len(colors)]
        else:
            color = CATEGORICAL[index % len(CATEGORICAL)]
        first = index == 0
        fig.add_trace(
            go.Scatter(
                x=axis,
                y=frame[column],
                mode="lines",
                name=str(column),
                line=dict(color=color, width=width),
                fill="tozeroy" if (fill_first and first) else None,
                fillcolor=_rgba(color, 0.10) if (fill_first and first) else None,
                hovertemplate=_hover(value_fmt, "y") + "<extra></extra>",
            )
        )
    return style(
        fig,
        height=height,
        legend="h",
        x_title=x_title,
        y_title=y_title,
        x_grid=False,
        y_grid=True,
        hovermode=hovermode,
    )


def underwater(
    drawdown: pd.Series,
    *,
    x_title: Optional[str] = None,
    y_title: str = "Drawdown",
    height: Optional[int] = None,
) -> go.Figure:
    """The underwater plot: how far the portfolio sits below its own peak."""
    fig = go.Figure(
        go.Scatter(
            x=list(drawdown.index),
            y=drawdown.to_numpy(),
            mode="lines",
            line=dict(color=LOSS, width=1.6),
            fill="tozeroy",
            fillcolor=_rgba(LOSS, 0.14),
            name="Drawdown",
            hovertemplate="%{y:.2%}<extra></extra>",
        )
    )
    fig.add_hline(y=0, line=dict(color=LINE, width=1))
    return style(
        fig,
        height=height,
        legend=None,
        x_title=x_title,
        y_title=y_title,
        x_grid=False,
        y_grid=True,
        hovermode="x unified",
    )


def histogram(
    values: Sequence[float],
    *,
    bins: int = 40,
    color: str = ACCENT,
    markers: Sequence[tuple[float, str]] = (),
    x_title: Optional[str] = None,
    y_title: str = "Companies",
    height: Optional[int] = 300,
) -> go.Figure:
    """A distribution histogram with optional labelled reference lines.

    Used for the price band on the screener: the shape shows where the universe
    clusters, and the markers show where the budget cuts it.
    """
    fig = go.Figure(
        go.Histogram(
            x=list(values),
            nbinsx=bins,
            marker=dict(color=_rgba(color, 0.85), line=dict(color=SURFACE, width=0.5)),
            hovertemplate="%{x}<br>%{y} companies<extra></extra>",
        )
    )
    for position, label in markers:
        fig.add_vline(
            x=position,
            line=dict(color=INK, width=1.4, dash="dash"),
            annotation_text=label,
            annotation_position="top",
            annotation_font=dict(size=11, color=INK),
        )
    fig.update_layout(bargap=0.06)
    return style(
        fig,
        height=height,
        legend=None,
        x_title=x_title,
        y_title=y_title,
        x_grid=False,
        y_grid=True,
        y_tickformat=",.0f",
    )


def vertical_bar(
    labels: Sequence,
    values: Sequence[float],
    *,
    value_fmt: str = "{:,.0f}",
    color: Optional[Sequence[str] | str] = None,
    y_title: Optional[str] = None,
    height: Optional[int] = None,
    reference: Optional[float] = None,
    reference_label: Optional[str] = None,
) -> go.Figure:
    """A simple vertical bar, coloured per bar or as one series."""
    fig = go.Figure(
        go.Bar(
            x=_labels(labels),
            y=list(values),
            marker=dict(color=color if color is not None else ACCENT),
            text=[value_fmt.format(v) for v in values],
            textposition="outside",
            cliponaxis=False,
            textfont=dict(size=12, color=INK),
            hovertemplate="<b>%{x}</b><br>" + _hover(value_fmt, "y") + "<extra></extra>",
        )
    )
    if reference is not None:
        fig.add_hline(
            y=reference,
            line=dict(color=MUTED, width=1.4, dash="dash"),
            annotation_text=reference_label or f"{reference:,.0f}",
            annotation_position="top left",
            annotation_font=dict(size=11, color=MUTED),
        )
    return style(fig, height=height, legend=None, y_title=y_title, x_grid=False, y_grid=True)


__all__ = [
    "ACCENT",
    "CATEGORICAL",
    "DIVERGING",
    "GAIN",
    "LOSS",
    "WARN",
    "SIGN_COLORS",
    "barh",
    "diverging_barh",
    "donut",
    "dumbbell",
    "fan",
    "heatmap",
    "histogram",
    "lines",
    "scatter",
    "style",
    "underwater",
    "vertical_bar",
]
