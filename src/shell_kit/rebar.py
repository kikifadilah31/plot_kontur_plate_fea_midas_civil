"""
Rebar calculation engine — flexural & shear reinforcement for RC slabs.
All functions are vectorized (NumPy) for direct use with contour arrays.

Reference: SNI 2847:2019 (aligned with ACI 318-19), rectangular stress block.

Convention: np.nan means SECTION INADEQUATE. Every code check that a section
fails propagates nan so the plotting layer marks it grey and counts it in the
"SECTION INADEQUATE" badge — failures are never rounded back into safe-looking
numbers.
"""

import numpy as np

from .config import ES_STEEL, LAMBDA_CONCRETE, EPSILON_CU

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
SHEAR_DIAMETERS = np.array([10, 13, 16, 19, 22, 25], dtype=float)  # mm (stirrup sizes)

# Seed diameter for the iterative effective-depth solve (Mode B)
SEED_DIAMETER = 16.0   # mm
MAX_DEPTH_ITERATIONS = 5

# Slabs are reinforced at both faces, so the code's section-total minimum is
# shared between them rather than applied in full to each layer.
DEFAULT_AS_MIN_FACES = 2


# =============================================================================
# Code Checks (SNI 2847:2019)
# =============================================================================

def calc_beta1(fc):
    """
    Equivalent rectangular stress block depth factor β1 (SNI 22.2.2.4.3).

      f'c <= 28        -> 0.85
      28 < f'c < 55    -> 0.85 - 0.05 (f'c - 28) / 7
      f'c >= 55        -> 0.65

    Parameters
    ----------
    fc : float — concrete compressive strength in MPa.

    Returns
    -------
    float : β1 (dimensionless, 0.65..0.85).
    """
    if fc <= 28.0:
        return 0.85
    if fc >= 55.0:
        return 0.65
    return 0.85 - 0.05 * (fc - 28.0) / 7.0


def calc_rho_min(fy):
    """
    Minimum reinforcement ratio for slabs (SNI 24.4.3.2 / Tabel 7.6.1.1).

      fy <  420 MPa -> 0.0020
      fy >= 420 MPa -> max(0.0018 * 420 / fy, 0.0014)

    The ratio scales with 420/fy because what must be maintained is the
    tensile FORCE the steel can carry, not its area — higher grade steel
    delivers the same force with less section.
    """
    if fy < 420.0:
        return 0.0020
    return max(0.0018 * 420.0 / fy, 0.0014)


def calc_as_min(fy, h_mm, b=STRIP_WIDTH_MM):
    """
    Minimum slab reinforcement for shrinkage and temperature (SNI 24.4.3.2).

    This is the quantity the code states: the TOTAL for one direction through
    the full thickness, referred to the GROSS section (b x h) rather than to
    the effective depth — shrinkage and temperature act on the whole section,
    not just the compression block.

    It is NOT the amount for a single face. A slab reinforced top and bottom
    distributes this total between the two; use calc_as_min_per_face() for
    what one layer must carry.

    Parameters
    ----------
    fy : float — steel yield strength in MPa.
    h_mm : float — slab thickness in mm.
    b : float — strip width in mm (default 1000).

    Returns
    -------
    float : As_min in mm2/m, total for one direction.
    """
    return calc_rho_min(fy) * b * h_mm


def calc_as_min_per_face(fy, h_mm, b=STRIP_WIDTH_MM, n_faces=DEFAULT_AS_MIN_FACES,
                         surface_zone=None):
    """
    Share of the code minimum carried by ONE face of the slab.

    Two corrections to a naive reading of the clause:

    1. The code amount is a section total, so it is divided between the faces
       that are actually reinforced. Applying the full amount to every layer
       placed twice the required steel in each direction.

    2. `surface_zone` caps the thickness each face is computed on. Shrinkage
       and temperature cracking is a SURFACE phenomenon — the core of a thick
       raft restrains itself and does not behave like a thin slab, so scaling
       0.0018 linearly with a 3 m thickness is not what the clause intends.
       ACI 350-06 §7.12.2.1 caps this at 300 mm per face for members thicker
       than 600 mm. SNI 2847:2019 states no such cap, so this is engineering
       judgement borrowed from ACI 350 and normal mat practice — it is opt-in
       and recorded in the report whenever it is used.

    Parameters
    ----------
    fy : float — steel yield strength in MPa.
    h_mm : float — slab thickness in mm.
    b : float — strip width in mm (default 1000).
    n_faces : int — number of reinforced faces sharing the total (default 2).
    surface_zone : float, optional — cap in mm on the thickness per face.

    Returns
    -------
    float : As_min in mm2/m for one layer.
    """
    t_eff = h_mm / max(n_faces, 1)
    if surface_zone:
        t_eff = min(t_eff, surface_zone)
    return calc_rho_min(fy) * b * t_eff


