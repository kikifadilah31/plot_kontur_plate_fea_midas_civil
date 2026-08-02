"""
Discrete rebar colormap construction (A5).

Selecting all 24 rebar configurations needs 26 colour bins, which overran the
25-entry hand-picked palette. BoundaryNorm then refused to build and EVERY
config plot failed — visible only as a "plots failed" count.
"""

import matplotlib.colors as mcolors
import pytest

from shell_kit.plotting_rebar import (
    build_categorical_colors,
    CATEGORICAL_COLORS,
    INADEQUATE_COLOR,
)
from shell_kit.rebar import REBAR_CONFIG_TABLE


@pytest.mark.parametrize('n_bins', range(1, 41))
def test_returns_exactly_n_colors(n_bins):
    assert len(build_categorical_colors(n_bins)) == n_bins


@pytest.mark.parametrize('n_bins', range(2, 41))
def test_boundary_norm_accepts_the_palette(n_bins):
    """BoundaryNorm requires ncolors >= number of bins."""
    cmap = mcolors.ListedColormap(build_categorical_colors(n_bins))
    boundaries = list(range(n_bins + 1))
    norm = mcolors.BoundaryNorm(boundaries, cmap.N)
    assert norm.Ncmap == n_bins


def test_full_rebar_table_builds():
    """The exact scenario that failed: --rebar-select with all 24 configs."""
    n_configs = len(REBAR_CONFIG_TABLE)
    boundaries = (
        [-0.5, 0.5]
        + [i + 0.5 for i in range(1, n_configs + 1)]
        + [n_configs + 1.5]
    )
    n_bins = len(boundaries) - 1

    assert n_bins > len(CATEGORICAL_COLORS)   # the overflow really happens

    cmap = mcolors.ListedColormap(build_categorical_colors(n_bins))
    mcolors.BoundaryNorm(boundaries, cmap.N)  # must not raise


def test_index_zero_stays_white_and_last_is_inadequate():
    for n_bins in (5, 25, 26, 30):
        colors = build_categorical_colors(n_bins)
        assert colors[0] == '#FFFFFF'
        assert colors[-1] == INADEQUATE_COLOR


def test_hand_picked_palette_is_preserved_below_overflow():
    colors = build_categorical_colors(10)
    assert colors[:9] == CATEGORICAL_COLORS[:9]


def test_all_colors_are_parseable():
    for c in build_categorical_colors(35):
        mcolors.to_rgba(c)


def test_rejects_nonsense_bin_count():
    with pytest.raises(ValueError):
        build_categorical_colors(0)
