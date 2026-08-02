"""
Which layers `shell-kit rebar` produces, and how much minimum steel each gets.

Two decisions are locked here:

1. A face with no moment anywhere still needs shrinkage and temperature steel.
   Dropping its layer left the report silent about reinforcement the code
   requires.

2. One layer carries its SHARE of the code minimum. SNI 24.4.3.2 states a
   total for the direction through the full thickness; applying that total to
   every layer placed twice the required steel in each direction.
"""

import numpy as np
import pytest

from shell_kit.cli_rebar import _build_rebar_tasks
from shell_kit.rebar import calc_as_min, calc_as_min_per_face

FC, FY = 30.0, 420.0
H, COVER = 400.0, 40.0
N = 6


def _geom():
    """Dummy geometry — the builder only forwards it into task tuples."""
    x = np.linspace(0.0, 5.0, N)
    y = np.zeros(N)
    tris = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int32)
    return x, y, tris


def _build(moment, layer='top', mode='diameter', apply_min=True,
           surface_zone=None, direction='x'):
    x, y, tris = _geom()
    return _build_rebar_tasks(
        x, y, tris, None, None,
        np.asarray(moment, dtype=float), H, COVER, FC, FY,
        None, 150.0, mode,
        direction, layer, 'Mxx_Top_X',
        'LC1', 'out', 'average-nodal', False, 'light',
        apply_min=apply_min, surface_zone=surface_zone,
    )


# =============================================================================
# A face with no moment still gets its layer
# =============================================================================

def test_face_without_moment_still_produces_a_layer():
    """Sagging everywhere: the top face has no flexural demand, but the
    section still needs shrinkage and temperature steel there."""
    sagging_only = np.full(N, 50.0)          # Mxx > 0 everywhere
    tasks, result = _build(sagging_only, layer='top')

    assert tasks, 'lapis atas hilang padahal susut & suhu tetap menuntutnya'
    assert np.all(result['As'] == pytest.approx(calc_as_min_per_face(FY, H)))


def test_that_layer_carries_only_the_minimum():
    tasks, result = _build(np.full(N, 50.0), layer='top')
    per_face = calc_as_min_per_face(FY, H)
    assert result['As'].max() == pytest.approx(per_face)
    assert result['As'].min() == pytest.approx(per_face)


def test_layer_is_dropped_when_the_minimum_is_switched_off():
    """With --no-as-min there is genuinely nothing to draw for that face."""
    tasks, result = _build(np.full(N, 50.0), layer='top', apply_min=False)
    assert tasks == []


def test_loaded_face_is_unaffected():
    tasks, result = _build(np.full(N, 50.0), layer='bottom')
    assert tasks
    assert result['As'].max() > calc_as_min_per_face(FY, H)


# =============================================================================
# How much minimum each layer gets
# =============================================================================

def test_layer_minimum_is_half_the_section_total():
    _, result = _build(np.zeros(N), layer='top')
    assert result['As'][0] == pytest.approx(calc_as_min(FY, H) / 2)


def test_four_layers_no_longer_double_the_section_requirement():
    """
    Old basis: 4 layers x rho.Ag = 0.0072.Ag placed, against 0.0036.Ag
    required across X and Y. The split brings the two into line.
    """
    _, res = _build(np.zeros(N), layer='top')
    per_layer = res['As'][0]
    assert 4 * per_layer == pytest.approx(2 * calc_as_min(FY, H))


def test_surface_zone_reaches_the_layer_builder():
    """A 3 m raft is where the uncapped basis becomes unbuildable."""
    _, capped = _build(np.zeros(N), layer='top', surface_zone=300.0)
    _, plain = _build(np.zeros(N), layer='top')

    assert capped['As'][0] == pytest.approx(calc_as_min_per_face(
        FY, H, surface_zone=300.0))
    assert capped['As'][0] <= plain['As'][0]


@pytest.mark.parametrize('mode,diameter', [('diameter', None), ('spacing', 16.0)])
def test_both_modes_use_the_same_minimum(mode, diameter):
    x, y, tris = _geom()
    _, result = _build_rebar_tasks(
        x, y, tris, None, None,
        np.zeros(N), H, COVER, FC, FY,
        diameter, 150.0, mode,
        'x', 'top', 'Mxx_Top_X',
        'LC1', 'out', 'average-nodal', False, 'light',
        apply_min=True,
    )
    assert result['As'][0] == pytest.approx(calc_as_min_per_face(FY, H))
