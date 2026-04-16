"""
Plotly interactive plotting engine for FEA Streamlit UI.

Generates interactive contour figures for display in the browser.
Also provides a simple matplotlib save helper for static PNG export.
"""

import os
import numpy as np
import plotly.graph_objects as go
from scipy.interpolate import griddata
from matplotlib.tri import Triangulation, LinearTriInterpolator

from .rebar import AVAILABLE_DIAMETERS

INADEQUATE_COLOR = '#8B008B'  # DarkMagenta — matches CLI


# =============================================================================
# Grid Interpolation Helpers
# =============================================================================

def _tri_interpolate_to_grid(x, y, z, triangles, nx=300, ny=300):
    """
    Interpolate triangulated (nodal) data to a regular grid
    using matplotlib's LinearTriInterpolator.
    """
    tri = Triangulation(x, y, triangles)
    interp = LinearTriInterpolator(tri, z)

    xi = np.linspace(float(x.min()), float(x.max()), nx)
    yi = np.linspace(float(y.min()), float(y.max()), ny)
    Xi, Yi = np.meshgrid(xi, yi)
    Zi = interp(Xi, Yi)

    return xi, yi, np.ma.filled(Zi, np.nan)


def _scatter_interpolate_to_grid(x, y, z, nx=300, ny=300):
    """
    Interpolate scattered (centroid) data to a regular grid
    using scipy's griddata.
    """
    xi = np.linspace(float(np.nanmin(x)), float(np.nanmax(x)), nx)
    yi = np.linspace(float(np.nanmin(y)), float(np.nanmax(y)), ny)
    Xi, Yi = np.meshgrid(xi, yi)
    Zi = griddata((x, y), z, (Xi, Yi), method='linear')

    return xi, yi, Zi


def _get_extremes(mesh, z_values, method):
    """Get max/min values and their (x, y) coordinates."""
    if method == 'element-center':
        cx = np.array([c[0] for c in mesh.centroids])
        cy = np.array([c[1] for c in mesh.centroids])
    else:
        cx, cy = mesh.x, mesh.y

    # Handle NaN/Inf gracefully
    valid = np.isfinite(z_values)
    if not np.any(valid):
        return None

    z_clean = np.where(valid, z_values, np.nan)
    max_idx = int(np.nanargmax(z_clean))
    min_idx = int(np.nanargmin(z_clean))

    return {
        'max_val': float(z_clean[max_idx]),
        'min_val': float(z_clean[min_idx]),
        'max_x': float(cx[max_idx]),
        'max_y': float(cy[max_idx]),
        'min_x': float(cx[min_idx]),
        'min_y': float(cy[min_idx]),
    }


def _add_annotations(fig, extremes):
    """Add MAX/MIN diamond markers and text annotations to a Plotly figure."""
    if extremes is None:
        return

    mx, my = extremes['max_x'], extremes['max_y']
    nx_, ny_ = extremes['min_x'], extremes['min_y']
    mv, nv = extremes['max_val'], extremes['min_val']

    # MAX marker (red diamond)
    fig.add_trace(go.Scatter(
        x=[mx], y=[my], mode='markers+text',
        marker=dict(symbol='diamond', size=14, color='#DC143C',
                    line=dict(width=2, color='white')),
        text=[f'MAX: {mv:+.2f}<br>({mx:.2f}, {my:.2f})'],
        textposition='top center',
        textfont=dict(size=10, color='#DC143C', family='Arial Black'),
        showlegend=False, hoverinfo='skip',
    ))

    # MIN marker (blue diamond)
    fig.add_trace(go.Scatter(
        x=[nx_], y=[ny_], mode='markers+text',
        marker=dict(symbol='diamond', size=14, color='#1E90FF',
                    line=dict(width=2, color='white')),
        text=[f'MIN: {nv:+.2f}<br>({nx_:.2f}, {ny_:.2f})'],
        textposition='bottom center',
        textfont=dict(size=10, color='#1E90FF', family='Arial Black'),
        showlegend=False, hoverinfo='skip',
    ))


# =============================================================================
# Plotly Contour Generators
# =============================================================================

def generate_contour_plotly(mesh, z_values, col_name, method, colorscale='RdBu_r'):
    """
    Generate an interactive Plotly contour figure with:
    - Symmetric colorbar (matching CLI's vmin=-abs_max, vmax=+abs_max)
    - MAX/MIN diamond annotations
    """
    if method == 'element-center':
        cx = np.array([c[0] for c in mesh.centroids])
        cy = np.array([c[1] for c in mesh.centroids])
        xi, yi, Zi = _scatter_interpolate_to_grid(cx, cy, z_values)
    else:
        xi, yi, Zi = _tri_interpolate_to_grid(
            mesh.x, mesh.y, z_values, mesh.triangles,
        )

    # Symmetric colorbar — same logic as CLI plotting.py
    z_min = float(np.nanmin(z_values))
    z_max = float(np.nanmax(z_values))
    z_abs_max = max(abs(z_min), abs(z_max))
    if z_abs_max == 0:
        z_abs_max = 1.0
    vmin, vmax = -z_abs_max, z_abs_max

    fig = go.Figure(data=[
        go.Contour(
            x=xi, y=yi, z=Zi,
            colorscale=colorscale,
            zmin=vmin, zmax=vmax,
            contours=dict(
                coloring='heatmap',
                showlabels=True,
                labelfont=dict(size=8, color='white'),
            ),
            colorbar=dict(
                title=dict(text=col_name, side='right'),
            ),
            hovertemplate=(
                'X: %{x:.2f} m<br>Y: %{y:.2f} m<br>'
                'Value: %{z:.2f}<extra></extra>'
            ),
        )
    ])

    # Add MAX/MIN annotations
    extremes = _get_extremes(mesh, z_values, method)
    _add_annotations(fig, extremes)

    fig.update_layout(
        title=dict(text=col_name, x=0.5),
        xaxis_title='X (m)',
        yaxis_title='Y (m)',
        yaxis=dict(scaleanchor='x', scaleratio=1),
        height=550,
        margin=dict(l=60, r=60, t=50, b=50),
        template='plotly_white',
    )

    return fig


