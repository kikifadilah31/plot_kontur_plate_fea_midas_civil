"""
Reinforcement engine — SNI 2847:2019.

Invariant under test throughout: a section that does not satisfy the code
produces np.nan (SECTION INADEQUATE). Failures are never rounded, clamped or
zeroed back into safe-looking numbers.
"""

import numpy as np
import pytest

from shell_kit.rebar import (
    AVAILABLE_DIAMETERS, PHI_FLEXURE, PHI_SHEAR, STRIP_WIDTH_MM,
    calc_beta1, calc_as_min, calc_as_min_per_face, calc_rho_min, calc_rho_max,
    calc_effective_depth, calc_as_required, apply_as_min,
    calc_spacing_from_diameter, calc_diameter_from_spacing,
    calc_min_spacing, check_spacing_limits,
    calc_Vc, calc_Vs_max, calc_Av_min_per_s,
    calc_shear_Av_per_s, calc_shear_diameter,
    solve_rebar_iterative, format_depth_range,
    select_config_from_As,
)

FC = 30.0
FY = 420.0


# =============================================================================
# beta1 (SNI 22.2.2.4.3)
# =============================================================================

@pytest.mark.parametrize('fc,expected', [
    (20.0, 0.85),
    (28.0, 0.85),          # boundary, low side
    (30.0, 0.85 - 0.05 * 2 / 7),
    (55.0, 0.65),          # boundary, high side
    (70.0, 0.65),
])
def test_beta1_across_all_three_ranges(fc, expected):
    assert calc_beta1(fc) == pytest.approx(expected)


def test_beta1_is_monotonically_decreasing():
    values = [calc_beta1(fc) for fc in range(20, 80, 5)]
    assert all(a >= b for a, b in zip(values, values[1:]))


# =============================================================================
# As minimum (SNI 24.4.3.2)
# =============================================================================

@pytest.mark.parametrize('fy,h,expected', [
    (400.0, 400.0, 0.0020 * 1000 * 400),              # fy < 420
    (420.0, 400.0, 0.0018 * 1000 * 400),              # fy = 420
    (500.0, 400.0, 0.0018 * 420 / 500 * 1000 * 400),  # fy > 420
])
def test_as_min_matches_code_ratios(fy, h, expected):
    assert calc_as_min(fy, h) == pytest.approx(expected)


def test_as_min_never_below_the_0_0014_floor():
    # A very high fy would otherwise drive the ratio below 0.0014
    assert calc_as_min(1000.0, 400.0) == pytest.approx(0.0014 * 1000 * 400)


def test_as_min_scales_with_gross_thickness_not_effective_depth():
    assert calc_as_min(FY, 800.0) == pytest.approx(2 * calc_as_min(FY, 400.0))


def test_apply_as_min_raises_low_values():
    """One layer carries its SHARE of the section minimum, not the whole."""
    As = np.array([0.0, 100.0, 5000.0])
    out = apply_as_min(As, FY, 400.0)
    per_face = calc_as_min_per_face(FY, 400.0)
    assert out[0] == pytest.approx(per_face)
    assert out[1] == pytest.approx(per_face)
    assert out[2] == pytest.approx(5000.0)   # already above the minimum
    assert per_face == pytest.approx(calc_as_min(FY, 400.0) / 2)


def test_apply_as_min_does_not_rescue_a_failed_section():
    """Minimum steel is not a cure for an inadequate section."""
    out = apply_as_min(np.array([np.nan, 100.0]), FY, 400.0)
    assert np.isnan(out[0])


# =============================================================================
# As required
# =============================================================================

def test_as_required_matches_hand_calculation():
    """
    b=1000, f'c=30, fy=420, d=350, phi=0.9, Mu=100 kN.m/m
      denom    = 0.9 * 25.5 * 1000 * 350^2 = 2.811375e9
      sqrt_arg = 1 - 2*100e6/denom         = 0.9288704
      As       = (25.5*1000*350/420)*(1-sqrt(sqrt_arg)) = 769.7 mm2/m
    """
    As = calc_as_required(np.array([100.0]), FC, FY, 350.0)
    assert As[0] == pytest.approx(769.7, rel=1e-3)


