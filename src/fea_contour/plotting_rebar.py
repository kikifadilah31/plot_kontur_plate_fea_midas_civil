"""
Plotting engine for rebar analysis — specialized contour visualization.
Uses sequential colormap (YlOrRd) instead of diverging (RdBu_r).
Handles NaN masking for Section Inadequate zones.
"""

import os

import matplotlib
matplotlib.use('Agg')  # CRITICAL: Must be before pyplot import

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as cm
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import PolyCollection

from .config import PLOT_FIGSIZE, PLOT_DPI_WORKER, PLOT_DPI_SAVE, CONTOUR_LEVELS
from .math_utils import safe_filename

# =============================================================================
# Rebar-specific colormap
# =============================================================================
REBAR_CMAP = 'YlOrRd'
INADEQUATE_COLOR = '#404040'  # Dark Gray for Section Inadequate zones

import threading
thread_local_rb = threading.local()

# =============================================================================
# GLOBAL WORKER VARIABLES (For Figure Recycling)
# =============================================================================
rebar_fig = None
rebar_ax = None

def init_rebar_worker():
    """Initializer for Pool: Sets up the backend."""
    plt.switch_backend('Agg')

def generate_rebar_plot_worker(task):
    """
    Rebar-specific plotting worker with figure recycling.

    Task tuple:
        (x, y, z, triangles, polygons, centroids,
         plot_label, unit_label, subtitle, load_name,
         output_folder, contour_method, show_mesh, theme, filename_tag)
    """
    try:
        if not hasattr(thread_local_rb, "fig"):
            # Use strictly Object-Oriented API to prevent pyplot state-machine crashes in multiprocessing
            fig = Figure(figsize=PLOT_FIGSIZE, dpi=PLOT_DPI_WORKER)
            FigureCanvasAgg(fig)
            thread_local_rb.fig = fig
            thread_local_rb.ax = fig.add_subplot(111)
            
        rebar_fig = thread_local_rb.fig
        rebar_ax = thread_local_rb.ax
        (x, y, z, triangles, polygons, centroids,
         plot_label, unit_label, subtitle, load_name,
         output_folder, contour_method, show_mesh, theme, filename_tag) = task

        is_dark = theme == 'dark'
        bg_col = '#1E1E1E' if is_dark else '#FFFFFF'
        text_col = '#E0E0E0' if is_dark else '#2C3E50'
        grid_col = '#333333' if is_dark else '#E5E5E5'

        # --- Clear and setup ---
        rebar_fig.clear()
        rebar_fig.patch.set_facecolor(bg_col)
        rebar_ax = rebar_fig.add_subplot(111)
        rebar_ax.set_facecolor(bg_col)

        # Dynamic figure resizing based on data geometry
        if len(x) > 0 and len(y) > 0:
            x_range = np.max(x) - np.min(x)
            y_range = np.max(y) - np.min(y)
            if x_range > 0 and y_range > 0:
                data_ratio = x_range / y_range
                fig_w = 14.0
                fig_h = (fig_w - 3.0) / data_ratio + 2.5
                fig_h = max(5.0, min(14.0, fig_h))
                rebar_fig.set_size_inches(fig_w, fig_h, forward=True)

        # --- Prepare data ---
        z_plot = z.copy()
        has_nan = np.any(np.isnan(z_plot))
        has_inf = np.any(np.isinf(z_plot))

        # Replace inf with 0 for plotting (areas with no rebar needed)
        z_plot[np.isinf(z_plot)] = 0.0

        # For NaN (inadequate), we'll mask them and plot them separately
        nan_mask = np.isnan(z_plot)
        z_plot[nan_mask] = 0.0

        # Determine value range (only finite positive values)
        finite_vals = z_plot[~nan_mask & (z_plot > 0)]
        if len(finite_vals) > 0:
            vmin = 0.0
            vmax = np.max(finite_vals)
        else:
            vmin, vmax = 0.0, 1.0

        if vmax <= vmin:
            vmax = vmin + 1.0

        # Detect plot type from filename_tag
        fn_lower = filename_tag.lower()
        is_diameter_plot = 'diameter' in fn_lower or '_shear_d_' in fn_lower
        is_shear = 'shear' in fn_lower

        if is_diameter_plot:
            from matplotlib.colors import BoundaryNorm, ListedColormap
            if is_shear:
                from .rebar import SHEAR_DIAMETERS as AVAIL_D
            else:
                from .rebar import AVAILABLE_DIAMETERS as AVAIL_D
                
            # Boundaries: [-0.1, 0.1, limit1, limit2, ..., limitN, overflow]
            boundaries = [-0.1, 0.1] + list(AVAIL_D) + [AVAIL_D[-1] + 3]
            n_bins = len(boundaries) - 1
            
            # Explicit highly contrasting categorical palette!
            distinct_colors = [
                '#FFFFFF',  # 0.0 (Safe / 0) -> White
                '#3498DB',  # Bin 1 (Blue)
                '#2ECC71',  # Bin 2 (Green)
                '#F1C40F',  # Bin 3 (Yellow)
                '#E67E22',  # Bin 4 (Orange)
                '#E74C3C',  # Bin 5 (Red)
                '#9B59B6',  # Bin 6 (Purple)
                '#FF1493',  # Overflows...
                '#00FFFF',  # Overflows...
            ]
            
            cmap_colors = distinct_colors[:n_bins]
            cmap_colors[-1] = mcolors.to_rgba(INADEQUATE_COLOR)
            cmap = mcolors.ListedColormap(cmap_colors)
            norm = mcolors.BoundaryNorm(boundaries, cmap.N)
            levels = boundaries
        else:
            try:
                cmap = matplotlib.colormaps[REBAR_CMAP].resampled(CONTOUR_LEVELS)
            except AttributeError:
                cmap = cm.get_cmap(REBAR_CMAP, CONTOUR_LEVELS)
            norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
            levels = np.linspace(vmin, vmax, CONTOUR_LEVELS + 1)

        max_idx = np.argmax(z_plot)
        max_val = z_plot[max_idx]

        # --- Draw contour ---
        if contour_method in ('average-nodal', 'element-nodal'):
            if contour_method == 'average-nodal':
                pc = rebar_ax.tricontourf(
                    x, y, triangles, z_plot,
                    levels=levels, cmap=cmap, norm=norm, extend='max',
                )
                # Subtle isolines
                isoline_col = 'black' if is_dark else 'white'
                rebar_ax.tricontour(x, y, triangles, z_plot, levels=levels,
                                    colors=isoline_col, linewidths=0.2, alpha=0.4)
            else:
                pc = rebar_ax.tripcolor(
                    x, y, triangles, z_plot,
                    cmap=cmap, norm=norm, shading='gouraud',
                )

            if show_mesh:
                lw = 0.2 if contour_method == 'average-nodal' else 0.3
                alpha = 0.5 if contour_method == 'average-nodal' else 0.8
                rebar_ax.triplot(x, y, triangles,
                                 color='black' if not is_dark else 'white',
                                 linewidth=lw, alpha=alpha)

            max_xy = (x[max_idx], y[max_idx])

            # Mark Section Inadequate zones (NaN)
            if has_nan and np.any(nan_mask):
                rebar_ax.tricontourf(
                    x, y, triangles, nan_mask.astype(float),
                    levels=[0.5, 1.5], colors=[INADEQUATE_COLOR], alpha=0.7,
                )

        else:
            edge_color = 'black' if show_mesh else 'face'
            line_width = 0.3 if show_mesh else 0
            pc = PolyCollection(
                polygons, array=z_plot, cmap=cmap, norm=norm,
                edgecolors=edge_color, linewidths=line_width, alpha=1.0,
            )
            rebar_ax.add_collection(pc)

            if centroids:
                max_xy = centroids[max_idx]
            else:
                max_xy = (0, 0)

            if polygons:
                all_x = [p[0] for poly in polygons for p in poly]
                all_y = [p[1] for poly in polygons for p in poly]
                rebar_ax.set_xlim(min(all_x) - 1.0, max(all_x) + 1.0)
                rebar_ax.set_ylim(min(all_y) - 1.0, max(all_y) + 1.0)

        # --- Annotations ---
        y_range_ax = rebar_ax.get_ylim()[1] - rebar_ax.get_ylim()[0]
        offset = y_range_ax * 0.06

        bbox_style = dict(boxstyle='round,pad=0.5', fc=bg_col, ec='#DC143C', lw=1.5, alpha=0.9)
        arrow_style = dict(arrowstyle='-|>,head_width=0.4,head_length=0.6',
                           color='#DC143C', lw=1.5, connectionstyle='arc3,rad=0.3')

        # Smart HA positioning
        x_range_data = np.max(x) - np.min(x)
        x_min_data = np.min(x)
        ha = 'right' if max_xy[0] > x_min_data + 0.8 * x_range_data else \
             'left' if max_xy[0] < x_min_data + 0.2 * x_range_data else 'center'

        if max_val > 0:
            rebar_ax.plot(
                max_xy[0], max_xy[1], 'D', ms=12, color='#DC143C',
                markeredgecolor='white', markeredgewidth=1.5, zorder=10,
            )
            if is_diameter_plot:
                max_text = f'MAX: D{int(max_val)}\n@ ({max_xy[0]:.2f}, {max_xy[1]:.2f})'
            else:
                max_text = f'MAX: {max_val:.1f} {unit_label}\n@ ({max_xy[0]:.2f}, {max_xy[1]:.2f})'
            rebar_ax.annotate(
                max_text, xy=max_xy, xytext=(max_xy[0], max_xy[1] + offset),
                fontsize=10, fontweight='bold', color=text_col, ha=ha, va='bottom',
                bbox=bbox_style, arrowprops=arrow_style, zorder=11,
            )

        # Section Inadequate warning badge
        if has_nan:
            n_inad = np.sum(np.isnan(z))
            rebar_ax.text(
                0.98, 0.02,
                f'SECTION INADEQUATE: {n_inad} points',
                transform=rebar_ax.transAxes, fontsize=10,
                fontweight='bold', color='white', ha='right', va='bottom',
                bbox=dict(boxstyle='round,pad=0.5', fc=INADEQUATE_COLOR, ec='white',
                          lw=1.5, alpha=0.9),
            )

        # --- Axes styling ---
        rebar_ax.set_aspect('equal')
        rebar_ax.set_xlabel('X Coordinate (m)', fontsize=12, fontweight='bold', color=text_col)
        rebar_ax.set_ylabel('Y Coordinate (m)', fontsize=12, fontweight='bold', color=text_col)

        title_str = f'{load_name} - {plot_label}'
        if subtitle:
            title_str += f'\n{subtitle}'
        rebar_ax.set_title(title_str, fontsize=16, fontweight='bold', pad=25, color=text_col)

        rebar_ax.grid(False)
        for spine in rebar_ax.spines.values():
            spine.set_color(text_col)
        rebar_ax.tick_params(colors=text_col)

        # --- Colorbar ---
        from mpl_toolkits.axes_grid1 import make_axes_locatable
        divider = make_axes_locatable(rebar_ax)
        cax = divider.append_axes("right", size="2%", pad=0.4)
        cbar = rebar_fig.colorbar(pc, cax=cax, orientation='vertical')

        if is_diameter_plot:
            # Discrete ticks at each available diameter
            from .rebar import AVAILABLE_DIAMETERS as AVAIL_D
            tick_vals = [0] + list(AVAIL_D)
            tick_labels = ['0'] + [f'D{int(d)}' for d in AVAIL_D]
            cbar.set_ticks(tick_vals)
            cbar.set_ticklabels(tick_labels)

        cax.set_title(f'{unit_label}\n', fontsize=10, color=text_col, fontweight='bold')
        cax.tick_params(colors=text_col, labelsize=9)
        cbar.outline.set_edgecolor(text_col)
        cbar.set_label(plot_label, fontsize=11, fontweight='bold', color=text_col)

        # --- Save ---
        try:
            rebar_fig.tight_layout()
        except:
            pass

        output_path = os.path.join(
            output_folder,
            f"rebar_{safe_filename(filename_tag)}.png",
        )
        rebar_fig.savefig(output_path, dpi=PLOT_DPI_SAVE, bbox_inches='tight', facecolor=bg_col)

        return {'status': 'ok', 'path': output_path}

    except Exception as e:
        tag = task[14] if len(task) > 14 else 'unknown'
        return {'status': 'error', 'task': tag, 'error': str(e)}
