"""
CLI entry point for FEA Contour Plot Generator.
Orchestrates mesh building, value mapping, and parallel plotting.
"""

import os
import sys
import argparse
import numpy as np
from datetime import datetime
from tqdm import tqdm
from multiprocessing import Pool, cpu_count

from .config import (
    DEFAULT_THICKNESS, ALL_METHODS, PLOTTABLE_COLUMNS,
    STRESS_PAIRS, OUTPUT_FOLDER,
)
from .math_utils import calculate_stress_vectorized, safe_filename
from .combination import parse_combination_file, validate_combinations
from .io_utils import load_csv_inputs, build_coord_dict, resolve_input_files
from .mesh import MeshTopology
from .values import ValueMapper
from .plotting import init_worker, generate_plot_worker


def main():
    parser = argparse.ArgumentParser(description='FEA 2D Contour Plot Generator')
    parser.add_argument('--kordinat', type=str, help='Path to coordinate CSV')
    parser.add_argument('--connectivity', type=str, help='Path to connectivity CSV')
    parser.add_argument('--gaya', type=str, help='Path to force/moment CSV')
    parser.add_argument('--thickness', type=float, default=DEFAULT_THICKNESS,
                        help=f'Plate thickness in meters (default: {DEFAULT_THICKNESS})')
    parser.add_argument('--output', type=str, default=OUTPUT_FOLDER,
                        help=f'Output base folder (default: {OUTPUT_FOLDER})')
    parser.add_argument('--no-mesh', action='store_true', help='Hide mesh wireframe')
    parser.add_argument('--method', type=str,
                        choices=['average-nodal', 'element-nodal', 'element-center', 'all'],
                        default='average-nodal',
                        help='Contour method (default: average-nodal)')
    parser.add_argument('--comb', type=str, default='',
                        help='Path to load combination CSV')
    parser.add_argument('--theme', type=str, choices=['light', 'dark'], default='light',
                        help='Plot styling theme (default: light)')
    args = parser.parse_args()

    show_mesh = not args.no_mesh
    thickness = args.thickness

    # Timestamped output
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    timestamp_output = os.path.join(args.output, timestamp)
    os.makedirs(timestamp_output, exist_ok=True)

    print("=" * 60)
    print("FEA CONTOUR PLOT GENERATOR (HYPER-OPTIMIZED)")
    print("=" * 60)
    print(f"Output Directory: {timestamp_output}")
    print(f"Plate Thickness:  {thickness * 1000:.0f} mm")

    # Resolve and load input files
    k_file, c_file, g_file = resolve_input_files(
        args.kordinat, args.connectivity, args.gaya,
    )
    df_kordinat, df_conn, df_gaya = load_csv_inputs(k_file, c_file, g_file)
    coord_dict = build_coord_dict(df_kordinat)

    load_cases = [lc for lc in df_gaya['Load'].dropna().unique() if str(lc).strip()]
    methods_to_run = ALL_METHODS if args.method == 'all' else [args.method]
    print(f"Methods to run: {len(methods_to_run)} | Load Cases: {len(load_cases)}")

    # Parse combinations
    combos = []
    if args.comb and os.path.exists(args.comb):
        combos = parse_combination_file(args.comb)
        print(f"Combinations loaded: {len(combos)}")

    for method in methods_to_run:
        print(f"\nProcessing Method: {method.upper()}")
        method_output = (
            os.path.join(timestamp_output, f"Method_{safe_filename(method)}")
            if args.method == 'all'
            else timestamp_output
        )

        # =====================================================================
        # [1/3] Build MeshTopology ONCE per method + ValueMappers per LC
        # FIX: MeshTopology was previously rebuilt per load case (identical work)
        # =====================================================================
        print("  [1/3] Building Value Mappers (Heavy Computation)...")
        mesh = MeshTopology(df_conn, coord_dict, method)  # BUILD ONCE!
        value_mapper_cache = {}

        for lc in load_cases:
            df_lc = df_gaya[df_gaya['Load'] == lc].copy()

            # Calculate stresses using shared formula
            if 'Fxx (kN/m)' in df_lc.columns and 'Mxx (kN·m/m)' in df_lc.columns:
                top, bot = calculate_stress_vectorized(
                    df_lc['Fxx (kN/m)'].values,
                    df_lc['Mxx (kN·m/m)'].values,
                    thickness,
                )
                df_lc.loc[:, 'Sig-xx_Top (kPa)'] = top
                df_lc.loc[:, 'Sig-xx_Bottom (kPa)'] = bot

            if 'Fyy (kN/m)' in df_lc.columns and 'Myy (kN·m/m)' in df_lc.columns:
                top, bot = calculate_stress_vectorized(
                    df_lc['Fyy (kN/m)'].values,
                    df_lc['Myy (kN·m/m)'].values,
                    thickness,
                )
                df_lc.loc[:, 'Sig-yy_Top (kPa)'] = top
                df_lc.loc[:, 'Sig-yy_Bottom (kPa)'] = bot

            value_mapper_cache[lc] = ValueMapper(df_lc, mesh)

        # =====================================================================
        # [2/3] Build Global Task Pool
        # FIX: Simplified column detection (was 3 identical if-elif branches)
        # =====================================================================
        print("  [2/3] Building Global Task Pool (Fast Cache Lookup)...")
        all_tasks = []

        first_vm = value_mapper_cache[load_cases[0]]
        cols_to_plot = list(first_vm.cached_z.keys()) if first_vm.cached_z else []
        cols_to_plot = [c for c in cols_to_plot if c in PLOTTABLE_COLUMNS]

        # --- Load case tasks ---
        for lc in load_cases:
            vm = value_mapper_cache[lc]
            load_folder = os.path.join(method_output, f"Load_{safe_filename(lc)}")
            os.makedirs(load_folder, exist_ok=True)

            x, y, tris = (None, None, None) if method == 'element-center' else (mesh.x, mesh.y, mesh.triangles)
            polys, cents = (mesh.polygons, mesh.centroids) if method == 'element-center' else (None, None)

            for col in cols_to_plot:
                z = vm.get_z_array(col)
                if len(z) > 0 and not np.all(z == 0):
                    axial_arr = moment_arr = None
                    if col in STRESS_PAIRS:
                        f_col, m_col = STRESS_PAIRS[col]
                        axial_arr = vm.get_z_array(f_col)
                        moment_arr = vm.get_z_array(m_col)

                    suf = "(Top Fiber)" if "Top" in col else "(Bottom Fiber)" if "Bottom" in col else ""
                    all_tasks.append((
                        x, y, z, tris, polys, cents,
                        col, col, suf, lc, load_folder,
                        method, show_mesh, axial_arr, moment_arr, args.theme,
                    ))

        # --- Combination tasks ---
        _, matched_map = validate_combinations(combos, set(load_cases))
        valid_combos = []
        for combo in combos:
            is_valid = True
            resolved = []
            for lc, fac in combo['lc_factors']:
                actual = matched_map.get(lc, lc)
                if actual in value_mapper_cache:
                    resolved.append((actual, fac))
                else:
                    is_valid = False
                    break
            if is_valid and resolved:
                valid_combos.append({'name': combo['name'], 'lc_factors': resolved})

        for combo in valid_combos:
            lc_factors = combo['lc_factors']
            combo_name = combo['name']
            combo_folder = os.path.join(method_output, f"Combination_{safe_filename(combo_name)}")
            os.makedirs(combo_folder, exist_ok=True)

            x_ref, y_ref, tris_ref = (None, None, None) if method == 'element-center' else (mesh.x, mesh.y, mesh.triangles)
            polys_ref, cents_ref = (mesh.polygons, mesh.centroids) if method == 'element-center' else (None, None)

            for col in cols_to_plot:
                first_lc_vm = value_mapper_cache[lc_factors[0][0]]
                z_comb = np.zeros(len(first_lc_vm.get_z_array(col)))
                for lc_a, fac in lc_factors:
                    z_comb += fac * value_mapper_cache[lc_a].get_z_array(col)

                if len(z_comb) > 0 and not np.all(z_comb == 0):
                    axial_comb = moment_comb = None
                    if col in STRESS_PAIRS:
                        f_col, m_col = STRESS_PAIRS[col]
                        axial_comb = np.zeros_like(z_comb)
                        moment_comb = np.zeros_like(z_comb)
                        for lc_a, fac in lc_factors:
                            vm_a = value_mapper_cache[lc_a]
                            axial_comb += fac * vm_a.get_z_array(f_col)
                            moment_comb += fac * vm_a.get_z_array(m_col)

                    suf = "(Top Fiber)" if "Top" in col else "(Bottom Fiber)" if "Bottom" in col else ""
                    all_tasks.append((
                        x_ref, y_ref, z_comb, tris_ref, polys_ref, cents_ref,
                        col, col, suf, f"Comb: {combo_name}", combo_folder,
                        method, show_mesh, axial_comb, moment_comb, args.theme,
                    ))

        # =====================================================================
        # [3/3] Parallel Plotting
        # =====================================================================
        print(f"  [3/3] Plotting {len(all_tasks)} plots using {cpu_count()} cores...")
        num_cores = min(cpu_count(), len(all_tasks))
        generated_files = []
        errors = []

        if num_cores > 0 and len(all_tasks) > 0:
            with Pool(processes=num_cores, initializer=init_worker) as pool:
                for result in tqdm(
                    pool.imap_unordered(generate_plot_worker, all_tasks, chunksize=20),
                    total=len(all_tasks),
                    desc="Plotting",
                ):
                    if result['status'] == 'ok':
                        generated_files.append(result['path'])
                    elif result['status'] == 'error':
                        errors.append(result)

        print(f"  [OK] Successfully generated {len(generated_files)} plots.")
        if errors:
            print(f"  [WARN] {len(errors)} plots failed:")
            for err in errors[:5]:
                print(f"    - {err.get('task', '?')}: {err.get('error', '?')}")

    print("\n[SUCCESS] All plots generated in the output folder.")
    return 0


def entry_point():
    """Console script entry point (called by pyproject.toml [project.scripts])."""
    import sys
    from multiprocessing import freeze_support
    freeze_support()
    sys.exit(main())