def calc_rho_max(fc, fy):
    """
    Maximum reinforcement ratio keeping the section tension-controlled.

    The engine assumes phi = 0.90, which is only valid for a tension-controlled
    section (SNI Table 21.2.2). Rather than silently reducing phi, sections
    exceeding this ratio are flagged inadequate — the correct answer for a slab
    is a thicker section, not a less ductile one.

      rho_max = 0.85 * beta1 * (f'c / fy) * eps_cu / (eps_cu + eps_ty + 0.003)

    with eps_ty = fy / Es.

    Parameters
    ----------
    fc : float — concrete compressive strength in MPa.
    fy : float — steel yield strength in MPa.

    Returns
    -------
    float : rho_max (dimensionless).
    """
    beta1 = calc_beta1(fc)
    eps_ty = fy / ES_STEEL
    eps_limit = eps_ty + 0.003  # tension-controlled strain limit
    return 0.85 * beta1 * (fc / fy) * EPSILON_CU / (EPSILON_CU + eps_limit)

# =============================================================================
# Rebar Configuration Table (hardcoded from _ref/List_konfigurasi_tulangan.csv)
# Maps: Kode → (Diameter_mm, Jumlah, Luas_mm2)
# =============================================================================
REBAR_CONFIG_TABLE = {
    '13':   (13, 1, 133),
    '16':   (16, 1, 201),
    '19':   (19, 1, 284),
    '22':   (22, 1, 380),
    '25':   (25, 1, 491),
    '32':   (32, 1, 804),
    '2D13': (13, 2, 265),
    '2D16': (16, 2, 402),
    '2D19': (19, 2, 567),
    '2D22': (22, 2, 760),
    '2D25': (25, 2, 982),
    '2D32': (32, 2, 1608),
    '3D13': (13, 3, 398),
    '3D16': (16, 3, 603),
    '3D19': (19, 3, 851),
    '3D22': (22, 3, 1140),
    '3D25': (25, 3, 1473),
    '3D32': (32, 3, 2413),
    '4D13': (13, 4, 531),
    '4D16': (16, 4, 804),
    '4D19': (19, 4, 1134),
    '4D22': (22, 4, 1521),
    '4D25': (25, 4, 1963),
    '4D32': (32, 4, 3217),
}


def get_config_area(code):
    """
    Get the area (mm²) of a rebar configuration by its code.

    Parameters
    ----------
    code : str
        Configuration code, e.g. '16', '2D25', '3D32'.

    Returns
    -------
    float : area in mm².

    Raises
    ------
    ValueError : if code is not found in REBAR_CONFIG_TABLE.
    """
    code = str(code).upper().strip()
    # Accept bare numbers: '16' → '16'
    if code in REBAR_CONFIG_TABLE:
        return float(REBAR_CONFIG_TABLE[code][2])
    raise ValueError(
        f"Kode konfigurasi '{code}' tidak ditemukan. "
        f"Kode tersedia: {', '.join(sorted(REBAR_CONFIG_TABLE.keys()))}"
    )


def get_available_config_codes():
    """Return all available config codes sorted by area ascending."""
    return sorted(REBAR_CONFIG_TABLE.keys(),
                  key=lambda k: REBAR_CONFIG_TABLE[k][2])


