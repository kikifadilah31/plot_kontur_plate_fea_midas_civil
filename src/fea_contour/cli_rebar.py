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

from . import __version__

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
    AVAILABLE_DIAMETERS, SHEAR_DIAMETERS,
    REBAR_CONFIG_TABLE,
    calc_effective_depth, calc_as_required,
    calc_spacing_from_diameter, calc_diameter_from_spacing,
    check_spacing_limits,
    calc_shear_Av_per_s, calc_shear_diameter,
    get_config_area, select_config_from_As,
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

# Shear reinforcement cases
# For Vxx: s_longitudinal = along X, s_transversal = along Y
# For Vyy: s_longitudinal = along Y, s_transversal = along X
SHEAR_CASES = [
    # (shear_col, direction, label)
    ('Vxx (kN/m)', 'x', 'Vxx_Shear_X'),
    ('Vyy (kN/m)', 'y', 'Vyy_Shear_Y'),
]


def _build_rebar_tasks(
    x, y, triangles, polygons, centroids,
    moment_array, h_mm, cover, fc, fy,
    diameter_input, spacing_input, mode,
    direction, layer, case_label,
    load_name, output_folder, method, show_mesh, theme,
    rebar_select_codes=None, config_code=None, config_area=None,
    show_annotation=True,
):
    """
    Build plotting task tuples for one rebar case.
    Returns list of task tuples (As plot + spacing/diameter plot).

    When rebar_select_codes is provided, Mode B uses custom config matching
    instead of standard calc_diameter_from_spacing.

    When config_code/config_area is provided, Mode A uses config area
    instead of single bar area for spacing calculation.
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

    # --- Task 1: As_required plot (always shown) ---
    tasks.append((
        x, y, As, triangles, polygons, centroids,
        f'As Required — {layer_label} ({dir_label})',
        'mm²/m',
        f'(Method: {method.replace("-", " ").title()} | f\'c = {fc} MPa | d_eff = {d_eff:.0f} mm)',
        load_name, output_folder, method, show_mesh, theme,
        f'As_{case_label}',
        None,  # config_labels (not applicable for As plot)
        show_annotation,
    ))

    # --- Task 2: Spacing or Diameter/Config plot ---
    if mode == 'spacing':
        # Mode A: given config code, output spacing
        if config_code and config_area:
            # Use config area (e.g. 2D25 = 982 mm²) for spacing calc
            spacing = np.full_like(As, np.inf)
            active = (As > 1e-6) & ~np.isnan(As)
            spacing[active] = config_area * 1000.0 / As[active]
            spacing = check_spacing_limits(spacing, h_mm, diameter_input)
            label_code = config_code
        else:
            spacing = calc_spacing_from_diameter(As, diameter_input)
            spacing = check_spacing_limits(spacing, h_mm, diameter_input)
            label_code = f'D{int(diameter_input)}'

        tasks.append((
            x, y, spacing, triangles, polygons, centroids,
            f'Spasi Tulangan {label_code} — {layer_label} ({dir_label})',
            'mm',
            f'(Method: {method.replace("-", " ").title()} | f\'c = {fc} MPa | d_eff = {d_eff:.0f} mm)',
            load_name, output_folder, method, show_mesh, theme,
            f'spacing_{label_code}_{case_label}',
            None,  # config_labels (not applicable for spacing plot)
            show_annotation,
        ))
    else:
        # Mode B: given spacing, output diameter or config
        if rebar_select_codes:
            # Custom config matching
            cfg_idx, sorted_codes, sorted_areas = select_config_from_As(
                As, rebar_select_codes, spacing_input,
            )
            tasks.append((
                x, y, cfg_idx, triangles, polygons, centroids,
                f'Konfigurasi Tulangan s={int(spacing_input)}mm — {layer_label} ({dir_label})',
                'kode',
                f'(Method: {method.replace("-", " ").title()} | f\'c = {fc} MPa | d_eff = {d_eff:.0f} mm)',
                load_name, output_folder, method, show_mesh, theme,
                f'config_s{int(spacing_input)}_{case_label}',
                sorted_codes,  # config_labels for colorbar
                show_annotation,
            ))
        else:
            # Standard diameter matching (backward compatible)
            D_selected = calc_diameter_from_spacing(As, spacing_input)
            tasks.append((
                x, y, D_selected, triangles, polygons, centroids,
                f'Diameter Tulangan s={int(spacing_input)}mm — {layer_label} ({dir_label})',
                'mm',
                f'(Method: {method.replace("-", " ").title()} | f\'c = {fc} MPa | d_eff = {d_eff:.0f} mm)',
                load_name, output_folder, method, show_mesh, theme,
                f'diameter_s{int(spacing_input)}_{case_label}',
                None,  # config_labels (use default AVAILABLE_DIAMETERS)
                show_annotation,
            ))

    return tasks


def _build_shear_tasks(
    x, y, triangles, polygons, centroids,
    shear_array, h_mm, cover, fc, fy,
    s_long, s_trans,
    direction, case_label,
    load_name, output_folder, method, show_mesh, theme,
    show_annotation=True,
):
    """
    Build plotting task tuples for one shear case.
    Returns list of task tuples (Av/s plot + diameter plot).
    """
    tasks = []

    # Effective depth (use D16 assumption for depth calc, direction determines layer order)
    D_for_depth = 16.0
    # For shear, use 'bottom' layer convention for dv (conservative)
    dv = calc_effective_depth(h_mm, cover, D_for_depth, direction, 'bottom')

    # Calculate Av/s
    Av_s = calc_shear_Av_per_s(shear_array, fc, fy, dv)

    # Skip if all zeros (no shear rebar needed anywhere)
    if np.all(Av_s == 0):
        return tasks

    dir_label = "Arah X" if direction == 'x' else "Arah Y"

    # --- Task 1: Av/s plot ---
    tasks.append((
        x, y, Av_s, triangles, polygons, centroids,
        f'Av/s Geser — {dir_label}',
        '(mm\u00b2/mm) per pias 1m',
        f'(Method: {method.replace("-", " ").title()} | f\'c = {fc} MPa | dv = {dv:.0f} mm)',
        load_name, output_folder, method, show_mesh, theme,
        f'Avs_{case_label}',
        None,  # config_labels
        show_annotation,
    ))

    # --- Task 2: Diameter plot ---
    D_shear = calc_shear_diameter(Av_s, s_long, s_trans)
    s_long_label = int(s_long)
    s_trans_label = int(s_trans)
    tasks.append((
        x, y, D_shear, triangles, polygons, centroids,
        f'Diameter Sengkang s={s_long_label}\u00d7{s_trans_label}mm — {dir_label}',
        'mm',
        f'(Method: {method.replace("-", " ").title()} | f\'c = {fc} MPa | dv = {dv:.0f} mm)',
        load_name, output_folder, method, show_mesh, theme,
        f'shear_diameter_s{s_long_label}x{s_trans_label}_{case_label}',
        None,  # config_labels
        show_annotation,
    ))

    return tasks


def main():
    parser = argparse.ArgumentParser(
        description='FEA Rebar Analysis & Contour Plot Generator'
    )
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
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
    parser.add_argument('--diameter', type=str, default=None,
                        help='Rebar config code for Mode A (output = spacing). '
                             'Examples: 16, 2D25, 3D32')
    parser.add_argument('--spacing', type=float, default=150,
                        help='Bar spacing in mm (Mode B: output = config, default: 150)')
    parser.add_argument('--rebar-select', type=str, nargs='+', default=None,
                        help='Select rebar configs for Mode B output. '
                             'Examples: --rebar-select 16 22 25 2D25 2D32')
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
    parser.add_argument('--shear', action='store_true',
                        help='Enable shear reinforcement analysis (Av/s from Vxx, Vyy)')
    parser.add_argument('--shear-spacing-long', type=float, default=150,
                        help='Stirrup longitudinal spacing in mm (default: 150)')
    parser.add_argument('--shear-spacing-trans', type=float, default=150,
                        help='Stirrup transversal spacing in mm (default: 150)')
    parser.add_argument('--no-annotation', action='store_true',
                        help='Hide MAX marker and SECTION INADEQUATE badge on plots')
    args = parser.parse_args()

    show_mesh = not args.no_mesh
    show_annotation = not args.no_annotation
    h_mm = args.thickness * 1000  # m → mm

    # Validate --rebar-select codes if provided
    rebar_select_codes = None
    if args.rebar_select:
        rebar_select_codes = [c.upper().strip() for c in args.rebar_select]
        for code in rebar_select_codes:
            if code not in REBAR_CONFIG_TABLE:
                print(f"[ERROR] Kode konfigurasi '{code}' tidak dikenali.")
                print(f"  Kode tersedia: {', '.join(sorted(REBAR_CONFIG_TABLE.keys()))}")
                sys.exit(1)

    # Determine mode
    if args.diameter is not None:
        mode = 'spacing'
        config_code = args.diameter.upper().strip()
        if config_code not in REBAR_CONFIG_TABLE:
            # Try as bare number (backward compat: --diameter 16)
            if config_code.isdigit() and config_code in REBAR_CONFIG_TABLE:
                pass
            else:
                print(f"[ERROR] Kode konfigurasi '{config_code}' tidak dikenali.")
                print(f"  Kode tersedia: {', '.join(sorted(REBAR_CONFIG_TABLE.keys()))}")
                sys.exit(1)
        config_area = get_config_area(config_code)
        # Extract base diameter for effective depth calc
        diameter_input = float(REBAR_CONFIG_TABLE[config_code][0])
        spacing_input = None
        mode_desc = f"Mode A: Input {config_code} (As={config_area:.0f} mm²) -> Output Spasi"
    else:
        mode = 'diameter'
        config_code = None
        config_area = None
        diameter_input = None
        spacing_input = args.spacing
        if rebar_select_codes:
            codes_str = ', '.join(rebar_select_codes)
            mode_desc = f"Mode B: Input s={int(spacing_input)}mm -> Output Konfigurasi [{codes_str}]"
        else:
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
    if args.shear:
        print(f"Shear Analysis: ON | s_long={args.shear_spacing_long:.0f}mm | s_trans={args.shear_spacing_trans:.0f}mm")

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
    shear_envelope_data = {}  # For shear Av/s envelope

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
                    rebar_select_codes=rebar_select_codes,
                    config_code=config_code, config_area=config_area,
                    show_annotation=show_annotation,
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

        def process_shear_source(source_name, force_arrays, folder_path):
            """Process one source for shear reinforcement."""
            tasks = []
            for shear_col, direction, case_label in SHEAR_CASES:
                if shear_col not in force_arrays:
                    continue
                v_arr = force_arrays[shear_col]

                # Determine spacing convention:
                # Vxx → s_long = along X (user input), s_trans = along Y (user input)
                # Vyy → s_long = along Y (user input), s_trans = along X (user input)
                if direction == 'x':
                    s_l = args.shear_spacing_long
                    s_t = args.shear_spacing_trans
                else:
                    s_l = args.shear_spacing_trans
                    s_t = args.shear_spacing_long

                case_tasks = _build_shear_tasks(
                    x, y, tris, polys, cents,
                    v_arr, h_mm, args.cover, args.fc, args.fy,
                    s_l, s_t,
                    direction, case_label,
                    source_name, folder_path, method, show_mesh, args.theme,
                    show_annotation=show_annotation,
                )
                tasks.extend(case_tasks)

                # --- Shear envelope accumulation ---
                D_for_depth = 16.0
                dv = calc_effective_depth(h_mm, args.cover, D_for_depth, direction, 'bottom')
                Av_s = calc_shear_Av_per_s(v_arr, args.fc, args.fy, dv)

                if case_label not in shear_envelope_data:
                    shear_envelope_data[case_label] = Av_s.copy()
                else:
                    shear_envelope_data[case_label] = np.fmax(
                        shear_envelope_data[case_label], Av_s
                    )

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

                # --- Shear tasks for this load case ---
                if args.shear:
                    force_arrays = {}
                    for shear_col, _, _ in SHEAR_CASES:
                        arr = vm.get_z_array(shear_col)
                        if len(arr) > 0:
                            force_arrays[shear_col] = arr
                    all_tasks.extend(process_shear_source(lc, force_arrays, lc_folder))

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

                # --- Shear tasks for this combination ---
                if args.shear:
                    force_arrays = {}
                    for shear_col, _, _ in SHEAR_CASES:
                        first_arr = value_mapper_cache[lc_factors[0][0]].get_z_array(shear_col)
                        z_comb = np.zeros_like(first_arr)
                        for lc_a, fac in lc_factors:
                            z_comb += fac * value_mapper_cache[lc_a].get_z_array(shear_col)
                        force_arrays[shear_col] = z_comb
                    all_tasks.extend(
                        process_shear_source(f"Comb: {combo_name}", force_arrays, combo_folder)
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
                    f'(Maximum dari seluruh kasus | f\'c = {args.fc} MPa | d_eff = {d_eff:.0f} mm)',
                    'ENVELOPE', envelope_folder, method, show_mesh, args.theme,
                    f'ENVELOPE_As_{case_label}',
                    None,  # config_labels
                    show_annotation,
                ))

                # Spacing/Diameter/Config envelope plot
                if mode == 'spacing':
                    if config_code and config_area:
                        spacing_env = np.full_like(As_env, np.inf)
                        active_env = (As_env > 1e-6) & ~np.isnan(As_env)
                        spacing_env[active_env] = config_area * 1000.0 / As_env[active_env]
                        spacing_env = check_spacing_limits(spacing_env, h_mm, diameter_input)
                        label_code = config_code
                    else:
                        spacing_env = calc_spacing_from_diameter(As_env, diameter_input)
                        spacing_env = check_spacing_limits(spacing_env, h_mm, diameter_input)
                        label_code = f'D{int(diameter_input)}'
                    all_tasks.append((
                        x, y, spacing_env, tris, polys, cents,
                        f'ENVELOPE Spasi {label_code} — {layer_label} ({dir_label})',
                        'mm',
                        f'(Maximum dari seluruh kasus | f\'c = {args.fc} MPa | d_eff = {d_eff:.0f} mm)',
                        'ENVELOPE', envelope_folder, method, show_mesh, args.theme,
                        f'ENVELOPE_spacing_{label_code}_{case_label}',
                        None,  # config_labels
                        show_annotation,
                    ))
                else:
                    if rebar_select_codes:
                        cfg_idx, sorted_codes, sorted_areas = select_config_from_As(
                            As_env, rebar_select_codes, spacing_input,
                        )
                        all_tasks.append((
                            x, y, cfg_idx, tris, polys, cents,
                            f'ENVELOPE Konfigurasi s={int(spacing_input)}mm — {layer_label} ({dir_label})',
                            'kode',
                            f'(Maximum dari seluruh kasus | f\'c = {args.fc} MPa | d_eff = {d_eff:.0f} mm)',
                            'ENVELOPE', envelope_folder, method, show_mesh, args.theme,
                            f'ENVELOPE_config_s{int(spacing_input)}_{case_label}',
                            sorted_codes,  # config_labels
                            show_annotation,
                        ))
                    else:
                        D_env = calc_diameter_from_spacing(As_env, spacing_input)
                        all_tasks.append((
                            x, y, D_env, tris, polys, cents,
                            f'ENVELOPE Diameter s={int(spacing_input)}mm — {layer_label} ({dir_label})',
                            'mm',
                            f'(Maximum dari seluruh kasus | f\'c = {args.fc} MPa | d_eff = {d_eff:.0f} mm)',
                            'ENVELOPE', envelope_folder, method, show_mesh, args.theme,
                            f'ENVELOPE_diameter_s{int(spacing_input)}_{case_label}',
                            None,  # config_labels
                            show_annotation,
                        ))

        # --- Shear Envelope tasks ---
        if args.shear and shear_envelope_data:
            shear_env_folder = os.path.join(method_output, "Envelope_Shear")
            os.makedirs(shear_env_folder, exist_ok=True)

            for case_label, Av_s_env in shear_envelope_data.items():
                for shear_col, direction, cl in SHEAR_CASES:
                    if cl == case_label:
                        break

                dir_label = "Arah X" if direction == 'x' else "Arah Y"
                D_for_depth = 16.0
                dv = calc_effective_depth(h_mm, args.cover, D_for_depth, direction, 'bottom')

                # Av/s envelope plot
                all_tasks.append((
                    x, y, Av_s_env, tris, polys, cents,
                    f'ENVELOPE Av/s Geser — {dir_label}',
                    '(mm²/mm) per pias 1m',
                    f'(Maximum dari seluruh kasus | f\'c = {args.fc} MPa | dv = {dv:.0f} mm)',
                    'ENVELOPE', shear_env_folder, method, show_mesh, args.theme,
                    f'ENVELOPE_Avs_{case_label}',
                    None,  # config_labels
                    show_annotation,
                ))

                # Diameter envelope plot
                if direction == 'x':
                    s_l = args.shear_spacing_long
                    s_t = args.shear_spacing_trans
                else:
                    s_l = args.shear_spacing_trans
                    s_t = args.shear_spacing_long

                D_shear_env = calc_shear_diameter(Av_s_env, s_l, s_t)
                all_tasks.append((
                    x, y, D_shear_env, tris, polys, cents,
                    f'ENVELOPE Diameter Sengkang s={int(s_l)}×{int(s_t)}mm — {dir_label}',
                    'mm',
                    f'(Maximum dari seluruh kasus | f\'c = {args.fc} MPa | dv = {dv:.0f} mm)',
                    'ENVELOPE', shear_env_folder, method, show_mesh, args.theme,
                    f'ENVELOPE_shear_D_s{int(s_l)}x{int(s_t)}_{case_label}',
                    None,  # config_labels
                    show_annotation,
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