def generate_rebar_plotly(mesh, z_values, col_name, method, mode='diameter'):
    """
    Generate an interactive Plotly rebar contour figure with:
    - SECTION INADEQUATE warning for diameter > D32 (NaN values)
    - MAX/MIN diamond annotations
    - Discrete colorscale for diameter mode
    """
    # Pre-process: detect NaN (section inadequate) and Inf (no rebar needed)
    z_plot = z_values.copy().astype(float)
    has_nan = np.any(np.isnan(z_plot))
    n_inad = int(np.sum(np.isnan(z_plot)))

    # Replace inf with 0 (no rebar needed), NaN stays for inadequate
    z_plot[np.isinf(z_plot)] = 0.0

    if method == 'element-center':
        cx = np.array([c[0] for c in mesh.centroids])
        cy = np.array([c[1] for c in mesh.centroids])
        xi, yi, Zi = _scatter_interpolate_to_grid(cx, cy, z_plot)
    else:
        xi, yi, Zi = _tri_interpolate_to_grid(
            mesh.x, mesh.y, z_plot, mesh.triangles,
        )

    if mode == 'diameter':
        is_shear = 'shear' in col_name.lower() or 'geser' in col_name.lower()
        if is_shear:
            from .rebar import SHEAR_DIAMETERS as AVAIL_D
        else:
            from .rebar import AVAILABLE_DIAMETERS as AVAIL_D

        d_min = float(AVAIL_D[0])
        d_max = float(AVAIL_D[-1])

        colors = ['#ffffb2', '#fecc5c', '#fd8d3c', '#f03b20', '#bd0026', '#4d004b']
        # Resample colors to match length of AVAIL_D
        import matplotlib.colors as mcolors
        import matplotlib.cm as cm
        try:
            base_cmap = matplotlib.colormaps['YlOrRd'].resampled(len(AVAIL_D))
        except AttributeError:
            base_cmap = cm.get_cmap('YlOrRd', len(AVAIL_D))
        
        cs = []
        for i, d in enumerate(AVAIL_D):
            lo = (d - d_min) / (d_max - d_min)
            # Extracted rgba for plotly colorscale
            rgba = base_cmap(i / max(1, len(AVAIL_D) - 1))
            hex_col = mcolors.to_hex(rgba)
            cs.append([lo, hex_col])
            
            hi = lo if i == len(AVAIL_D) - 1 else (
                (AVAIL_D[i + 1] - d_min) / (d_max - d_min)
            )
            cs.append([hi, hex_col])

        fig = go.Figure(data=[
            go.Contour(
                x=xi, y=yi, z=Zi,
                colorscale=cs,
                zmin=d_min, zmax=d_max,
                contours=dict(coloring='heatmap'),
                colorbar=dict(
                    title=dict(text='Diameter (mm)'),
                    tickvals=AVAIL_D.tolist() if hasattr(AVAIL_D, 'tolist') else list(AVAIL_D),
                    ticktext=[f'D{int(d)}' for d in AVAIL_D],
                ),
                hovertemplate=(
                    'X: %{x:.2f} m<br>Y: %{y:.2f} m<br>'
                    'D: %{z:.0f} mm<extra></extra>'
                ),
            )
        ])
    else:
        cscale = 'YlOrRd_r' if mode == 'spacing' else 'YlOrRd'
        unit = 'mm' if mode == 'spacing' else 'mm\u00b2/m'
        fig = go.Figure(data=[
            go.Contour(
                x=xi, y=yi, z=Zi,
                colorscale=cscale,
                contours=dict(
                    coloring='heatmap',
                    showlabels=True,
                    labelfont=dict(size=8),
                ),
                colorbar=dict(title=dict(text=f'{col_name} ({unit})')),
                hovertemplate=(
                    'X: %{x:.2f} m<br>Y: %{y:.2f} m<br>'
                    f'Value: %{{z:.1f}} {unit}<extra></extra>'
                ),
            )
        ])

    # Add MAX/MIN annotations (on cleaned data)
    extremes = _get_extremes(mesh, z_plot, method)
    _add_annotations(fig, extremes)

    # SECTION INADEQUATE badge — matching CLI
    if has_nan and n_inad > 0:
        fig.add_annotation(
            text=f'⚠ SECTION INADEQUATE: {n_inad} points',
            xref='paper', yref='paper',
            x=0.98, y=0.02,
            showarrow=False,
            font=dict(size=12, color='white', family='Arial Black'),
            bgcolor=INADEQUATE_COLOR,
            bordercolor='white',
            borderwidth=2,
            borderpad=6,
            opacity=0.9,
        )

    fig.update_layout(
        title=dict(text=col_name, x=0.5),
        xaxis_title='X (m)',
        yaxis_title='Y (m)',
        yaxis=dict(scaleanchor='x', scaleratio=1),
        height=550,
        margin=dict(l=60, r=60, t=50, b=50),
        template='plotly_white',
    )

    return fig
