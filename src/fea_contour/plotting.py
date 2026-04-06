"""
Plotting engine — multiprocessing worker and plot generation.
Handles figure recycling and contour visualization.
"""

import os

import matplotlib
matplotlib.use('Agg')  # CRITICAL: Must be before pyplot import

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

from .config import PLOT_FIGSIZE, PLOT_DPI_WORKER, PLOT_DPI_SAVE, PLOT_CMAP, CONTOUR_LEVELS
from .math_utils import safe_filename

# =============================================================================
# GLOBAL WORKER VARIABLES (For Figure Recycling)
# =============================================================================
worker_fig = None
worker_ax = None


def init_worker():
    """Initializer for Pool: Creates ONE figure per CPU process."""
    global worker_fig, worker_ax
    worker_fig, worker_ax = plt.subplots(figsize=PLOT_FIGSIZE, dpi=PLOT_DPI_WORKER)


def generate_plot_worker(task):
    """
    Hyper-optimized plotting function with figure recycling and error handling.

    Recycles worker_fig/worker_ax to avoid creating new figures per plot.
    Returns dict with status, path, and error info.
    """
    global worker_fig, worker_ax

    try:
        (x, y, z, triangles, polygons, centroids,
         force_col, display_name, title_suffix, load_name,
         output_folder, contour_method, show_mesh,
         axial_array, moment_array) = task

        # Clear entire figure to remove old colorbars
        worker_fig.clear()
        worker_ax = worker_fig.add_subplot(111)

        z_min, z_max = np.min(z), np.max(z)
        z_abs_max = max(abs(z_min), abs(z_max))
        vmin, vmax = -z_abs_max, z_abs_max
        if vmin == vmax:
            vmin, vmax = -1, 1

        norm = plt.Normalize(vmin=vmin, vmax=vmax)
        levels = np.linspace(vmin, vmax, CONTOUR_LEVELS + 1)
        cmap = plt.get_cmap(PLOT_CMAP, CONTOUR_LEVELS)

        max_idx, min_idx = np.argmax(z), np.argmin(z)
        max_val, min_val = z[max_idx], z[min_idx]

        # --- Draw contour ---
        if contour_method in ('average-nodal', 'element-nodal'):
            if contour_method == 'average-nodal':
                pc = worker_ax.tricontourf(
                    x, y, triangles, z,
                    levels=levels, cmap=cmap, norm=norm, extend='both',
                )
            else:
                pc = worker_ax.tripcolor(
                    x, y, triangles, z,
                    cmap=cmap, norm=norm, shading='gouraud',
                )

            if show_mesh:
                lw = 0.2 if contour_method == 'average-nodal' else 0.3
                alpha = 0.5 if contour_method == 'average-nodal' else 0.8
                worker_ax.triplot(x, y, triangles, color='black', linewidth=lw, alpha=alpha)

            max_xy = (x[max_idx], y[max_idx])
            min_xy = (x[min_idx], y[min_idx])
        else:
            edge_color = 'black' if show_mesh else 'face'
            line_width = 0.3 if show_mesh else 0
            pc = PolyCollection(
                polygons, array=z, cmap=cmap, norm=norm,
                edgecolors=edge_color, linewidths=line_width, alpha=1.0,
            )
            worker_ax.add_collection(pc)

            if centroids:
                max_xy = centroids[max_idx]
                min_xy = centroids[min_idx]
            else:
                max_xy = min_xy = (0, 0)

            if polygons:
                all_x = [p[0] for poly in polygons for p in poly]
                all_y = [p[1] for poly in polygons for p in poly]
                worker_ax.set_xlim(min(all_x) - 1.0, max(all_x) + 1.0)
                worker_ax.set_ylim(min(all_y) - 1.0, max(all_y) + 1.0)

        # --- Annotations ---
        offset = (worker_ax.get_xlim()[1] - worker_ax.get_xlim()[0]) * 0.05

        show_forces = axial_array is not None and moment_array is not None
        if show_forces and len(axial_array) > max_idx and len(moment_array) > max_idx:
            axial_at_max = axial_array[max_idx]
            moment_at_max = moment_array[max_idx]
            axial_at_min = axial_array[min_idx]
            moment_at_min = moment_array[min_idx]
        else:
            show_forces = False

        # MAX marker
        worker_ax.plot(
            max_xy[0], max_xy[1], 'D', ms=16, color='#DC143C',
            markeredgecolor='white', markeredgewidth=2, zorder=10,
        )
        if show_forces:
            max_text = (f'MAX: {max_val:+.2f}\n@ ({max_xy[0]:.2f}, {max_xy[1]:.2f})'
                        f'\nN = {axial_at_max:+.2f} kN/m\nM = {moment_at_max:+.2f} kN·m/m')
        else:
            max_text = f'MAX: {max_val:+.2f}\n@ ({max_xy[0]:.2f}, {max_xy[1]:.2f})'

        worker_ax.annotate(
            max_text, xy=max_xy, xytext=(max_xy[0], max_xy[1] + offset),
            fontsize=10, fontweight='bold', color='#DC143C', ha='center', va='bottom',
            bbox=dict(boxstyle='round,pad=0.6', fc='white', ec='#DC143C', lw=2, alpha=0.95),
            arrowprops=dict(arrowstyle='->,head_width=0.3,head_length=0.4', color='#DC143C', lw=2),
        )

        # MIN marker
        worker_ax.plot(
            min_xy[0], min_xy[1], 'D', ms=16, color='#1E90FF',
            markeredgecolor='white', markeredgewidth=2, zorder=10,
        )
        if show_forces:
            min_text = (f'MIN: {min_val:+.2f}\n@ ({min_xy[0]:.2f}, {min_xy[1]:.2f})'
                        f'\nN = {axial_at_min:+.2f} kN/m\nM = {moment_at_min:+.2f} kN·m/m')
        else:
            min_text = f'MIN: {min_val:+.2f}\n@ ({min_xy[0]:.2f}, {min_xy[1]:.2f})'

        worker_ax.annotate(
            min_text, xy=min_xy, xytext=(min_xy[0], min_xy[1] - offset),
            fontsize=10, fontweight='bold', color='#1E90FF', ha='center', va='top',
            bbox=dict(boxstyle='round,pad=0.6', fc='white', ec='#1E90FF', lw=2, alpha=0.95),
            arrowprops=dict(arrowstyle='->,head_width=0.3,head_length=0.4', color='#1E90FF', lw=2),
        )

        # Method badge
        method_label = f"Method: {contour_method.replace('-', ' ').title()}"
        worker_ax.text(
            0.02, 0.02, method_label, transform=worker_ax.transAxes, fontsize=9,
            fontweight='bold', color='white', alpha=0.9, va='bottom',
            bbox=dict(boxstyle='round,pad=0.5', fc='black', ec='gray', lw=1.5, alpha=0.8),
        )

        # Colorbar
        cbar = worker_fig.colorbar(
            pc, ax=worker_ax, shrink=0.85, pad=0.05,
            orientation='horizontal', location='bottom',
            ticks=np.linspace(vmin, vmax, 11),
        )
        cbar.set_label(display_name, fontsize=13, fontweight='bold', color='black')
        cbar.ax.tick_params(labelsize=10, labelrotation=0)
        cbar.outline.set_linewidth(1.5)

        if 0 not in cbar.get_ticks():
            ticks = list(cbar.get_ticks()) + [0]
            ticks.sort()
            cbar.set_ticks(ticks)

        # Axes styling
        worker_ax.set_aspect('equal')
        worker_ax.set_xlabel('X Coordinate (m)', fontsize=12, fontweight='bold', color='#333333')
        worker_ax.set_ylabel('Y Coordinate (m)', fontsize=12, fontweight='bold', color='#333333')

        title_str = f'{load_name} - {display_name}'
        if title_suffix:
            title_str += f' | {title_suffix}'
        worker_ax.set_title(title_str, fontsize=15, fontweight='bold', pad=20, color='#2C3E50')

        if show_mesh:
            worker_ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.3, color='gray')
        else:
            worker_ax.grid(False)

        # Save
        worker_fig.tight_layout()
        output_path = os.path.join(
            output_folder,
            f"contour_{safe_filename(force_col)}_{safe_filename(title_suffix)}.png",
        )
        worker_fig.savefig(output_path, dpi=PLOT_DPI_SAVE, bbox_inches='tight', facecolor='white')

        return {'status': 'ok', 'path': output_path}

    except Exception as e:
        col_name = task[6] if len(task) > 6 else 'unknown'
        return {'status': 'error', 'task': col_name, 'error': str(e)}