def test_zero_moment_needs_no_steel():
    As = calc_as_required(np.array([0.0, 0.0]), FC, FY, 350.0)
    assert np.all(As == 0.0)


def test_moment_beyond_flexural_capacity_is_nan():
    # denom/2 = 1405.7 kN.m/m is the absolute ceiling; go well past it
    As = calc_as_required(np.array([2000.0]), FC, FY, 350.0)
    assert np.isnan(As[0])


def test_non_ductile_section_is_flagged_even_though_the_maths_works():
    """
    Mu = 900 kN.m/m still yields a real As (~8504 mm2/m), but that exceeds
    rho_max * b * d, so phi = 0.90 would be invalid. The correct answer for a
    slab is a thicker section, not a quietly reduced phi.
    """
    Mu = np.array([900.0])
    assert np.isnan(calc_as_required(Mu, FC, FY, 350.0)[0])

    unchecked = calc_as_required(Mu, FC, FY, 350.0, check_ductility=False)
    assert unchecked[0] == pytest.approx(8504.0, rel=1e-3)
    assert unchecked[0] > calc_rho_max(FC, FY) * STRIP_WIDTH_MM * 350.0


def test_rho_max_is_a_sane_ratio():
    rho = calc_rho_max(FC, FY)
    assert 0.005 < rho < 0.05


def test_as_required_accepts_a_per_node_depth_array():
    """Mode B needs this: depth varies with the bar selected at each node."""
    Mu = np.array([100.0, 100.0])
    d = np.array([350.0, 300.0])
    As = calc_as_required(Mu, FC, FY, d)
    assert As[1] > As[0]     # shallower section needs more steel


def test_scalar_and_array_depth_agree():
    Mu = np.array([120.0, 80.0])
    from_scalar = calc_as_required(Mu, FC, FY, 350.0)
    from_array = calc_as_required(Mu, FC, FY, np.full(2, 350.0))
    assert np.allclose(from_scalar, from_array)


def test_zero_depth_is_inadequate_not_a_crash():
    As = calc_as_required(np.array([100.0]), FC, FY, np.array([0.0]))
    assert np.isnan(As[0])


# =============================================================================
# Effective depth
# =============================================================================

def test_y_direction_sits_below_x_direction():
    dx = calc_effective_depth(400.0, 40.0, 16.0, 'x', 'bottom')
    dy = calc_effective_depth(400.0, 40.0, 16.0, 'y', 'bottom')
    assert dx == pytest.approx(400 - 40 - 8)
    assert dy == pytest.approx(400 - 40 - 16 - 8)
    assert dy < dx


def test_effective_depth_is_vectorised():
    d = calc_effective_depth(400.0, 40.0, np.array([16.0, 32.0]), 'x', 'bottom')
    assert d.tolist() == [352.0, 344.0]


# =============================================================================
# Spacing limits (B3)
# =============================================================================

@pytest.mark.parametrize('D,expected', [
    (13.0, 13 + 25),    # clear distance floor of 25 mm governs
    (16.0, 16 + 25),
    (32.0, 32 + 32),    # bar diameter governs
])
def test_min_spacing_is_clear_distance_plus_one_diameter(D, expected):
    assert calc_min_spacing(D) == pytest.approx(expected)


def test_spacing_above_maximum_is_clamped_down():
    """Clamping down is conservative — it places more steel than required."""
    out = check_spacing_limits(np.array([600.0]), 400.0, 16.0)
    assert out[0] == pytest.approx(450.0)   # min(2h, 450)


def test_spacing_max_follows_two_h_for_thin_slabs():
    out = check_spacing_limits(np.array([600.0]), 150.0, 16.0)
    assert out[0] == pytest.approx(300.0)   # 2 * 150


def test_spacing_below_minimum_is_inadequate_not_clamped_up():
    """
    The old code clamped 30 mm up to 25/41 mm and the plot looked fine, hiding
    a section that cannot physically accept the bars.
    """
    out = check_spacing_limits(np.array([30.0]), 400.0, 16.0)
    assert np.isnan(out[0])