def select_config_from_As(As, config_codes, spacing):
    """
    Select the smallest rebar configuration that satisfies As_required.

    For each node, computes:
      A_bar_req = As × spacing / 1000
    Then finds the smallest config (by area) from config_codes
    whose area ≥ A_bar_req.

    Parameters
    ----------
    As : array-like
        Required steel area in mm²/m.
    config_codes : list of str
        User-selected configuration codes, e.g. ['16', '22', '2D25'].
    spacing : float
        Bar spacing in mm.

    Returns
    -------
    numpy array : config index (1-based) for each node.
        0 = no rebar needed (As ≈ 0).
        np.nan = section inadequate (exceeds largest config).
    list of str : sorted config codes (ascending by area).
    list of float : sorted config areas (ascending).
    """
    As = np.asarray(As, dtype=float)

    # Sort configs by area ascending
    sorted_codes = sorted(config_codes,
                          key=lambda c: REBAR_CONFIG_TABLE[c.upper()][2])
    sorted_areas = np.array([REBAR_CONFIG_TABLE[c.upper()][2]
                             for c in sorted_codes], dtype=float)

    result = np.zeros_like(As)
    valid = (As > 1e-6) & ~np.isnan(As)

    if not np.any(valid):
        result[np.isnan(As)] = np.nan
        return result, sorted_codes, sorted_areas.tolist()

    A_bar_req = As[valid] * spacing / 1000.0

    # For each point, find smallest config with area >= A_bar_req
    idx = np.searchsorted(sorted_areas, A_bar_req, side='left')
    matched = np.full(A_bar_req.shape, np.nan)  # beyond largest -> inadequate
    found = idx < len(sorted_areas)
    matched[found] = idx[found] + 1.0  # 1-based index

    result[valid] = matched
    result[np.isnan(As)] = np.nan

    return result, sorted_codes, sorted_areas.tolist()



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
    D : float or array-like
        Bar diameter in mm. An array gives a per-node effective depth, which is
        what solve_rebar_iterative() needs once the bar size varies across the
        slab.
    direction : str
        'x' (outer layer) or 'y' (inner layer).
    layer : str
        'top' or 'bottom' (both have the same d formula, just from different faces).

    Returns
    -------
    float or numpy array : effective depth d (mm), matching the shape of D.
    """
    if direction == 'x':
        return h_mm - cover - 0.5 * D
    else:  # 'y' → inner layer
        return h_mm - cover - D - 0.5 * D


def calc_as_required(Mu_knm, fc, fy, d, phi=PHI_FLEXURE, check_ductility=True):
    """
    Vectorized calculation of required steel area As.

    Uses the SNI/ACI rectangular stress block.
    Input moment in kN·m/m (auto-converted to N·mm/m internally).

    Two independent failure modes both yield np.nan:
      1. Negative value under the square root — the section cannot develop Mu
         in flexure at all.
      2. As > rho_max * b * d — the section could carry Mu but would not be
         tension-controlled, so the assumed phi = 0.90 would be invalid.

    Parameters
    ----------
    Mu_knm : array-like
        Absolute design moment in kN·m/m (always positive).
    fc : float
        Concrete compressive strength in MPa.
    fy : float
        Steel yield strength in MPa.
    d : float or array-like
        Effective depth in mm. Accepts a per-node array so the caller can
        iterate depth against the bar size actually selected.
    phi : float
        Strength reduction factor (default: 0.90).
    check_ductility : bool
        Apply the rho_max tension-controlled check (default: True).

    Returns
    -------
    numpy array : As_required in mm²/m.
        Returns 0.0 where Mu ≈ 0.
        Returns np.nan where the section is inadequate.
    """
    Mu_knm = np.asarray(Mu_knm, dtype=float)
    As = np.zeros(Mu_knm.shape, dtype=float)

    # Convert kN·m/m → N·mm/m
    Mu = Mu_knm * 1e6

    # Mask: only compute where moment is significant
    active = np.abs(Mu) > 1e-3  # threshold: > 0.001 N·mm/m

    if not np.any(active):
        return As

    b = STRIP_WIDTH_MM
    fc_term = 0.85 * fc

    d_arr = np.broadcast_to(np.asarray(d, dtype=float), Mu_knm.shape)
    d_act = d_arr[active]
    Mu_act = Mu[active]

    # Default to inadequate; only nodes that pass every check get a number
    As_act = np.full(d_act.shape, np.nan)

    denominator = phi * fc_term * b * d_act ** 2
    positive = denominator > 0
    if np.any(positive):
        sqrt_arg = 1.0 - (2.0 * Mu_act[positive]) / denominator[positive]
        adequate = sqrt_arg >= 0

        d_positive = d_act[positive]
        vals = np.full(sqrt_arg.shape, np.nan)
        vals[adequate] = (
            (fc_term * b * d_positive[adequate] / fy)
            * (1.0 - np.sqrt(sqrt_arg[adequate]))
        )
        As_act[positive] = vals

    # Ductility check — must stay tension-controlled for phi = 0.90 to hold
    if check_ductility:
        as_max = calc_rho_max(fc, fy) * b * d_act
        with np.errstate(invalid='ignore'):
            As_act[As_act > as_max] = np.nan

    As[active] = As_act
    return As


def apply_as_min(As, fy, h_mm, b=STRIP_WIDTH_MM, surface_zone=None,
                 n_faces=DEFAULT_AS_MIN_FACES):
    """
    Raise one layer's As to its share of the code minimum.

    The share, not the whole: the clause states a total for the direction
    through the full thickness, and this slab is reinforced at both faces.

    Nodes already flagged np.nan stay np.nan — a section that fails is not
    rescued by adding minimum steel.

    Parameters
    ----------
    As : array-like — required steel area in mm²/m.
    fy : float — steel yield strength in MPa.
    h_mm : float — slab thickness in mm.
    b : float — strip width in mm.
    surface_zone : float, optional — cap in mm on the thickness per face.
    n_faces : int — reinforced faces sharing the total.

    Returns
    -------
    numpy array : As in mm²/m, at least the per-face minimum where As is finite.
    """
    As = np.asarray(As, dtype=float)
    as_min = calc_as_min_per_face(fy, h_mm, b, n_faces, surface_zone)
    out = np.where(np.isnan(As), np.nan, np.maximum(As, as_min))
    return out


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
    idx = np.searchsorted(AVAILABLE_DIAMETERS, D_req, side='left')
    result = np.full(D_req.shape, np.nan)  # beyond max 32mm -> inadequate
    found = idx < len(AVAILABLE_DIAMETERS)
    result[found] = AVAILABLE_DIAMETERS[idx[found]]

    D_selected[valid] = result
    D_selected[np.isnan(As)] = np.nan

    return D_selected


def calc_min_spacing(D):
    """
    Minimum centre-to-centre bar spacing (SNI 25.2.1).

    The code limit is a CLEAR distance of at least max(25 mm, db); the
    centre-to-centre spacing is that clear distance plus one bar diameter.
    Treating max(25, db) as centre-to-centre understated the limit.

    Parameters
    ----------
    D : float — bar diameter in mm.

    Returns
    -------
    float : minimum centre-to-centre spacing in mm.
    """
    return D + max(25.0, D)


def check_spacing_limits(s, h_mm, D):
    """
    Apply code spacing limits.

    Asymmetric on purpose:
      - s > s_max  -> clamped DOWN to s_max = min(2h, 450). Conservative and
        correct: it places more steel than strictly required.
      - s < s_min  -> np.nan (SECTION INADEQUATE). Bars physically cannot be
        placed that close, so the section fails for this bar size. Clamping it
        UP (the previous behaviour) made failing zones look acceptable.

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
    numpy array : spacing in mm, np.nan where the section is inadequate.
    """
    s = np.asarray(s, dtype=float)
    s_max = min(2.0 * h_mm, 450.0)
    s_min = calc_min_spacing(D)

    out = np.minimum(s, s_max)

    with np.errstate(invalid='ignore'):
        too_tight = s < s_min
    out[too_tight] = np.nan

    # Preserve NaN (already inadequate) and Inf (no rebar needed)
    out[np.isnan(s)] = np.nan
    out[np.isinf(s)] = np.inf

    return out


# =============================================================================
# Mode B solver — effective depth iterated against the bar actually selected
# =============================================================================

def solve_rebar_iterative(Mu_knm, fc, fy, h_mm, cover, direction, layer,
                          spacing, config_codes=None, apply_min=True,
                          phi=PHI_FLEXURE, max_iter=MAX_DEPTH_ITERATIONS,
                          surface_zone=None):
    """
    Mode B: given a target spacing, solve As and the bar selection together.

    Effective depth depends on bar size, but bar size is the answer. Assuming a
    fixed D16 for the depth (the previous behaviour) overstates d wherever a
    larger bar is actually selected, which UNDERESTIMATES As — unconservative
    exactly in the highly stressed zones that matter.

    The iteration is monotone: the depth diameter is only ever revised upward
    (np.maximum). Growing D shrinks d, which raises As, so the loop is both
    guaranteed to terminate — diameters are bounded — and conservative if it
    stops early.

    Parameters
    ----------
    Mu_knm : array-like
        Absolute design moment in kN·m/m (already sign-filtered per layer).
    fc, fy : float
        Material strengths in MPa.
    h_mm : float
        Slab thickness in mm.
    cover : float
        Clear cover in mm.
    direction : str — 'x' or 'y'.
    layer : str — 'top' or 'bottom'.
    spacing : float
        Target bar spacing in mm.
    config_codes : list of str, optional
        Rebar config codes to choose from (--rebar-select). When None, falls
        back to single bars from AVAILABLE_DIAMETERS.
    apply_min : bool
        Apply the slab minimum reinforcement (default: True).
    phi : float
        Flexural strength reduction factor.
    max_iter : int
        Iteration cap.

    Returns
    -------
    tuple of (As, d_eff, selection, sorted_codes)
        As        : mm²/m, np.nan where inadequate.
        d_eff     : per-node effective depth in mm.
        selection : 1-based config index when config_codes is given,
                    otherwise the selected diameter in mm.
        sorted_codes : config codes ascending by area, or None.
    """
    Mu = np.asarray(Mu_knm, dtype=float)

    if config_codes:
        sorted_codes = sorted(config_codes,
                              key=lambda c: REBAR_CONFIG_TABLE[c.upper()][2])
        # Base bar diameter of each config, aligned with sorted_codes
        base_D = np.array([REBAR_CONFIG_TABLE[c.upper()][0]
                           for c in sorted_codes], dtype=float)
    else:
        sorted_codes = None
        base_D = None

    D_depth = np.full(Mu.shape, SEED_DIAMETER, dtype=float)
    As = d_eff = selection = None

    for _ in range(max_iter):
        d_eff = calc_effective_depth(h_mm, cover, D_depth, direction, layer)
        As = calc_as_required(Mu, fc, fy, d_eff, phi)
        if apply_min:
            As = apply_as_min(As, fy, h_mm, surface_zone=surface_zone)

        D_new = np.full(Mu.shape, SEED_DIAMETER, dtype=float)
        if sorted_codes is not None:
            selection, _, _ = select_config_from_As(As, sorted_codes, spacing)
            with np.errstate(invalid='ignore'):
                picked = selection >= 1
            D_new[picked] = base_D[(selection[picked] - 1).astype(int)]
        else:
            selection = calc_diameter_from_spacing(As, spacing)
            with np.errstate(invalid='ignore'):
                picked = selection > 0
            D_new[picked] = selection[picked]

        # Monotone upward revision — guarantees termination
        D_next = np.maximum(D_depth, D_new)
        if np.array_equal(D_next, D_depth):
            break
        D_depth = D_next

    return As, d_eff, selection, sorted_codes


def format_depth_range(d_eff):
    """
    Format a per-node effective depth for a plot subtitle.

    Returns 'd_eff = 352 mm' when uniform, 'd_eff = 352-369 mm' when it varies.
    """
    d = np.asarray(d_eff, dtype=float)
    if d.ndim == 0 or d.size == 0:
        return f"{float(d):.0f} mm"
    lo, hi = float(np.min(d)), float(np.max(d))
    if abs(hi - lo) < 0.5:
        return f"{lo:.0f} mm"
    return f"{lo:.0f}-{hi:.0f} mm"


# =============================================================================
# Shear Reinforcement Functions (SNI 2847:2019)
# =============================================================================

def calc_Vc(fc, bw, dv, lam=LAMBDA_CONCRETE):
    """
    Concrete shear capacity (SNI 22.5.5.1).

    Vc = 0.17 × λ × √f'c × bw × dv

    Previously this used the AASHTO form 0.083 × β × √f'c with β = 2.0
    (= 0.166), while the flexural side was SNI. The two are numerically within
    2.5%; unifying on SNI keeps code, formulas and documentation consistent.

    Parameters
    ----------
    fc : float
        Concrete compressive strength in MPa.
    bw : float
        Web width in mm (typically 1000 mm for slab strip).
    dv : float
        Effective shear depth in mm.
    lam : float
        Lightweight concrete factor λ (1.0 for normal weight).

    Returns
    -------
    float : Vc in Newtons.
    """
    return 0.17 * lam * np.sqrt(fc) * bw * dv


def calc_Vs_max(fc, bw, dv):
    """
    Upper limit on shear carried by stirrups before web crushing (SNI 22.5.1.2).

    Vs_max = 0.66 × √f'c × bw × dv

    Beyond this no amount of stirrups helps — the section itself must grow.

    Returns
    -------
    float : Vs_max in Newtons.
    """
    return 0.66 * np.sqrt(fc) * bw * dv


def calc_Av_min_per_s(fc, fyt, bw=STRIP_WIDTH_MM):
    """
    Minimum shear reinforcement ratio (SNI 9.6.3.4).

    Av,min/s = max(0.062 √f'c · bw / fyt, 0.35 · bw / fyt)

    Returns
    -------
    float : Av/s in mm²/mm.
    """
    return max(0.062 * np.sqrt(fc) * bw / fyt, 0.35 * bw / fyt)


def calc_shear_Av_per_s(Vu_kn_per_m, fc, fy, dv, lam=LAMBDA_CONCRETE,
                        apply_av_min=True):
    """
    Vectorized calculation of required shear reinforcement Av/s.

    Steps:
      1. Convert Vu from kN/m → N  (×1000, since bw = 1000 mm = 1m)
      2. Vc = 0.17 × λ × √f'c × bw × dv
      3. Shear rebar needed only where |Vu| > 0.5 × φ × Vc
      4. Vs = |Vu|/φ − Vc   (clamped at 0)
      5. Vs > Vs_max        → np.nan (web crushing — thicken the slab)
      6. Av/s = Vs / (fy × dv), raised to Av,min/s

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
    lam : float
        Lightweight concrete factor λ.
    apply_av_min : bool
        Enforce the code minimum where stirrups are required (default: True).

    Returns
    -------
    numpy array : Av/s in mm²/mm.
        0.0 where no shear reinforcement is needed.
        np.nan where the web crushing limit is exceeded.
    """
    Vu_kn = np.asarray(Vu_kn_per_m, dtype=float)
    Vu_abs_N = np.abs(Vu_kn) * 1000.0  # kN/m → N (per 1m strip)

    bw = STRIP_WIDTH_MM  # 1000 mm
    Vc = calc_Vc(fc, bw, dv, lam)
    Vs_max = calc_Vs_max(fc, bw, dv)

    # Threshold: shear rebar needed only if Vu > 0.5 × φ × Vc
    threshold = 0.5 * PHI_SHEAR * Vc
    needs_rebar = Vu_abs_N > threshold

    Av_per_s = np.zeros(Vu_kn.shape, dtype=float)

    if np.any(needs_rebar):
        Vs = (Vu_abs_N[needs_rebar] / PHI_SHEAR) - Vc
        Vs = np.maximum(Vs, 0.0)  # clamp negative to 0

        req = Vs / (fy * dv)
        if apply_av_min:
            req = np.maximum(req, calc_Av_min_per_s(fc, fy, bw))

        # Web crushing — stirrups cannot solve this
        req[Vs > Vs_max] = np.nan

        Av_per_s[needs_rebar] = req

    return Av_per_s


def calc_shear_diameter(Av_per_s, s_long, s_trans, available_diameters=None):
    """
    Calculate required stirrup diameter given Av/s and both spacings.

    For a 1m-wide slab strip with stirrup grid:
      Ab_required = (Av/s) × s_long × s_trans / 1000
      D_required  = √(4 × Ab_required / π)
      → Round UP to nearest standard stirrup diameter from available list.

    Parameters
    ----------
    Av_per_s : array-like
        Required shear reinforcement in mm²/mm.
    s_long : float
        Longitudinal spacing in mm (along shear direction).
    s_trans : float
        Transversal spacing in mm (across 1m strip width).
    available_diameters : array-like, optional
        Custom list of available stirrup diameters in mm.
        If None, uses default SHEAR_DIAMETERS [10, 13, 16, 19, 22, 25].

    Returns
    -------
    numpy array : selected diameter in mm.
        Returns 0.0 where Av/s ≈ 0 (no shear rebar needed).
        Returns np.nan where required diameter exceeds max available.
    """
    diameters = np.asarray(available_diameters, dtype=float) if available_diameters is not None else SHEAR_DIAMETERS
    diameters = np.sort(diameters)

    Av_per_s = np.asarray(Av_per_s, dtype=float)
    D_selected = np.zeros(Av_per_s.shape, dtype=float)

    with np.errstate(invalid='ignore'):
        active = Av_per_s > 1e-9

    # Propagate web-crushing failures — without this they read as "0 = no
    # stirrups needed", the exact opposite of the truth.
    D_selected[np.isnan(Av_per_s)] = np.nan

    if not np.any(active):
        return D_selected

    # Area per single stirrup leg
    Ab_req = Av_per_s[active] * s_long * s_trans / 1000.0
    D_req = np.sqrt(4.0 * Ab_req / np.pi)

    # Round UP to the nearest available stirrup diameter
    idx = np.searchsorted(diameters, D_req, side='left')
    result = np.full(D_req.shape, np.nan)  # beyond largest -> inadequate
    found = idx < len(diameters)
    result[found] = diameters[idx[found]]

    D_selected[active] = result
    return D_selected

