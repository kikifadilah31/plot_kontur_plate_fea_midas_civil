"""
Rebar calculation engine — flexural & shear reinforcement for RC slabs.
All functions are vectorized (NumPy) for direct use with contour arrays.

Reference: ACI 318 / SNI 2847 simplified rectangular stress block.
"""

import numpy as np

# =============================================================================
# Constants
# =============================================================================
AVAILABLE_DIAMETERS = np.array([13, 16, 19, 22, 25, 32], dtype=float)  # mm
DEFAULT_FC = 30      # MPa
DEFAULT_FY = 420     # MPa
DEFAULT_COVER = 40   # mm
PHI_FLEXURE = 0.90
STRIP_WIDTH_MM = 1000  # mm (per 1m width)

# --- Shear-specific constants ---
PHI_SHEAR = 0.75
BETA_SHEAR = 2.0   # β for normal-weight concrete (always 2.0)
SHEAR_DIAMETERS = np.array([10, 13, 16, 19, 22, 25], dtype=float)  # mm (stirrup sizes)


def calc_effective_depth(h_mm, cover, D, direction, layer):
    """
    Calculate effective depth (d) based on bar placement order.

    Convention: X-direction bars are placed in the OUTER layer.

    Parameters
    ----------
    h_mm : float
        Slab thickness in mm.
    cover : float
        Clear concrete cover in mm.
    D : float
        Bar diameter in mm.
    direction : str
        'x' (outer layer) or 'y' (inner layer).
    layer : str
        'top' or 'bottom' (both have the same d formula, just from different faces).

    Returns
    -------
    float : effective depth d (mm).
    """
    if direction == 'x':
        return h_mm - cover - 0.5 * D
    else:  # 'y' → inner layer
        return h_mm - cover - D - 0.5 * D


def calc_as_required(Mu_knm, fc, fy, d, phi=PHI_FLEXURE):
    """
    Vectorized calculation of required steel area As.

    Uses ACI rectangular stress block formula.
    Input moment in kN·m/m (auto-converted to N·mm/m internally).

    Parameters
    ----------
    Mu_knm : array-like
        Absolute design moment in kN·m/m (always positive).
    fc : float
        Concrete compressive strength in MPa.
    fy : float
        Steel yield strength in MPa.
    d : float
        Effective depth in mm.
    phi : float
        Strength reduction factor (default: 0.90).

    Returns
    -------
    numpy array : As_required in mm²/m.
        Returns 0.0 where Mu ≈ 0.
        Returns np.nan where section is inadequate (sqrt of negative).
    """
    Mu_knm = np.asarray(Mu_knm, dtype=float)
    As = np.zeros_like(Mu_knm)

    # Convert kN·m/m → N·mm/m
    Mu = Mu_knm * 1e6

    # Mask: only compute where moment is significant
    active = np.abs(Mu) > 1e-3  # threshold: > 0.001 N·mm/m

    if not np.any(active):
        return As

    b = STRIP_WIDTH_MM
    fc_term = 0.85 * fc
    denominator = phi * fc_term * b * d ** 2

    # Guard against zero denominator
    if denominator == 0:
        As[active] = np.nan
        return As

    # Value inside the square root
    sqrt_arg = 1.0 - (2.0 * Mu[active]) / denominator

    # Section Inadequate check
    inadequate = sqrt_arg < 0
    valid = ~inadequate

    # Compute As for valid nodes
    if np.any(valid):
        As_valid = (fc_term * b * d / fy) * (1.0 - np.sqrt(sqrt_arg[valid]))
        # Create temporary array for active indices
        result = np.full(np.sum(active), np.nan)
        result[valid] = As_valid
        As[active] = result

    return As


def calc_spacing_from_diameter(As, D):
    """
    Calculate bar spacing given As and bar diameter.

    Parameters
    ----------
    As : array-like
        Required steel area in mm²/m.
    D : float
        Bar diameter in mm.

    Returns
    -------
    numpy array : spacing in mm.
        Returns np.inf where As ≈ 0 (no rebar needed).
        Returns np.nan where As is nan (section inadequate).
    """
    As = np.asarray(As, dtype=float)
    A_bar = 0.25 * np.pi * D ** 2

    spacing = np.full_like(As, np.inf)

    valid = (As > 1e-6) & ~np.isnan(As)
    spacing[valid] = A_bar * 1000.0 / As[valid]

    # Propagate NaN from inadequate sections
    spacing[np.isnan(As)] = np.nan

    return spacing


def calc_diameter_from_spacing(As, s):
    """
    Calculate required bar diameter given As and spacing.
    Rounds UP to the nearest available diameter.

    Parameters
    ----------
    As : array-like
        Required steel area in mm²/m.
    s : float
        Bar spacing in mm.

    Returns
    -------
    numpy array : selected diameter in mm (from AVAILABLE_DIAMETERS).
        Returns 0.0 where As ≈ 0 (no rebar needed).
        Returns np.nan where required diameter exceeds max available (32mm).
    """
    As = np.asarray(As, dtype=float)
    D_selected = np.zeros_like(As)

    valid = (As > 1e-6) & ~np.isnan(As)

    if not np.any(valid):
        D_selected[np.isnan(As)] = np.nan
        return D_selected

    A_bar_req = As[valid] * s / 1000.0
    D_req = np.sqrt(4.0 * A_bar_req / np.pi)

    # Round UP to nearest available diameter
    result = np.full_like(D_req, np.nan)
    for i, d_req in enumerate(D_req):
        candidates = AVAILABLE_DIAMETERS[AVAILABLE_DIAMETERS >= d_req]
        if len(candidates) > 0:
            result[i] = candidates[0]  # smallest diameter >= D_req
        # else: stays np.nan (exceeds max 32mm)

    D_selected[valid] = result
    D_selected[np.isnan(As)] = np.nan

    return D_selected