def test_spacing_in_range_passes_through_untouched():
    out = check_spacing_limits(np.array([150.0]), 400.0, 16.0)
    assert out[0] == pytest.approx(150.0)


def test_spacing_preserves_infinity_and_nan():
    out = check_spacing_limits(np.array([np.inf, np.nan]), 400.0, 16.0)
    assert np.isinf(out[0])     # no rebar needed
    assert np.isnan(out[1])     # already inadequate


# =============================================================================
# Bar selection
# =============================================================================

def test_spacing_from_diameter_is_the_inverse_of_area_per_metre():
    As = np.array([1000.0])
    s = calc_spacing_from_diameter(As, 16.0)
    assert s[0] == pytest.approx(0.25 * np.pi * 256 * 1000.0 / 1000.0)


def test_no_steel_needed_means_infinite_spacing():
    s = calc_spacing_from_diameter(np.array([0.0]), 16.0)
    assert np.isinf(s[0])


def test_diameter_rounds_up_to_the_next_stock_size():
    # As chosen so D_req lands between 16 and 19
    As = np.array([1400.0])
    D = calc_diameter_from_spacing(As, 150.0)
    assert D[0] == 19.0


def test_diameter_beyond_the_largest_bar_is_inadequate():
    D = calc_diameter_from_spacing(np.array([80000.0]), 150.0)
    assert np.isnan(D[0])


def test_exact_diameter_match_does_not_round_up():
    A_bar = 0.25 * np.pi * 16.0 ** 2
    As = np.array([A_bar * 1000.0 / 150.0])
    assert calc_diameter_from_spacing(As, 150.0)[0] == 16.0


def test_config_selection_picks_smallest_adequate_option():
    codes = ['16', '22', '2D25']
    As = np.array([0.0, 500.0, 20000.0])
    idx, sorted_codes, areas = select_config_from_As(As, codes, 150.0)
    assert sorted_codes == ['16', '22', '2D25']
    assert idx[0] == 0.0        # no steel needed
    assert idx[1] == 1.0        # '16' suffices (500*150/1000 = 75 mm2)
    assert np.isnan(idx[2])     # beyond 2D25


# =============================================================================
# Shear (B4)
# =============================================================================

def test_Vc_matches_sni_22_5_5_1():
    assert calc_Vc(FC, 1000.0, 350.0) == pytest.approx(
        0.17 * np.sqrt(FC) * 1000.0 * 350.0
    )


def test_Vs_max_matches_sni_22_5_1_2():
    assert calc_Vs_max(FC, 1000.0, 350.0) == pytest.approx(
        0.66 * np.sqrt(FC) * 1000.0 * 350.0
    )


def test_Av_min_matches_sni_9_6_3_4():
    expected = max(0.062 * np.sqrt(FC) * 1000.0 / FY, 0.35 * 1000.0 / FY)
    assert calc_Av_min_per_s(FC, FY) == pytest.approx(expected)


def test_low_shear_needs_no_stirrups():
    # threshold = 0.5 * 0.75 * Vc = 122.2 kN/m
    Av = calc_shear_Av_per_s(np.array([100.0]), FC, FY, 350.0)
    assert Av[0] == 0.0


def test_shear_just_past_the_threshold_gets_minimum_stirrups():
    """Vs computes to zero here, but the code still requires Av,min."""
    Av = calc_shear_Av_per_s(np.array([200.0]), FC, FY, 350.0)
    assert Av[0] == pytest.approx(calc_Av_min_per_s(FC, FY))


def test_high_shear_matches_hand_calculation():
    # Vs = 500000/0.75 - Vc = 340841.8 N ; Av/s = Vs/(fy*dv)
    Av = calc_shear_Av_per_s(np.array([500.0]), FC, FY, 350.0)
    expected = (500000.0 / PHI_SHEAR - calc_Vc(FC, 1000.0, 350.0)) / (FY * 350.0)
    assert Av[0] == pytest.approx(expected)
    assert Av[0] == pytest.approx(2.3186, rel=1e-3)


