"""
CLI entry point for FEA Rebar Analysis & Contour Plot Generator.
Calculates required reinforcement from FEM moments and plots contour maps.
"""

import os
import sys
import argparse
import fnmatch
import numpy as np
from datetime import datetime
from tqdm import tqdm
from multiprocessing import Pool, cpu_count

from .config import (
    DEFAULT_THICKNESS, ALL_METHODS, OUTPUT_FOLDER,
)
from .math_utils import safe_filename
from .combination import parse_combination_file, validate_combinations
from .io_utils import load_csv_inputs, build_coord_dict, resolve_input_files
from .mesh import MeshTopology
from .values import ValueMapper
from .rebar import (
    DEFAULT_FC, DEFAULT_FY, DEFAULT_COVER, PHI_FLEXURE,
    AVAILABLE_DIAMETERS,
    calc_effective_depth, calc_as_required,
    calc_spacing_from_diameter, calc_diameter_from_spacing,
    check_spacing_limits,
)
from .plotting_rebar import init_rebar_worker, generate_rebar_plot_worker


# =============================================================================
# Rebar case definitions
# =============================================================================
REBAR_CASES = [
    # (moment_col, direction, layer, label)
    ('Mxx (kN·m/m)', 'x', 'bottom', 'Mxx_Bottom_X'),  # Mxx > 0 → bottom
    ('Mxx (kN·m/m)', 'x', 'top',    'Mxx_Top_X'),      # Mxx < 0 → top
    ('Myy (kN·m/m)', 'y', 'bottom', 'Myy_Bottom_Y'),   # Myy > 0 → bottom
    ('Myy (kN·m/m)', 'y', 'top',    'Myy_Top_Y'),      # Myy < 0 → top
]


def _build_rebar_tasks(
    x, y, triangles, polygons, centroids,
    moment_array, h_mm, cover, fc, fy,
    diameter_input, spacing_input, mode,
    direction, layer, case_label,
    load_name, output_folder, method, show_mesh, theme,
):
    """
    Build plotting task tuples for one rebar case.
    Returns list of task tuples (As plot + spacing/diameter plot).
    """
    tasks = []

    # Separate positive (bottom) and negative (top) moments
    if layer == 'bottom':
        # Positive moment → bottom rebar
        Mu = np.where(moment_array > 0, moment_array, 0.0)
    else:
        # Negative moment → top rebar (use absolute value)
        Mu = np.where(moment_array < 0, np.abs(moment_array), 0.0)

    # Effective depth
    D_for_depth = diameter_input if diameter_input else 16.0  # assume D16 for depth calc in Mode B
    d_eff = calc_effective_depth(h_mm, cover, D_for_depth, direction, layer)

    # Calculate As_required
    As = calc_as_required(Mu, fc, fy, d_eff, PHI_FLEXURE)

    # Skip if all zeros
    if np.all((As == 0) | np.isnan(As)):
        return tasks

    layer_label = "Tulangan Bawah" if layer == 'bottom' else "Tulangan Atas"
    dir_label = "Arah X" if direction == 'x' else "Arah Y"

    # --- Task 1: As_required plot ---
    tasks.append((
        x, y, As, triangles, polygons, centroids,
        f'As Required — {layer_label} ({dir_label})',
        'mm²/m',
        f'(Method: {method.replace("-", " ").title()} | d_eff = {d_eff:.0f} mm)',
        load_name, output_folder, method, show_mesh, theme,
        f'As_{case_label}',
    ))

    # --- Task 2: Spacing or Diameter plot ---
    if mode == 'spacing':
        # Mode A: given diameter, output spacing
        spacing = calc_spacing_from_diameter(As, diameter_input)
        spacing = check_spacing_limits(spacing, h_mm, diameter_input)
        tasks.append((
            x, y, spacing, triangles, polygons, centroids,
            f'Spasi Tulangan D{int(diameter_input)} — {layer_label} ({dir_label})',
            'mm',
            f'(Method: {method.replace("-", " ").title()} | d_eff = {d_eff:.0f} mm)',
            load_name, output_folder, method, show_mesh, theme,
            f'spacing_D{int(diameter_input)}_{case_label}',
        ))
    else:
        # Mode B: given spacing, output diameter
        D_selected = calc_diameter_from_spacing(As, spacing_input)
        tasks.append((
            x, y, D_selected, triangles, polygons, centroids,
            f'Diameter Tulangan s={int(spacing_input)}mm — {layer_label} ({dir_label})',
            'mm',
            f'(Method: {method.replace("-", " ").title()} | d_eff = {d_eff:.0f} mm)',
            load_name, output_folder, method, show_mesh, theme,
            f'diameter_s{int(spacing_input)}_{case_label}',
        ))

    return tasks


