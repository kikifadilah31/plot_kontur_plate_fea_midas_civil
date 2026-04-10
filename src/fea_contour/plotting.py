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

import threading
thread_local = threading.local()

# =============================================================================
# GLOBAL WORKER VARIABLES (For Figure Recycling)
# =============================================================================
# Deprecated globals (kept for compatibility if needed elsewhere, but not used by worker)
worker_fig = None
worker_ax = None

def init_worker():
    """Initializer for Pool: Sets up the backend."""
    plt.switch_backend('Agg')

def generate_plot_worker(task):
    """
    Hyper-optimized plotting function with figure recycling and error handling.

    Recycles a THREAD-LOCAL figure to avoid creating new figures per plot,
    allowing safe usage with ThreadPoolExecutor without race conditions.
    Returns dict with status, path, and error info.
    """
    try:
        # Guarantee thread-local figure exists
        if not hasattr(thread_local, "fig"):
            plt.switch_backend('Agg')
            thread_local.fig, thread_local.ax = plt.subplots(figsize=PLOT_FIGSIZE, dpi=PLOT_DPI_WORKER)
        
        worker_fig = thread_local.fig
        worker_ax = thread_local.ax
        (x, y, z, triangles, polygons, centroids,
         force_col, display_name, title_suffix, load_name,
         output_folder, contour_method, show_mesh,
         axial_array, moment_array, theme) = task

        is_dark = theme == 'dark'
        bg_col = '#1E1E1E' if is_dark else '#FFFFFF'
        text_col = '#E0E0E0' if is_dark else '#2C3E50'
        grid_col = '#333333' if is_dark else '#E5E5E5'

        # Clear entire figure to remove old colorbars
        worker_fig.clear()
        worker_fig.patch.set_facecolor(bg_col)
        
        worker_ax = worker_fig.add_subplot(111)
        worker_ax.set_facecolor(bg_col)

        # Dynamic figure resizing based on data geometry to eliminate vertical dead space
        if len(x) > 0 and len(y) > 0:
            x_range = np.max(x) - np.min(x)
            y_range = np.max(y) - np.min(y)
            if x_range > 0 and y_range > 0:
                data_ratio = x_range / y_range
                fig_w = 14.0
                # Calculate required height and clamp
                fig_h = (fig_w - 3.0) / data_ratio + 2.5
                fig_h = max(5.0, min(14.0, fig_h))
                worker_fig.set_size_inches(fig_w, fig_h, forward=True)

        z_min, z_max = np.min(z), np.max(z)
        z_abs_max = max(abs(z_min), abs(z_max))
        vmin, vmax = -z_abs_max, z_abs_max
        if vmin == vmax:
            vmin, vmax = -1, 1

        norm = plt.Normalize(vmin=vmin, vmax=vmax)
        levels = np.linspace(vmin, vmax, CONTOUR_LEVELS + 1)
        cmap_name = 'seismic' if is_dark else PLOT_CMAP
        cmap = plt.get_cmap(cmap_name, CONTOUR_LEVELS)

        max_idx, min_idx = np.argmax(z), np.argmin(z)
        max_val, min_val = z[max_idx], z[min_idx]

        # --- Draw contour ---
        if contour_method in ('average-nodal', 'element-nodal'):
            if contour_method == 'average-nodal':
                pc = worker_ax.tricontourf(
                    x, y, triangles, z,
                    levels=levels, cmap=cmap, norm=norm, extend='both',
                )
                # Isolines (thin black/white)
                isoline_col = 'black' if is_dark else 'white'
                worker_ax.tricontour(x, y, triangles, z, levels=levels, 
                                     colors=isoline_col, linewidths=0.2, alpha=0.5)
                # Zero-line (thinner 1.0)
                worker_ax.tricontour(x, y, triangles, z, levels=[0], 
                                     colors='black' if not is_dark else 'white', 
                                     linewidths=1.0, linestyles='--')
            else:
                pc = worker_ax.tripcolor(
                    x, y, triangles, z,
                    cmap=cmap, norm=norm, shading='gouraud',
                )

            if show_mesh:
                lw = 0.2 if contour_method == 'average-nodal' else 0.3
                alpha = 0.5 if contour_method == 'average-nodal' else 0.8
                worker_ax.triplot(x, y, triangles, color='black' if not is_dark else 'white', 
                                  linewidth=lw, alpha=alpha)

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
        y_range_ax = worker_ax.get_ylim()[1] - worker_ax.get_ylim()[0]
        offset = y_range_ax * 0.05
        
        # Smart HA positioning to prevent overlapping at borders
        x_range_data = np.max(x) - np.min(x)
        x_min_data = np.min(x)
        ha_max = 'right' if max_xy[0] > x_min_data + 0.8*x_range_data else 'left' if max_xy[0] < x_min_data + 0.2*x_range_data else 'center'
        ha_min = 'right' if min_xy[0] > x_min_data + 0.8*x_range_data else 'left' if min_xy[0] < x_min_data + 0.2*x_range_data else 'center'

        show_forces = axial_array is not None and moment_array is not None
        if show_forces and len(axial_array) > max_idx and len(moment_array) > max_idx:
            axial_at_max = axial_array[max_idx]
            moment_at_max = moment_array[max_idx]
            axial_at_min = axial_array[min_idx]
            moment_at_min = moment_array[min_idx]
        else:
            show_forces = False

        bbox_style = dict(boxstyle='round,pad=0.5', fc=bg_col, ec=text_col, lw=1, alpha=0.9)
        arrow_style = dict(arrowstyle='-|>,head_width=0.4,head_length=0.6', 
                           color=text_col, lw=1.5, connectionstyle='arc3,rad=0.3')

        # MAX marker
        worker_ax.plot(
            max_xy[0], max_xy[1], 'D', ms=12, color='#DC143C',
            markeredgecolor='white', markeredgewidth=1.5, zorder=10,
        )
        if show_forces:
            max_text = (f'MAX: {max_val:+.2f}\n@ ({max_xy[0]:.2f}, {max_xy[1]:.2f})'
                        f'\nN = {axial_at_max:+.2f} kN/m\nM = {moment_at_max:+.2f} kN·m/m')
        else:
            max_text = f'MAX: {max_val:+.2f}\n@ ({max_xy[0]:.2f}, {max_xy[1]:.2f})'

        worker_ax.annotate(
            max_text, xy=max_xy, xytext=(max_xy[0], max_xy[1] + offset),
            fontsize=10, fontweight='bold', color=text_col, ha=ha_max, va='bottom',
            bbox=bbox_style, arrowprops=arrow_style, zorder=11,
        )

        # MIN marker
        worker_ax.plot(
            min_xy[0], min_xy[1], 'D', ms=12, color='#1E90FF',
            markeredgecolor='white', markeredgewidth=1.5, zorder=10,
        )
        if show_forces:
            min_text = (f'MIN: {min_val:+.2f}\n@ ({min_xy[0]:.2f}, {min_xy[1]:.2f})'
                        f'\nN = {axial_at_min:+.2f} kN/m\nM = {moment_at_min:+.2f} kN·m/m')
        else:
            min_text = f'MIN: {min_val:+.2f}\n@ ({min_xy[0]:.2f}, {min_xy[1]:.2f})'

        worker_ax.annotate(
            min_text, xy=min_xy, xytext=(min_xy[0], min_xy[1] - offset),
            fontsize=10, fontweight='bold', color=text_col, ha=ha_min, va='top',
            bbox=bbox_style, arrowprops=arrow_style, zorder=11,
        )

        # Watermark at the bottom left of the entire FIGURE (outside the plot box)
        worker_fig.text(
            0.01, 0.02, f'FEA Contour Plotter | {theme.upper()} THEME',
            color=text_col, alpha=0.4, fontsize=9, fontweight='bold',
        )

        # Axes styling
        worker_ax.set_aspect('equal')
        worker_ax.set_xlabel('X Coordinate (m)', fontsize=12, fontweight='bold', color=text_col)
        worker_ax.set_ylabel('Y Coordinate (m)', fontsize=12, fontweight='bold', color=text_col)

        title_str = f'{load_name} - {display_name}'
        if title_suffix:
            title_str += f' | {title_suffix}'
        title_str += f'\n(Method: {contour_method.replace("-", " ").title()})'
        worker_ax.set_title(title_str, fontsize=16, fontweight='bold', pad=25, color=text_col)

        if show_mesh:
            worker_ax.grid(True, linestyle=':', linewidth=1.0, alpha=0.5, color=grid_col)
        else:
            worker_ax.grid(False)

        for spine in worker_ax.spines.values():
            spine.set_color(text_col)
        worker_ax.tick_params(colors=text_col)

        # Dynamic Colorbar linked exactly to the axes height to avoid overlapping
        from mpl_toolkits.axes_grid1 import make_axes_locatable
        divider = make_axes_locatable(worker_ax)
        cax = divider.append_axes("right", size="2%", pad=0.4)
        cbar = worker_fig.colorbar(pc, cax=cax, orientation='vertical')
        
        cax.set_title('TENSION (+)\n(Tarik)\n', fontsize=10, color=text_col, fontweight='bold')
        cax.set_xlabel('COMPRESSION (-)\n(Tekan)', fontsize=10, color=text_col, fontweight='bold', labelpad=15)
                 
        cax.tick_params(colors=text_col, labelsize=9)
        cbar.outline.set_edgecolor(text_col)
        cbar.set_label(display_name, fontsize=11, fontweight='bold', color=text_col)

        if 0 not in cbar.get_ticks():
            ticks = list(cbar.get_ticks()) + [0]
            ticks.sort()
            cbar.set_ticks(ticks)

        # Save with tight layout
        try:
            worker_fig.tight_layout()
        except:
            pass # ignore tight layout warnings if any
            
        output_path = os.path.join(
            output_folder,
            f"contour_{safe_filename(force_col)}_{safe_filename(title_suffix)}.png",
        )
        worker_fig.savefig(output_path, dpi=PLOT_DPI_SAVE, bbox_inches='tight', facecolor=bg_col)

        return {'status': 'ok', 'path': output_path}

    except Exception as e:
        col_name = task[6] if len(task) > 6 else 'unknown'
        return {'status': 'error', 'task': col_name, 'error': str(e)}