def test_web_crushing_is_inadequate_not_a_bigger_stirrup():
    """
    Past Vs_max no amount of shear steel helps — the slab must get thicker.
    Reporting a stirrup diameter here would be actively misleading.
    """
    Av = calc_shear_Av_per_s(np.array([1500.0]), FC, FY, 350.0)
    assert np.isnan(Av[0])


def test_sign_of_shear_does_not_matter():
    pos = calc_shear_Av_per_s(np.array([500.0]), FC, FY, 350.0)
    neg = calc_shear_Av_per_s(np.array([-500.0]), FC, FY, 350.0)
    assert pos[0] == pytest.approx(neg[0])


def test_av_min_can_be_disabled():
    Av = calc_shear_Av_per_s(np.array([200.0]), FC, FY, 350.0, apply_av_min=False)
    assert Av[0] == 0.0


def test_shear_diameter_propagates_web_crushing():
    """A crushing zone must not read as '0 = no stirrups needed'."""
    D = calc_shear_diameter(np.array([np.nan, 0.0, 1.0]), 150.0, 150.0)
    assert np.isnan(D[0])
    assert D[1] == 0.0
    assert D[2] > 0.0


def test_shear_diameter_honours_a_custom_list():
    D = calc_shear_diameter(np.array([0.5]), 150.0, 150.0,
                            available_diameters=[10, 13])
    assert D[0] in (10.0, 13.0)


def test_shear_diameter_beyond_custom_list_is_inadequate():
    D = calc_shear_diameter(np.array([5.0]), 150.0, 150.0,
                            available_diameters=[10])
    assert np.isnan(D[0])


# =============================================================================
# Iterative effective depth (B5)
# =============================================================================

def test_iterative_solve_is_conservative_against_the_fixed_d16_assumption():
    """
    The core of the fix. Assuming D16 for depth while actually placing D22
    overstates d and therefore UNDERSTATES As — unconservative exactly where
    the slab is most stressed.
    """
    Mu = np.array([250.0])
    As_iter, d_eff, selection, _ = solve_rebar_iterative(
        Mu, FC, FY, 400.0, 40.0, 'x', 'bottom', 150.0,
    )

    d_fixed = calc_effective_depth(400.0, 40.0, 16.0, 'x', 'bottom')
    As_fixed = calc_as_required(Mu, FC, FY, d_fixed)

    assert selection[0] > 16.0        # a bigger bar really is selected
    assert d_eff[0] < d_fixed         # so the section is shallower
    assert As_iter[0] > As_fixed[0]   # and needs more steel


def test_iterative_solve_converges_within_the_iteration_cap():
    """Monotone upward revision must reach a fixed point, not oscillate."""
    Mu = np.array([50.0, 150.0, 250.0, 400.0])
    As_a, d_a, sel_a, _ = solve_rebar_iterative(
        Mu, FC, FY, 400.0, 40.0, 'x', 'bottom', 150.0, max_iter=5,
    )
    As_b, d_b, sel_b, _ = solve_rebar_iterative(
        Mu, FC, FY, 400.0, 40.0, 'x', 'bottom', 150.0, max_iter=20,
    )
    assert np.allclose(d_a, d_b)
    assert np.allclose(np.nan_to_num(sel_a), np.nan_to_num(sel_b))


def test_depth_varies_across_nodes_when_bar_size_does():
    Mu = np.array([20.0, 400.0])
    _, d_eff, selection, _ = solve_rebar_iterative(
        Mu, FC, FY, 400.0, 40.0, 'x', 'bottom', 150.0,
    )
    assert selection[1] > selection[0]
    assert d_eff[1] < d_eff[0]


def test_iterative_solve_applies_as_min_by_default():
    Mu = np.array([1.0])
    As, _, _, _ = solve_rebar_iterative(
        Mu, FC, FY, 400.0, 40.0, 'x', 'bottom', 150.0,
    )
    assert As[0] == pytest.approx(calc_as_min_per_face(FY, 400.0))


