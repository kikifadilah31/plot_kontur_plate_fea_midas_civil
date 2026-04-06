"""
Centralized configuration — single source of truth for all constants.
All values that were previously hardcoded across multiple files live here.
"""

# =============================================================================
# Section Properties
# =============================================================================
DEFAULT_THICKNESS = 0.400  # meters (can be overridden by CLI --thickness)
STRIP_WIDTH = 1.0           # meters (hardcoded: FEA plate/shell output is always per 1m width)

# =============================================================================
# Column Definitions
# =============================================================================
FORCE_COLUMNS = [
    'Fxx (kN/m)', 'Fyy (kN/m)', 'Fxy (kN/m)', 'Fmax (kN/m)', 'Fmin (kN/m)',
    'Mxx (kN·m/m)', 'Myy (kN·m/m)', 'Mxy (kN·m/m)', 'Mmax (kN·m/m)', 'Mmin (kN·m/m)',
    'Vxx (kN/m)', 'Vyy (kN/m)',
]

STRESS_COLUMNS = [
    'Sig-xx_Top (kPa)', 'Sig-xx_Bottom (kPa)',
    'Sig-yy_Top (kPa)', 'Sig-yy_Bottom (kPa)',
]

PLOTTABLE_COLUMNS = FORCE_COLUMNS + STRESS_COLUMNS

# Mapping: stress column → (axial force column, moment column)
STRESS_PAIRS = {
    'Sig-xx_Top (kPa)':    ('Fxx (kN/m)', 'Mxx (kN·m/m)'),
    'Sig-xx_Bottom (kPa)': ('Fxx (kN/m)', 'Mxx (kN·m/m)'),
    'Sig-yy_Top (kPa)':    ('Fyy (kN/m)', 'Myy (kN·m/m)'),
    'Sig-yy_Bottom (kPa)': ('Fyy (kN/m)', 'Myy (kN·m/m)'),
}

# =============================================================================
# Plot Settings
# =============================================================================
PLOT_DPI_SAVE = 300
PLOT_DPI_WORKER = 150
PLOT_FIGSIZE = (16, 12)
PLOT_CMAP = 'coolwarm'
CONTOUR_LEVELS = 24

# =============================================================================
# Contour Methods
# =============================================================================
ALL_METHODS = ['average-nodal', 'element-nodal', 'element-center']

# =============================================================================
# Auto-detect Patterns
# =============================================================================
INPUT_FOLDER = 'input'
OUTPUT_FOLDER = 'output'
FILE_PATTERNS = {
    'kordinat': '*kordinat*.csv',
    'connectivity': '*connect*.csv',
    'gaya': '*gaya*.csv',
}
