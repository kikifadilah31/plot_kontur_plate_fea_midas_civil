"""
Mathematical utilities — single source of truth for stress calculation and helpers.
Eliminates duplication between plotter and reporter.
"""

import numpy as np
from .config import STRIP_WIDTH


def calculate_stress_vectorized(axial, moment, thickness):
    """
    Vectorized stress calculation at top and bottom fiber.

    Formula: σ = N/A - (M·y)/I
    Sign Convention (Midas Civil):
      - Axial (+) = Tension
      - Moment (+) → Top Fiber Compression (-), Bottom Fiber Tension (+)

    Parameters
    ----------
    axial : array-like
        Axial force values (kN/m).
    moment : array-like
        Moment values (kN·m/m).
    thickness : float
        Plate thickness in meters.

    Returns
    -------
    tuple of (top_stress, bottom_stress) as numpy arrays (kPa).
    """
    area = thickness * STRIP_WIDTH
    inertia = (STRIP_WIDTH * thickness ** 3) / 12
    y_top = thickness / 2
    y_bottom = -thickness / 2

    axial_stress = axial / area
    top_stress = axial_stress - (moment * y_top) / inertia
    bottom_stress = axial_stress - (moment * y_bottom) / inertia

    return top_stress, bottom_stress


def safe_filename(name):
    """Convert a column name or string to a safe filename component."""
    return (name
            .replace('(', '').replace(')', '')
            .replace('·', '').replace(' ', '_')
            .replace('/', '_per_')
            .replace('[', '').replace(']', '')
            .replace(',', ''))


def format_value(val, decimals=2):
    """Format a numeric value for report display."""
    if np.isnan(val):
        return "N/A"
    return f"{val:+.{decimals}f}"