def check_spacing_limits(s, h_mm, D):
    """
    Clamp spacing to code limits.

    Parameters
    ----------
    s : array-like
        Calculated spacing in mm.
    h_mm : float
        Slab thickness in mm.
    D : float
        Bar diameter in mm.

    Returns
    -------
    numpy array : clamped spacing in mm.
    """
    s = np.asarray(s, dtype=float)
    s_max = min(2.0 * h_mm, 450.0)
    s_min = max(25.0, D)

    clamped = np.clip(s, s_min, s_max)

    # Preserve NaN and Inf
    clamped[np.isnan(s)] = np.nan
    clamped[np.isinf(s)] = np.inf

    return clamped


# =============================================================================
# Shear Reinforcement Functions (ACI 318 / SNI 2847)
# =============================================================================

def calc_Vc(fc, bw, dv):
    """
    Concrete shear capacity.

    Vc = 0.083 × β × √f'c × bw × dv   (β = 2.0 hardcoded)

    Parameters
    ----------
    fc : float
        Concrete compressive strength in MPa.
    bw : float
        Web width in mm (typically 1000 mm for slab strip).
    dv : float
        Effective shear depth in mm.

    Returns
    -------
    float : Vc in Newtons.
    """
    return 0.083 * BETA_SHEAR * np.sqrt(fc) * bw * dv


def calc_shear_Av_per_s(Vu_kn_per_m, fc, fy, dv):
    """
    Vectorized calculation of required shear reinforcement Av/s.

    Steps:
      1. Convert Vu from kN/m → N  (×1000, since bw = 1000 mm = 1m)
      2. Compute Vc = 0.083 × β × √f'c × bw × dv
      3. Check: |Vu| > 0.5 × φ × Vc  → needs shear rebar
      4. Vs = |Vu|/φ − Vc   (clamp to 0 if negative)
      5. Av/s = Vs / (fy × dv)

    Parameters
    ----------
    Vu_kn_per_m : array-like
        Factored shear force in kN/m (from FEM: Vxx or Vyy).
    fc : float
        Concrete compressive strength in MPa.
    fy : float
        Steel yield strength in MPa.
    dv : float
        Effective shear depth in mm.

    Returns
    -------
    numpy array : Av/s in mm²/mm.
        Returns 0.0 where no shear reinforcement is needed.
    """
    Vu_kn = np.asarray(Vu_kn_per_m, dtype=float)
    Vu_abs_N = np.abs(Vu_kn) * 1000.0  # kN/m → N (per 1m strip)

    bw = STRIP_WIDTH_MM  # 1000 mm
    Vc = calc_Vc(fc, bw, dv)

    # Threshold: shear rebar needed only if Vu > 0.5 × φ × Vc
    threshold = 0.5 * PHI_SHEAR * Vc
    needs_rebar = Vu_abs_N > threshold

    Av_per_s = np.zeros_like(Vu_kn)

    if np.any(needs_rebar):
        Vs = (Vu_abs_N[needs_rebar] / PHI_SHEAR) - Vc
        Vs = np.maximum(Vs, 0.0)  # clamp negative to 0
        Av_per_s[needs_rebar] = Vs / (fy * dv)

    return Av_per_s


def calc_shear_diameter(Av_per_s, s_long, s_trans):
    """
    Calculate required stirrup diameter given Av/s and both spacings.

    For a 1m-wide slab strip with stirrup grid:
      Ab_required = (Av/s) × s_long × s_trans / 1000
      D_required  = √(4 × Ab_required / π)
      → Round UP to nearest standard stirrup diameter from SHEAR_DIAMETERS.

    Parameters
    ----------
    Av_per_s : array-like
        Required shear reinforcement in mm²/mm.
    s_long : float
        Longitudinal spacing in mm (along shear direction).
    s_trans : float
        Transversal spacing in mm (across 1m strip width).

    Returns
    -------
    numpy array : selected diameter in mm (from SHEAR_DIAMETERS).
        Returns 0.0 where Av/s ≈ 0 (no shear rebar needed).
        Returns np.nan where required diameter exceeds max available (25mm).
    """
    Av_per_s = np.asarray(Av_per_s, dtype=float)
    D_selected = np.zeros_like(Av_per_s)

    active = Av_per_s > 1e-9

    if not np.any(active):
        return D_selected

    # Area per single stirrup leg
    Ab_req = Av_per_s[active] * s_long * s_trans / 1000.0
    D_req = np.sqrt(4.0 * Ab_req / np.pi)

    # Round UP to nearest available stirrup diameter
    result = np.full_like(D_req, np.nan)
    for i, d_req in enumerate(D_req):
        candidates = SHEAR_DIAMETERS[SHEAR_DIAMETERS >= d_req]
        if len(candidates) > 0:
            result[i] = candidates[0]
        # else: stays np.nan (exceeds max D25 stirrup)

    D_selected[active] = result
    return D_selected