def main():
    parser = argparse.ArgumentParser(
        description='FEA Rebar Analysis & Contour Plot Generator'
    )
    parser.add_argument('--kordinat', type=str, help='Path to coordinate CSV')
    parser.add_argument('--connectivity', type=str, help='Path to connectivity CSV')
    parser.add_argument('--gaya', type=str, help='Path to force/moment CSV')
    parser.add_argument('--thickness', type=float, default=DEFAULT_THICKNESS,
                        help=f'Plate thickness in meters (default: {DEFAULT_THICKNESS})')
    parser.add_argument('--fc', type=float, default=DEFAULT_FC,
                        help=f"Concrete compressive strength in MPa (default: {DEFAULT_FC})")
    parser.add_argument('--fy', type=float, default=DEFAULT_FY,
                        help=f"Steel yield strength in MPa (default: {DEFAULT_FY})")
    parser.add_argument('--cover', type=float, default=DEFAULT_COVER,
                        help=f"Clear concrete cover in mm (default: {DEFAULT_COVER})")
    parser.add_argument('--diameter', type=float, default=None,
                        help='Bar diameter in mm (Mode A: output = spacing)')
    parser.add_argument('--spacing', type=float, default=150,
                        help='Bar spacing in mm (Mode B: output = diameter, default: 150)')
    parser.add_argument('--output', type=str, default=OUTPUT_FOLDER,
                        help=f'Output base folder (default: {OUTPUT_FOLDER})')
    parser.add_argument('--no-mesh', action='store_true', help='Hide mesh wireframe')
    parser.add_argument('--method', type=str,
                        choices=['average-nodal', 'element-nodal', 'element-center', 'all'],
                        default='average-nodal',
                        help='Contour method (default: average-nodal)')
    parser.add_argument('--comb', type=str, default='',
                        help='Path to load combination CSV')
    parser.add_argument('--comb-select', type=str, nargs='*', default=['*'],
                        help='Filter combination names by wildcard pattern (default: * = all)')
    parser.add_argument('--theme', type=str, choices=['light', 'dark'], default='light',
                        help='Plot styling theme (default: light)')
    args = parser.parse_args()

    show_mesh = not args.no_mesh
    h_mm = args.thickness * 1000  # m → mm

    # Determine mode
    if args.diameter is not None:
        mode = 'spacing'
        diameter_input = args.diameter
        spacing_input = None
        mode_desc = f"Mode A: Input D{int(diameter_input)} -> Output Spasi"
    else:
        mode = 'diameter'
        diameter_input = None
        spacing_input = args.spacing
        mode_desc = f"Mode B: Input s={int(spacing_input)}mm -> Output Diameter"

    # Timestamped output
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    timestamp_output = os.path.join(args.output, f"rebar_{timestamp}")
    os.makedirs(timestamp_output, exist_ok=True)

    print("=" * 60)
    print("FEA REBAR ANALYSIS & CONTOUR PLOT GENERATOR")
    print("=" * 60)
    print(f"Output Directory: {timestamp_output}")
    print(f"Plate Thickness:  {h_mm:.0f} mm")
    print(f"f'c = {args.fc} MPa | fy = {args.fy} MPa | Cover = {args.cover} mm")
    print(f"{mode_desc}")

    # --- Resolve and load input files ---
    k_file, c_file, g_file = resolve_input_files(
        args.kordinat, args.connectivity, args.gaya,
    )
    df_kordinat, df_conn, df_gaya = load_csv_inputs(k_file, c_file, g_file)
    coord_dict = build_coord_dict(df_kordinat)

    load_cases = [lc for lc in df_gaya['Load'].dropna().unique() if str(lc).strip()]
    methods_to_run = ALL_METHODS if args.method == 'all' else [args.method]

    # --- Parse combinations ---
    combos = []
    use_combos = False
    if args.comb and os.path.exists(args.comb):
        combos = parse_combination_file(args.comb)
        use_combos = True
        print(f"Combinations loaded: {len(combos)}")
        if args.comb_select != ['*']:
            print(f"Combination filter: {args.comb_select}")

    if use_combos:
        print(f"Mode: KOMBINASI BEBAN (load case tunggal diabaikan)")
    else:
        print(f"Mode: LOAD CASE TUNGGAL (beban dianggap sudah ultimate)")

    print(f"Methods to run: {len(methods_to_run)} | Load Cases: {len(load_cases)}")

    # --- Envelope accumulators ---
    # Structure: envelope_as[case_label] = running_max_array
    envelope_data = {}

    for method in methods_to_run:
        print(f"\nProcessing Method: {method.upper()}")
        method_output = (
            os.path.join(timestamp_output, f"Method_{safe_filename(method)}")
            if args.method == 'all'
            else timestamp_output
        )

        # --- Build MeshTopology + ValueMappers ---
        print("  [1/3] Building Value Mappers...")
        mesh = MeshTopology(df_conn, coord_dict, method)
        value_mapper_cache = {}

        for lc in load_cases:
            df_lc = df_gaya[df_gaya['Load'] == lc].copy()
            value_mapper_cache[lc] = ValueMapper(df_lc, mesh)

        # --- Geometry references ---
        x, y, tris = (None, None, None) if method == 'element-center' else (mesh.x, mesh.y, mesh.triangles)
        polys, cents = (mesh.polygons, mesh.centroids) if method == 'element-center' else (None, None)

        # --- Build Task Pool ---
        print("  [2/3] Building Rebar Task Pool...")
        all_tasks = []

        def process_moment_source(source_name, moment_arrays, folder_path):
            """Process one moment source (load case or combination) into plot tasks."""
            tasks = []
            for moment_col, direction, layer, case_label in REBAR_CASES:
                if moment_col not in moment_arrays:
                    continue
                m_arr = moment_arrays[moment_col]

                case_tasks = _build_rebar_tasks(
                    x, y, tris, polys, cents,
                    m_arr, h_mm, args.cover, args.fc, args.fy,
                    diameter_input, spacing_input, mode,
                    direction, layer, case_label,
                    source_name, folder_path, method, show_mesh, args.theme,
                )
                tasks.extend(case_tasks)

                # --- Envelope accumulation ---
                # Extract the As array (first task is always As)
                if layer == 'bottom':
                    Mu = np.where(m_arr > 0, m_arr, 0.0)
                else:
                    Mu = np.where(m_arr < 0, np.abs(m_arr), 0.0)

                D_for_depth = diameter_input if diameter_input else 16.0
                d_eff = calc_effective_depth(h_mm, args.cover, D_for_depth, direction, layer)
                As = calc_as_required(Mu, args.fc, args.fy, d_eff, PHI_FLEXURE)

                # Update envelope (element-wise maximum)
                if case_label not in envelope_data:
                    envelope_data[case_label] = As.copy()
                else:
                    envelope_data[case_label] = np.fmax(envelope_data[case_label], As)

            return tasks

        if not use_combos:
            # --- Mode: Load Case Tunggal (pilecap) ---
            for lc in load_cases:
                vm = value_mapper_cache[lc]
                lc_folder = os.path.join(method_output, f"Load_{safe_filename(lc)}")
                os.makedirs(lc_folder, exist_ok=True)

                moment_arrays = {}
                for moment_col, _, _, _ in REBAR_CASES:
                    arr = vm.get_z_array(moment_col)
                    if len(arr) > 0:
                        moment_arrays[moment_col] = arr

                all_tasks.extend(process_moment_source(lc, moment_arrays, lc_folder))

        else:
            # --- Mode: Kombinasi Beban ---
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

            # Apply --comb-select filter
            if args.comb_select != ['*']:
                filtered = []
                for combo in valid_combos:
                    for pattern in args.comb_select:
                        if fnmatch.fnmatch(combo['name'], pattern):
                            filtered.append(combo)
                            break
                print(f"  Filtered: {len(filtered)} / {len(valid_combos)} combinations")
                valid_combos = filtered

            for combo in valid_combos:
                lc_factors = combo['lc_factors']
                combo_name = combo['name']
                combo_folder = os.path.join(
                    method_output, f"Combination_{safe_filename(combo_name)}"
                )
                os.makedirs(combo_folder, exist_ok=True)

                # Superposition: combine moment arrays
                moment_arrays = {}
                for moment_col, _, _, _ in REBAR_CASES:
                    first_arr = value_mapper_cache[lc_factors[0][0]].get_z_array(moment_col)
                    z_comb = np.zeros_like(first_arr)
                    for lc_a, fac in lc_factors:
                        z_comb += fac * value_mapper_cache[lc_a].get_z_array(moment_col)
                    moment_arrays[moment_col] = z_comb

                all_tasks.extend(
                    process_moment_source(f"Comb: {combo_name}", moment_arrays, combo_folder)
                )

        # --- Envelope tasks ---
        if envelope_data:
            envelope_folder = os.path.join(method_output, "Envelope_Rebar")
            os.makedirs(envelope_folder, exist_ok=True)

            for case_label, As_env in envelope_data.items():
                # Find direction/layer info from case_label
                for moment_col, direction, layer, cl in REBAR_CASES:
                    if cl == case_label:
                        break

                layer_label = "Tulangan Bawah" if layer == 'bottom' else "Tulangan Atas"
                dir_label = "Arah X" if direction == 'x' else "Arah Y"
                D_for_depth = diameter_input if diameter_input else 16.0
                d_eff = calc_effective_depth(h_mm, args.cover, D_for_depth, direction, layer)

                # As envelope plot
                all_tasks.append((
                    x, y, As_env, tris, polys, cents,
                    f'ENVELOPE As — {layer_label} ({dir_label})',
                    'mm²/m',
                    f'(Maximum dari seluruh kasus | d_eff = {d_eff:.0f} mm)',
                    'ENVELOPE', envelope_folder, method, show_mesh, args.theme,
                    f'ENVELOPE_As_{case_label}',
                ))

                # Spacing/Diameter envelope plot
                if mode == 'spacing':
                    spacing_env = calc_spacing_from_diameter(As_env, diameter_input)
                    spacing_env = check_spacing_limits(spacing_env, h_mm, diameter_input)
                    all_tasks.append((
                        x, y, spacing_env, tris, polys, cents,
                        f'ENVELOPE Spasi D{int(diameter_input)} — {layer_label} ({dir_label})',
                        'mm',
                        f'(Maximum dari seluruh kasus | d_eff = {d_eff:.0f} mm)',
                        'ENVELOPE', envelope_folder, method, show_mesh, args.theme,
                        f'ENVELOPE_spacing_D{int(diameter_input)}_{case_label}',
                    ))
                else:
                    D_env = calc_diameter_from_spacing(As_env, spacing_input)
                    all_tasks.append((
                        x, y, D_env, tris, polys, cents,
                        f'ENVELOPE Diameter s={int(spacing_input)}mm — {layer_label} ({dir_label})',
                        'mm',
                        f'(Maximum dari seluruh kasus | d_eff = {d_eff:.0f} mm)',
                        'ENVELOPE', envelope_folder, method, show_mesh, args.theme,
                        f'ENVELOPE_diameter_s{int(spacing_input)}_{case_label}',
                    ))

        # --- Parallel Plotting ---
        print(f"  [3/3] Plotting {len(all_tasks)} rebar plots using {cpu_count()} cores...")
        num_cores = min(cpu_count(), len(all_tasks)) if all_tasks else 0
        generated_files = []
        errors = []

        if num_cores > 0:
            with Pool(processes=num_cores, initializer=init_rebar_worker) as pool:
                for result in tqdm(
                    pool.imap_unordered(generate_rebar_plot_worker, all_tasks, chunksize=10),
                    total=len(all_tasks),
                    desc="Rebar Plots",
                ):
                    if result['status'] == 'ok':
                        generated_files.append(result['path'])
                    elif result['status'] == 'error':
                        errors.append(result)

        print(f"  [OK] Successfully generated {len(generated_files)} rebar plots.")
        if errors:
            print(f"  [WARN] {len(errors)} plots failed:")
            for err in errors[:5]:
                print(f"    - {err.get('task', '?')}: {err.get('error', '?')}")

    print("\n[SUCCESS] All rebar analysis plots generated.")
    return 0


def entry_point():
    """Console script entry point (called by pyproject.toml [project.scripts])."""
    import sys
    from multiprocessing import freeze_support
    freeze_support()
    sys.exit(main())
