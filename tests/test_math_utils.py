"""
Stress calculation — the Midas Civil sign convention that both the plotting
and reporting paths depend on.
"""

import numpy as np
import pytest

from shell_kit.math_utils import (
    calculate_stress_vectorized, safe_filename, format_value,
)

T = 0.4  # m


def test_positive_moment_compresses_the_top_fibre():
    """Midas convention: M(+) -> top compression (-), bottom tension (+)."""
    top, bot = calculate_stress_vectorized(np.array([0.0]), np.array([100.0]), T)
    assert top[0] < 0
    assert bot[0] > 0
    assert top[0] == pytest.approx(-bot[0])


def test_pure_moment_hand_calculation():
    """I = 1*0.4^3/12 = 0.00533333 m4 ; y = 0.2 m ; sigma = M*y/I = 3750 kPa."""
    top, bot = calculate_stress_vectorized(np.array([0.0]), np.array([100.0]), T)
    assert bot[0] == pytest.approx(3750.0)


def test_pure_tension_is_uniform_across_the_section():
    top, bot = calculate_stress_vectorized(np.array([100.0]), np.array([0.0]), T)
    assert top[0] == pytest.approx(250.0)   # N/A = 100/0.4
    assert top[0] == pytest.approx(bot[0])


def test_axial_and_moment_superpose():
    top, bot = calculate_stress_vectorized(np.array([100.0]), np.array([100.0]), T)
    assert top[0] == pytest.approx(250.0 - 3750.0)
    assert bot[0] == pytest.approx(250.0 + 3750.0)


def test_thinner_plate_gives_higher_bending_stress():
    _, thick = calculate_stress_vectorized(np.array([0.0]), np.array([100.0]), 0.8)
    _, thin = calculate_stress_vectorized(np.array([0.0]), np.array([100.0]), 0.2)
    assert thin[0] > thick[0]


def test_stress_is_vectorised_elementwise():
    top, bot = calculate_stress_vectorized(
        np.array([0.0, 0.0]), np.array([100.0, 200.0]), T,
    )
    assert bot[1] == pytest.approx(2 * bot[0])


# =============================================================================
# Filename / display helpers
# =============================================================================

@pytest.mark.parametrize('raw,expected', [
    ('Mxx (kN·m/m)', 'Mxx_kNm_per_m'),
    ('Fxx (kN/m)', 'Fxx_kN_per_m'),
    ('Sig-xx_Top (kPa)', 'Sig-xx_Top_kPa'),
])
def test_safe_filename_strips_path_hostile_characters(raw, expected):
    out = safe_filename(raw)
    assert out == expected
    assert not any(c in out for c in '()/·[],')


def test_format_value_marks_nan_as_not_available():
    assert format_value(float('nan')) == 'N/A'


def test_format_value_always_shows_a_sign():
    assert format_value(1.5) == '+1.50'
    assert format_value(-1.5) == '-1.50'
