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


# =============================================================================
# Plotly Contour Generators
# =============================================================================

def generate_contour_plotly(mesh, z_values, col_name, method, colorscale='RdBu_r'):
    """
    Generate an interactive Plotly contour figure.

    Parameters
    ----------
    mesh : MeshTopology
    z_values : np.ndarray
    col_name : str
    method : str
    colorscale : str

    Returns
    -------
    go.Figure
    """
    if method == 'element-center':
        cx = np.array([c[0] for c in mesh.centroids])
        cy = np.array([c[1] for c in mesh.centroids])
        xi, yi, Zi = _scatter_interpolate_to_grid(cx, cy, z_values)
    else:
        xi, yi, Zi = _tri_interpolate_to_grid(
            mesh.x, mesh.y, z_values, mesh.triangles,
        )

    fig = go.Figure(data=[
        go.Contour(
            x=xi, y=yi, z=Zi,
            colorscale=colorscale,
            contours=dict(
                coloring='heatmap',
                showlabels=True,
                labelfont=dict(size=8, color='white'),
            ),
            colorbar=dict(title=dict(text=col_name, side='right')),
            hovertemplate=(
                'X: %{x:.2f} m<br>Y: %{y:.2f} m<br>'
                'Value: %{z:.2f}<extra></extra>'
            ),
        )
    ])

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
    Generate an interactive Plotly rebar contour figure.

    Parameters
    ----------
    mesh : MeshTopology
    z_values : np.ndarray
    col_name : str
    method : str
    mode : str — 'diameter', 'spacing', or 'as'

    Returns
    -------
    go.Figure
    """
    if method == 'element-center':
        cx = np.array([c[0] for c in mesh.centroids])
        cy = np.array([c[1] for c in mesh.centroids])
        xi, yi, Zi = _scatter_interpolate_to_grid(cx, cy, z_values)
    else:
        xi, yi, Zi = _tri_interpolate_to_grid(
            mesh.x, mesh.y, z_values, mesh.triangles,
        )

    if mode == 'diameter':
        d_min = float(AVAILABLE_DIAMETERS[0])
        d_max = float(AVAILABLE_DIAMETERS[-1])

        colors = ['#ffffb2', '#fecc5c', '#fd8d3c', '#f03b20', '#bd0026', '#4d004b']
        cs = []
        for i, d in enumerate(AVAILABLE_DIAMETERS):
            lo = (d - d_min) / (d_max - d_min)
            cs.append([lo, colors[i]])
            hi = lo if i == len(AVAILABLE_DIAMETERS) - 1 else (
                (AVAILABLE_DIAMETERS[i + 1] - d_min) / (d_max - d_min)
            )
            cs.append([hi, colors[i]])

        fig = go.Figure(data=[
            go.Contour(
                x=xi, y=yi, z=Zi,
                colorscale=cs,
                zmin=d_min, zmax=d_max,
                contours=dict(coloring='heatmap'),
                colorbar=dict(
                    title=dict(text='Diameter (mm)'),
                    tickvals=AVAILABLE_DIAMETERS.tolist(),
                    ticktext=[f'D{int(d)}' for d in AVAILABLE_DIAMETERS],
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


# =============================================================================
# Matplotlib Save Helper (for static PNG export)
# =============================================================================

def save_contour_matplotlib(mesh, z_values, col_name, method, output_path,
                            show_mesh=False, theme='light', cmap='RdBu_r',
                            levels=24):
    """
    Generate and save a static contour plot using Matplotlib.

    Parameters
    ----------
    mesh : MeshTopology
    z_values : np.ndarray
    col_name : str
    method : str
    output_path : str
    show_mesh : bool
    theme : str
    cmap : str
    levels : int
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection

    if theme == 'dark':
        plt.style.use('dark_background')
    else:
        plt.style.use('default')

    fig, ax = plt.subplots(figsize=(14, 8))

    if method == 'element-center':
        pc = PolyCollection(
            mesh.polygons, array=z_values, cmap=cmap,
            edgecolors='gray' if show_mesh else 'none',
            linewidths=0.3,
        )
        ax.add_collection(pc)
        ax.autoscale_view()
        plt.colorbar(pc, ax=ax, label=col_name, shrink=0.8)
    else:
        tri = Triangulation(mesh.x, mesh.y, mesh.triangles)
        tcf = ax.tricontourf(tri, z_values, levels=levels, cmap=cmap)
        if show_mesh:
            ax.triplot(tri, 'k-', linewidth=0.2, alpha=0.3)
        plt.colorbar(tcf, ax=ax, label=col_name, shrink=0.8)

    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m)')
    ax.set_title(col_name)
    ax.set_aspect('equal')

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close(fig)