def test_iterative_solve_honours_the_surface_zone_cap():
    Mu = np.array([1.0])
    As, _, _, _ = solve_rebar_iterative(
        Mu, FC, FY, 3000.0, 40.0, 'x', 'bottom', 150.0, surface_zone=300.0,
    )
    assert As[0] == pytest.approx(calc_as_min_per_face(FY, 3000.0,
                                                       surface_zone=300.0))

    As_off, _, _, _ = solve_rebar_iterative(
        Mu, FC, FY, 400.0, 40.0, 'x', 'bottom', 150.0, apply_min=False,
    )
    assert As_off[0] < calc_as_min(FY, 400.0)


def test_iterative_solve_with_config_codes_returns_indices():
    Mu = np.array([100.0, 250.0])
    As, d_eff, selection, sorted_codes = solve_rebar_iterative(
        Mu, FC, FY, 400.0, 40.0, 'x', 'bottom', 150.0,
        config_codes=['16', '22', '2D25'],
    )
    assert sorted_codes == ['16', '22', '2D25']
    assert selection[0] >= 1          # 1-based config index
    assert selection[1] >= selection[0]


# =============================================================================
# Depth label formatting
# =============================================================================

def test_depth_label_collapses_when_uniform():
    assert format_depth_range(np.full(4, 352.0)) == '352 mm'


def test_depth_label_shows_a_range_when_it_varies():
    assert format_depth_range(np.array([344.0, 352.0])) == '344-352 mm'


def test_depth_label_accepts_a_scalar():
    assert format_depth_range(352.0) == '352 mm'


# =============================================================================
# As,min distribution — the clause states a section total, not a per-face amount
# =============================================================================

def test_section_total_is_split_between_the_two_faces():
    """
    Applying the full clause amount to every layer placed twice the required
    steel in each direction: 4 layers x rho.Ag = 0.0072.Ag against the
    0.0036.Ag the code asks for across X and Y.
    """
    total = calc_as_min(FY, 400.0)
    per_face = calc_as_min_per_face(FY, 400.0)
    assert per_face == pytest.approx(total / 2)
    assert 2 * per_face == pytest.approx(total)


def test_section_total_still_matches_the_clause():
    """calc_as_min stays the quantity the code states — rho x b x h."""
    assert calc_as_min(FY, 400.0) == pytest.approx(calc_rho_min(FY) * 1000 * 400)


@pytest.mark.parametrize('h,cap,expected_t', [
    (200.0, 300.0, 100.0),    # h/2 governs, cap never bites
    (600.0, 300.0, 300.0),    # exactly at the boundary
    (3000.0, 300.0, 300.0),   # cap governs — a raft is not a thick slab
    (3000.0, None, 1500.0),   # without the cap it scales with the whole depth
])
def test_surface_zone_caps_the_thickness_per_face(h, cap, expected_t):
    got = calc_as_min_per_face(FY, h, surface_zone=cap)
    assert got == pytest.approx(calc_rho_min(FY) * 1000 * expected_t)


def test_surface_zone_never_increases_the_requirement():
    """A cap can only reduce; it must not raise a thin slab's minimum."""
    for h in (150.0, 300.0, 600.0, 1200.0):
        assert (calc_as_min_per_face(FY, h, surface_zone=300.0)
                <= calc_as_min_per_face(FY, h))


def test_thick_raft_minimum_becomes_buildable():
    """
    3 m pilecap: the old basis demanded 5400 mm2/m per layer (about D25-90 in
    all four layers as pure minimum), which is not what the clause intends.
    """
    old_basis = calc_as_min(FY, 3000.0)
    new_basis = calc_as_min_per_face(FY, 3000.0, surface_zone=300.0)
    assert old_basis == pytest.approx(5400.0)
    assert new_basis == pytest.approx(540.0)


def test_rho_min_follows_the_code_table():
    assert calc_rho_min(400.0) == pytest.approx(0.0020)
    assert calc_rho_min(420.0) == pytest.approx(0.0018)
    assert calc_rho_min(1000.0) == pytest.approx(0.0014)
