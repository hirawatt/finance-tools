"""Unit tests for the shared Plotly chart builders.

``utils.charts`` is pure — pandas in, a Plotly figure out — so every builder can
be checked without Streamlit or a network. These tests pin the design decisions
that are easy to regress: sorted rankings, sign colours, masked heatmap halves,
banded fans and reference lines.
"""

import numpy as np
import pandas as pd
import pytest

from utils import charts


def test_style_paints_the_brand_without_a_plotly_template():
    fig = charts.style(charts.barh(["A"], [1.0]), height=200)
    # "none" template: no inherited axis/background styling to fight the module.
    assert fig.layout.template.layout.to_plotly_json() == {}
    assert fig.layout.font.color == charts.INK
    assert fig.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert fig.layout.plot_bgcolor == "rgba(0,0,0,0)"
    assert fig.layout.colorway == tuple(charts.CATEGORICAL)
    assert fig.layout.height == 200


def test_donut_folds_small_slices_and_centres_the_total():
    values = pd.Series({f"S{i}": 10 - i for i in range(10)})  # ten slices
    fig = charts.donut(values, max_slices=5, center_title="Total", center_value="₹55")
    trace = fig.data[0]
    assert len(trace.labels) == 5
    assert trace.labels[-1].startswith("Other")
    assert fig.layout.annotations and "₹55" in fig.layout.annotations[0].text


def test_barh_ranks_ascending_so_the_largest_sits_on_top():
    fig = charts.barh(["A", "B", "C"], [3, 1, 2])
    assert list(fig.data[0].y) == ["B", "C", "A"]
    assert list(fig.data[0].x) == [1, 2, 3]


def test_barh_colours_follow_each_bar_when_sorted():
    colors = ["red", "green", "blue"]  # aligned with A, B, C above
    fig = charts.barh(["A", "B", "C"], [3, 1, 2], colors=colors)
    assert list(fig.data[0].marker.color) == ["green", "blue", "red"]


def test_diverging_barh_signs_its_colours():
    fig = charts.diverging_barh(["A", "B"], [5, -3])
    colors = list(fig.data[0].marker.color)
    assert charts.GAIN in colors and charts.LOSS in colors


def test_dumbbell_draws_a_connector_and_two_markers():
    fig = charts.dumbbell(["A", "B"], [10, 20], [15, 12])
    assert len(fig.data) == 3
    assert fig.data[1].name == "Current"
    assert fig.data[2].name == "Target"


def test_heatmap_masks_the_redundant_upper_triangle():
    matrix = pd.DataFrame([[1.0, 0.4], [0.4, 1.0]], index=["A", "B"], columns=["A", "B"])
    fig = charts.heatmap(matrix)
    z = np.asarray(fig.data[0].z, dtype=float)
    assert np.isnan(z[0, 0]) and np.isnan(z[0, 1])  # upper triangle + diagonal masked
    assert z[1, 0] == pytest.approx(0.4)
    assert fig.data[0].zmin == -1 and fig.data[0].zmax == 1


def test_fan_layers_bands_behind_the_median():
    steps = range(6)
    frame = pd.DataFrame(
        {
            "P5": [10, 9, 8, 7, 6, 5],
            "P25": [10, 11, 11, 12, 12, 13],
            "P50": [10, 12, 13, 14, 15, 16],
            "P75": [10, 13, 15, 16, 17, 18],
            "P95": [10, 15, 17, 19, 20, 22],
        },
        index=list(steps),
    )
    fig = charts.fan(frame)
    # two bands (4 traces) + the median line.
    assert len(fig.data) == 5
    assert fig.data[-1].name == "Median"
    assert fig.data[-1].line.color == charts.ACCENT


def test_underwater_fills_below_zero():
    drawdown = pd.Series([-0.1, -0.05, -0.2], index=pd.date_range("2025-01-01", periods=3))
    fig = charts.underwater(drawdown)
    assert fig.data[0].fill == "tozeroy"
    assert fig.data[0].line.color == charts.LOSS


def test_histogram_marks_the_budget_band():
    fig = charts.histogram([1, 2, 2, 3, 5], markers=((2.5, "cap"),))
    assert fig.data[0].nbinsx == 40
    assert len(fig.layout.shapes) >= 1  # the reference line


def test_vertical_bar_draws_a_reference_line():
    fig = charts.vertical_bar(["A", "B"], [2, 4], reference=3, reference_label="avg")
    assert len(fig.layout.shapes) == 1
    assert fig.data[0].text == ("2", "4")


def test_scatter_accepts_categorical_y_for_a_timeline():
    fig = charts.scatter(
        pd.to_datetime(["2026-01-01", "2026-02-01"]),
        ["AAA", "BBB"],
        labels=["AAA", "BBB"],
        sizes=[1.0, 2.0],
    )
    assert list(fig.data[0].y) == ["AAA", "BBB"]
    assert fig.data[0].marker.sizemode == "area"
