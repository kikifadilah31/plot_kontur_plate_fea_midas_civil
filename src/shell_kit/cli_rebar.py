"""
`shell-kit rebar` — reinforcement demand from FEM moments and shears.

Driven by shell_kit.cli, which owns the argument parser.
"""

import os
import sys
import fnmatch
import numpy as np
from datetime import datetime
from tqdm import tqdm
from multiprocessing import Pool, cpu_count

from .config import ALL_METHODS
from .math_utils import safe_filename
from .combination import (
    parse_combination_file, validate_combinations, format_resolution_warnings,
)
from .io_utils import load_csv_inputs, build_coord_dict, resolve_input_files
from .mesh import MeshTopology
from .values import ValueMapper
from .rebar import (
    DEFAULT_FC, DEFAULT_FY, DEFAULT_COVER, PHI_FLEXURE,
    AVAILABLE_DIAMETERS, SHEAR_DIAMETERS,
    REBAR_CONFIG_TABLE,
    calc_as_min, calc_as_min_per_face,
    calc_effective_depth, calc_as_required, apply_as_min,
    calc_spacing_from_diameter, calc_diameter_from_spacing,
    check_spacing_limits,
    calc_shear_Av_per_s, calc_shear_diameter,
    get_config_area, select_config_from_As,
    solve_rebar_iterative, format_depth_range,
)
from .plotting_rebar import init_rebar_worker, generate_rebar_plot_worker
from .reporting_rebar import (
    summarize_case, summarize_shear_case, build_params,
    render_rebar_report_md, render_rebar_report_typst,
)
from .report_writer import (
    prepare_figures, write_document, compile_pdfs, print_figure_dir,
    uses_typst, document_ext, COMBINED_STEM,
)
from .reporting_typst import render_combined_typst


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

# Report source name for the envelope — the governing design case
ENVELOPE_NAME = 'ENVELOPE'


def _build_rebar_tasks(
    x, y, triangles, polygons, centroids,
    moment_array, h_mm, cover, fc, fy,
    diameter_input, spacing_input, mode,
    direction, layer, case_label,
    load_name, output_folder, method, show_mesh, theme,
    rebar_select_codes=None, config_code=None, config_area=None,
    show_annotation=True, apply_min=True, surface_zone=None,
):
    """
    Build plotting task tuples for one rebar case.

    Returns (tasks, As, d_eff) so the caller can accumulate the envelope from
    the SAME As the plots use — recomputing it separately let the two drift.

    Mode A (a bar is given, spacing is the answer) keeps a scalar effective
    depth. Mode B (spacing is given, the bar is the answer) iterates the depth
    against the bar actually selected.
    """
    tasks = []

    # Separate positive (bottom) and negative (top) moments
    if layer == 'bottom':
        # Positive moment → bottom rebar
        Mu = np.where(moment_array > 0, moment_array, 0.0)
    else:
        # Negative moment → top rebar (use absolute value)
        Mu = np.where(moment_array < 0, np.abs(moment_array), 0.0)

    if mode == 'spacing':
        # Mode A: bar size is known up front, so d is a single scalar
        d_eff = calc_effective_depth(h_mm, cover, diameter_input, direction, layer)
        As = calc_as_required(Mu, fc, fy, d_eff, PHI_FLEXURE)
        if apply_min:
            As = apply_as_min(As, fy, h_mm, surface_zone=surface_zone)
        selection = sorted_codes = None
    else:
        # Mode B: d and the bar selection are solved together
        As, d_eff, selection, sorted_codes = solve_rebar_iterative(
            Mu, fc, fy, h_mm, cover, direction, layer,
            spacing_input, config_codes=rebar_select_codes,
            apply_min=apply_min, surface_zone=surface_zone,
        )

    layer_label = "Tulangan Bawah" if layer == 'bottom' else "Tulangan Atas"
    dir_label = "Arah X" if direction == 'x' else "Arah Y"

    # What the report needs to describe this case, regardless of mode
    result = {
        'As': As, 'd_eff': d_eff,
        'selection': None, 'kind': None, 'config_labels': None,
        'title': f'{layer_label} ({dir_label})',
        'figures': [],
    }

    # A face with no moment anywhere still needs shrinkage and temperature
    # steel, so it keeps its layer — carrying As_min alone. Dropping it left
    # the report silent about reinforcement the code actually requires.
    # Without the minimum enabled there is genuinely nothing to draw.
    if not np.any(Mu > 1e-9) and not apply_min:
        return tasks, result

    depth_label = format_depth_range(d_eff)
    subtitle = (f'(Method: {method.replace("-", " ").title()} '
                f'| f\'c = {fc} MPa | d_eff = {depth_label})')

    def _fig(tag):
        return os.path.join(output_folder, f"rebar_{safe_filename(tag)}.png")

    # --- Task 1: As_required plot (always shown) ---
    tasks.append((
        x, y, As, triangles, polygons, centroids,
        f'As Required — {layer_label} ({dir_label})',
        'mm²/m',
        subtitle,
        load_name, output_folder, method, show_mesh, theme,
        f'As_{case_label}',
        None,  # config_labels (not applicable for As plot)
        show_annotation,
    ))
    result['figures'].append(
        (f'As perlu — {layer_label} ({dir_label})', _fig(f'As_{case_label}'))
    )

    # --- Task 2: Spacing or Diameter/Config plot ---
    if mode == 'spacing':
        # Mode A: given config code, output spacing
        if config_code and config_area:
            # Use config area (e.g. 2D25 = 982 mm²) for spacing calc
            spacing = np.full(As.shape, np.inf)
            active = (As > 1e-6) & ~np.isnan(As)
            spacing[active] = config_area * 1000.0 / As[active]
            # Carry inadequate nodes through — they used to read as inf,
            # i.e. "no rebar needed", the opposite of the truth.
            spacing[np.isnan(As)] = np.nan
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
            subtitle,
            load_name, output_folder, method, show_mesh, theme,
            f'spacing_{label_code}_{case_label}',
            None,  # config_labels (not applicable for spacing plot)
            show_annotation,
        ))
        result['selection'] = spacing
        result['kind'] = 'spacing'
        result['figures'].append(
            (f'Spasi tulangan {label_code} — {layer_label} ({dir_label})',
             _fig(f'spacing_{label_code}_{case_label}'))
        )
    elif rebar_select_codes:
        # Mode B with custom config matching
        tasks.append((
            x, y, selection, triangles, polygons, centroids,
            f'Konfigurasi Tulangan s={int(spacing_input)}mm — {layer_label} ({dir_label})',
            'kode',
            subtitle,
            load_name, output_folder, method, show_mesh, theme,
            f'config_s{int(spacing_input)}_{case_label}',
            sorted_codes,  # config_labels for colorbar
            show_annotation,
        ))
        result['selection'] = selection
        result['kind'] = 'config'
        result['config_labels'] = sorted_codes
        result['figures'].append(
            (f'Konfigurasi tulangan s={int(spacing_input)}mm — {layer_label} ({dir_label})',
             _fig(f'config_s{int(spacing_input)}_{case_label}'))
        )
    else:
        # Mode B, standard single-diameter matching (backward compatible)
        tasks.append((
            x, y, selection, triangles, polygons, centroids,
            f'Diameter Tulangan s={int(spacing_input)}mm — {layer_label} ({dir_label})',
            'mm',
            subtitle,
            load_name, output_folder, method, show_mesh, theme,
            f'diameter_s{int(spacing_input)}_{case_label}',
            None,  # config_labels (use default AVAILABLE_DIAMETERS)
            show_annotation,
        ))
        result['selection'] = selection
        result['kind'] = 'diameter'
        result['figures'].append(
            (f'Diameter tulangan s={int(spacing_input)}mm — {layer_label} ({dir_label})',
             _fig(f'diameter_s{int(spacing_input)}_{case_label}'))
        )

    return tasks, result


def _build_shear_tasks(
    x, y, triangles, polygons, centroids,
    shear_array, h_mm, cover, fc, fy,
    s_long, s_trans,
    direction, case_label,
    load_name, output_folder, method, show_mesh, theme,
    show_annotation=True, shear_select_diameters=None,
):
    """
    Build plotting task tuples for one shear case.

    Returns (tasks, Av_s) so the caller reuses the same array for the envelope.
    """
    tasks = []

    # Effective depth (use D16 assumption for depth calc, direction determines layer order)
    D_for_depth = 16.0
    # For shear, use 'bottom' layer convention for dv (conservative)
    dv = calc_effective_depth(h_mm, cover, D_for_depth, direction, 'bottom')

    # Calculate Av/s
    Av_s = calc_shear_Av_per_s(shear_array, fc, fy, dv)

    # Skip only when no stirrups are needed anywhere AND nothing failed the
    # web-crushing check (np.nan) — a crushing zone must always be plotted.
    if not (np.any(Av_s > 0) or np.any(np.isnan(Av_s))):
        return tasks, Av_s

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
    D_shear = calc_shear_diameter(Av_s, s_long, s_trans,
                                  available_diameters=shear_select_diameters)
    s_long_label = int(s_long)
    s_trans_label = int(s_trans)

    # Build config_labels for custom shear diameters (for colorbar)
    shear_labels = None
    if shear_select_diameters is not None:
        sorted_d = sorted(shear_select_diameters)
        shear_labels = [f'D{int(d)}' for d in sorted_d]

    tasks.append((
        x, y, D_shear, triangles, polygons, centroids,
        f'Diameter Sengkang s={s_long_label}\u00d7{s_trans_label}mm — {dir_label}',
        'mm',
        f'(Method: {method.replace("-", " ").title()} | f\'c = {fc} MPa | dv = {dv:.0f} mm)',
        load_name, output_folder, method, show_mesh, theme,
        f'shear_diameter_s{s_long_label}x{s_trans_label}_{case_label}',
        shear_labels,  # config_labels for custom shear colorbar
        show_annotation,
    ))

    return tasks, Av_s


def run(args):

    show_mesh = not args.no_mesh
    show_annotation = not args.no_annotation
    apply_min = not args.no_as_min
    h_mm = args.thickness * 1000  # m → mm

    # Validate --shear-select diameters if provided
    shear_select_diameters = None
    if args.shear_select:
        shear_select_diameters = sorted(args.shear_select)

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
    if apply_min:
        sz = args.as_min_surface_zone
        total = calc_as_min(args.fy, h_mm)
        per_face = calc_as_min_per_face(args.fy, h_mm, surface_zone=sz)
        print(f"As minimum (SNI 24.4.3.2): {total:.0f} mm2/m penampang "
              f"-> {per_face:.0f} mm2/m per lapis")
        if sz:
            print(f"  Zona permukaan dibatasi {sz:.0f} mm per muka "
                  f"(ACI 350-06 7.12.2.1, di luar huruf SNI 2847)")
    else:
        print("As minimum: NONAKTIF (--no-as-min)")
    if args.shear:
        shear_info = f"Shear Analysis: ON | s_long={args.shear_spacing_long:.0f}mm | s_trans={args.shear_spacing_trans:.0f}mm"
        if shear_select_diameters:
            shear_info += f" | Diameter: D{shear_select_diameters}"
        print(shear_info)

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

    total_failed = 0

    for method in methods_to_run:
        print(f"\nProcessing Method: {method.upper()}")
        method_output = (
            os.path.join(timestamp_output, f"Method_{safe_filename(method)}")
            if args.method == 'all'
            else timestamp_output
        )

        # --- Envelope accumulators ---
        # Structure: envelope_data[case_label] = running_max_array
        # MUST be per-method: each contour method produces arrays of a
        # different length, so carrying them across methods made np.fmax
        # fail with a broadcast error on `--method all`.
        envelope_data = {}
        envelope_depth = {}       # element-wise MIN d_eff (conservative)
        shear_envelope_data = {}  # For shear Av/s envelope

        # --- Build MeshTopology + ValueMappers ---
        print("  [1/3] Building Value Mappers...")
        mesh = MeshTopology(df_conn, coord_dict, method)
        if mesh.n_invalid:
            print(f"  [WARN] {mesh.n_invalid} elemen dilewati "
                  f"(node tidak ada di CSV koordinat).")
        value_mapper_cache = {}

        for lc in load_cases:
            df_lc = df_gaya[df_gaya['Load'] == lc].copy()
            value_mapper_cache[lc] = ValueMapper(df_lc, mesh)

        # --- Geometry references ---
        x, y, tris = (None, None, None) if method == 'element-center' else (mesh.x, mesh.y, mesh.triangles)
        polys, cents = (mesh.polygons, mesh.centroids) if method == 'element-center' else (None, None)

        # Coordinates the report quotes when locating maxima and failures.
        # element-center reports centroids; the other methods report nodes.
        if method == 'element-center':
            coords_for_report = (
                np.array([c[0] for c in mesh.centroids]),
                np.array([c[1] for c in mesh.centroids]),
            )
        else:
            coords_for_report = (mesh.x, mesh.y)

        # {source_name: {'folder', 'cases', 'figures'}} — feeds --report
        report_sources = {}

        # --- Build Task Pool ---
        print("  [2/3] Building Rebar Task Pool...")
        all_tasks = []

        def process_moment_source(source_name, moment_arrays, folder_path):
            """Process one moment source (load case or combination) into plot tasks."""
            tasks = []
            entry = report_sources.setdefault(
                source_name,
                {'folder': folder_path, 'cases': [], 'shear_cases': [],
                 'figures': []},
            )
            for moment_col, direction, layer, case_label in REBAR_CASES:
                if moment_col not in moment_arrays:
                    continue
                m_arr = moment_arrays[moment_col]

                case_tasks, res = _build_rebar_tasks(
                    x, y, tris, polys, cents,
                    m_arr, h_mm, args.cover, args.fc, args.fy,
                    diameter_input, spacing_input, mode,
                    direction, layer, case_label,
                    source_name, folder_path, method, show_mesh, args.theme,
                    rebar_select_codes=rebar_select_codes,
                    config_code=config_code, config_area=config_area,
                    show_annotation=show_annotation,
                    apply_min=apply_min, surface_zone=args.as_min_surface_zone,
                )
                tasks.extend(case_tasks)

                As, d_eff = res['As'], res['d_eff']

                # --- Report accumulation ---
                if case_tasks:
                    entry['cases'].append((res['title'], summarize_case(
                        As, res['selection'], d_eff, coords_for_report,
                        kind=res['kind'], config_labels=res['config_labels'],
                    )))
                    entry['figures'].extend(res['figures'])

                # --- Envelope accumulation ---
                # Reuse the As the plots were built from, so the envelope can
                # never disagree with the per-case plots.
                d_arr = np.broadcast_to(np.asarray(d_eff, dtype=float), As.shape)
                if case_label not in envelope_data:
                    envelope_data[case_label] = As.copy()
                    envelope_depth[case_label] = d_arr.copy()
                else:
                    # np.maximum, NOT np.fmax: fmax discards NaN, so a node
                    # would only read as inadequate if EVERY case failed there.
                    # The envelope is what the design is taken from — one
                    # failing case is enough to condemn the node.
                    envelope_data[case_label] = np.maximum(envelope_data[case_label], As)
                    envelope_depth[case_label] = np.fmin(envelope_depth[case_label], d_arr)

            return tasks

        def process_shear_source(source_name, force_arrays, folder_path):
            """Process one source for shear reinforcement."""
            tasks = []
            entry = report_sources.setdefault(
                source_name,
                {'folder': folder_path, 'cases': [], 'shear_cases': [],
                 'figures': []},
            )
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

                case_tasks, Av_s = _build_shear_tasks(
                    x, y, tris, polys, cents,
                    v_arr, h_mm, args.cover, args.fc, args.fy,
                    s_l, s_t,
                    direction, case_label,
                    source_name, folder_path, method, show_mesh, args.theme,
                    show_annotation=show_annotation,
                    shear_select_diameters=shear_select_diameters,
                )
                tasks.extend(case_tasks)

                # --- Report figures + summary for shear ---
                if case_tasks:
                    dir_label = "Arah X" if direction == 'x' else "Arah Y"
                    dv_case = calc_effective_depth(h_mm, args.cover, 16.0,
                                                   direction, 'bottom')
                    entry['shear_cases'].append((
                        f'Geser {dir_label}',
                        summarize_shear_case(
                            Av_s,
                            calc_shear_diameter(
                                Av_s, s_l, s_t,
                                available_diameters=shear_select_diameters),
                            dv_case, coords_for_report),
                    ))
                    for tag, cap in (
                        (f'Avs_{case_label}', f'Av/s geser — {dir_label}'),
                        (f'shear_diameter_s{int(s_l)}x{int(s_t)}_{case_label}',
                         f'Diameter sengkang s={int(s_l)}×{int(s_t)}mm — {dir_label}'),
                    ):
                        entry['figures'].append(
                            (cap, os.path.join(
                                folder_path, f"rebar_{safe_filename(tag)}.png")),
                        )

                # --- Shear envelope accumulation (reuses the same Av_s) ---
                if case_label not in shear_envelope_data:
                    shear_envelope_data[case_label] = Av_s.copy()
                else:
                    # np.maximum so a web-crushing failure in any single case
                    # survives into the envelope (see the flexural note above).
                    shear_envelope_data[case_label] = np.maximum(
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
            _, matched_map, uncertain = validate_combinations(combos, load_cases)
            warn_lines = format_resolution_warnings(uncertain)
            if warn_lines:
                print("  [WARN] Nama load case tidak cocok persis, hasil penyesuaian:")
                for line in warn_lines:
                    print(line)
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

            # The envelope is what the design is actually taken from, so it
            # belongs in the report like any other source. It lives at the run
            # root because it spans both Envelope_Rebar and Envelope_Shear.
            env_entry = report_sources.setdefault(
                ENVELOPE_NAME,
                {'folder': method_output, 'cases': [], 'shear_cases': [],
                 'figures': []},
            )

            for case_label, As_env in envelope_data.items():
                # Find direction/layer info from case_label
                for moment_col, direction, layer, cl in REBAR_CASES:
                    if cl == case_label:
                        break

                layer_label = "Tulangan Bawah" if layer == 'bottom' else "Tulangan Atas"
                dir_label = "Arah X" if direction == 'x' else "Arah Y"
                depth_label = format_depth_range(envelope_depth[case_label])
                env_subtitle = (f'(Maximum dari seluruh kasus '
                                f'| f\'c = {args.fc} MPa | d_eff = {depth_label})')

                # As envelope plot
                all_tasks.append((
                    x, y, As_env, tris, polys, cents,
                    f'ENVELOPE As — {layer_label} ({dir_label})',
                    'mm²/m',
                    env_subtitle,
                    'ENVELOPE', envelope_folder, method, show_mesh, args.theme,
                    f'ENVELOPE_As_{case_label}',
                    None,  # config_labels
                    show_annotation,
                ))
                env_entry['figures'].append((
                    f'ENVELOPE As perlu — {layer_label} ({dir_label})',
                    os.path.join(envelope_folder,
                                 f'rebar_{safe_filename(f"ENVELOPE_As_{case_label}")}.png'),
                ))
                env_sel = env_kind = env_labels = None

                # Spacing/Diameter/Config envelope plot
                if mode == 'spacing':
                    if config_code and config_area:
                        spacing_env = np.full(As_env.shape, np.inf)
                        active_env = (As_env > 1e-6) & ~np.isnan(As_env)
                        spacing_env[active_env] = config_area * 1000.0 / As_env[active_env]
                        spacing_env[np.isnan(As_env)] = np.nan
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
                        env_subtitle,
                        'ENVELOPE', envelope_folder, method, show_mesh, args.theme,
                        f'ENVELOPE_spacing_{label_code}_{case_label}',
                        None,  # config_labels
                        show_annotation,
                    ))
                    env_sel, env_kind = spacing_env, 'spacing'
                    env_entry['figures'].append((
                        f'ENVELOPE spasi {label_code} — {layer_label} ({dir_label})',
                        os.path.join(envelope_folder,
                                     f'rebar_{safe_filename(f"ENVELOPE_spacing_{label_code}_{case_label}")}.png'),
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
                            env_subtitle,
                            'ENVELOPE', envelope_folder, method, show_mesh, args.theme,
                            f'ENVELOPE_config_s{int(spacing_input)}_{case_label}',
                            sorted_codes,  # config_labels
                            show_annotation,
                        ))
                        env_sel, env_kind, env_labels = cfg_idx, 'config', sorted_codes
                        env_entry['figures'].append((
                            f'ENVELOPE konfigurasi s={int(spacing_input)}mm — {layer_label} ({dir_label})',
                            os.path.join(envelope_folder,
                                         f'rebar_{safe_filename(f"ENVELOPE_config_s{int(spacing_input)}_{case_label}")}.png'),
                        ))
                    else:
                        D_env = calc_diameter_from_spacing(As_env, spacing_input)
                        all_tasks.append((
                            x, y, D_env, tris, polys, cents,
                            f'ENVELOPE Diameter s={int(spacing_input)}mm — {layer_label} ({dir_label})',
                            'mm',
                            env_subtitle,
                            'ENVELOPE', envelope_folder, method, show_mesh, args.theme,
                            f'ENVELOPE_diameter_s{int(spacing_input)}_{case_label}',
                            None,  # config_labels
                            show_annotation,
                        ))
                        env_sel, env_kind = D_env, 'diameter'
                        env_entry['figures'].append((
                            f'ENVELOPE diameter s={int(spacing_input)}mm — {layer_label} ({dir_label})',
                            os.path.join(envelope_folder,
                                         f'rebar_{safe_filename(f"ENVELOPE_diameter_s{int(spacing_input)}_{case_label}")}.png'),
                        ))

                env_entry['cases'].append((
                    f'{layer_label} ({dir_label})',
                    summarize_case(As_env, env_sel, envelope_depth[case_label],
                                   coords_for_report, kind=env_kind,
                                   config_labels=env_labels),
                ))

        # --- Shear Envelope tasks ---
        if args.shear and shear_envelope_data:
            shear_env_folder = os.path.join(method_output, "Envelope_Shear")
            os.makedirs(shear_env_folder, exist_ok=True)
            env_entry = report_sources.setdefault(
                ENVELOPE_NAME,
                {'folder': method_output, 'cases': [], 'shear_cases': [],
                 'figures': []},
            )

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

                D_shear_env = calc_shear_diameter(Av_s_env, s_l, s_t,
                                                  available_diameters=shear_select_diameters)
                # Build config_labels for custom shear diameters
                shear_env_labels = None
                if shear_select_diameters is not None:
                    sorted_d = sorted(shear_select_diameters)
                    shear_env_labels = [f'D{int(d)}' for d in sorted_d]

                all_tasks.append((
                    x, y, D_shear_env, tris, polys, cents,
                    f'ENVELOPE Diameter Sengkang s={int(s_l)}×{int(s_t)}mm — {dir_label}',
                    'mm',
                    f'(Maximum dari seluruh kasus | f\'c = {args.fc} MPa | dv = {dv:.0f} mm)',
                    'ENVELOPE', shear_env_folder, method, show_mesh, args.theme,
                    f'ENVELOPE_shear_D_s{int(s_l)}x{int(s_t)}_{case_label}',
                    shear_env_labels,  # config_labels for custom shear colorbar
                    show_annotation,
                ))

                for tag, cap in (
                    (f'ENVELOPE_Avs_{case_label}',
                     f'ENVELOPE Av/s geser — {dir_label}'),
                    (f'ENVELOPE_shear_D_s{int(s_l)}x{int(s_t)}_{case_label}',
                     f'ENVELOPE diameter sengkang s={int(s_l)}×{int(s_t)}mm — {dir_label}'),
                ):
                    env_entry['figures'].append((cap, os.path.join(
                        shear_env_folder, f'rebar_{safe_filename(tag)}.png')))

                env_entry['shear_cases'].append((
                    f'Geser {dir_label}',
                    summarize_shear_case(Av_s_env, D_shear_env, dv,
                                         coords_for_report),
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

        # Surface inadequate zones in the console — previously they were only
        # visible by opening every PNG.
        inadequate = {}
        for label, arr in envelope_data.items():
            n_bad = int(np.count_nonzero(np.isnan(arr)))
            if n_bad:
                inadequate[label] = n_bad
        for label, arr in shear_envelope_data.items():
            n_bad = int(np.count_nonzero(np.isnan(arr)))
            if n_bad:
                inadequate[label] = n_bad
        if inadequate:
            print("  [SECTION INADEQUATE] penampang tidak memenuhi syarat:")
            for label, n_bad in sorted(inadequate.items()):
                print(f"    - {label}: {n_bad} titik")

        if errors:
            total_failed += len(errors)
            print(f"  [WARN] {len(errors)} plots failed:")
            for err in errors[:5]:
                print(f"    - {err.get('task', '?')}: {err.get('error', '?')}")

        # --- Reports (--report) ---
        if args.report and report_sources:
            print("  [4/4] Menyusun laporan tulangan...")
            typst_mode = uses_typst(args.report_format)
            ext = document_ext(args.report_format)
            render = (render_rebar_report_typst if typst_mode
                      else render_rebar_report_md)
            params = build_params(
                args, h_mm, mode_desc, method, apply_min,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            )
            done = set(generated_files)
            written, fragments = [], []
            pdir = print_figure_dir(args.report_format, method_output)

            for name, entry in report_sources.items():
                if not entry['cases']:
                    continue
                figures = prepare_figures(entry['figures'], entry['folder'],
                                          done, pdir)
                content = render(name, entry['cases'], params, figures=figures,
                                 shear_cases=entry.get('shear_cases'))
                clean = name.replace('Comb: ', '')
                path = os.path.join(
                    entry['folder'], f'Laporan_Tulangan_{safe_filename(clean)}{ext}',
                )
                written.append(write_document(content, path))
                print(f"    {os.path.relpath(path, method_output)}")

                if typst_mode:
                    # Figures re-resolved against the combined document's
                    # folder so the same PNG is reachable from both.
                    fragments.append(render_rebar_report_typst(
                        name, entry['cases'], params,
                        figures=prepare_figures(entry['figures'],
                                                method_output, done, pdir),
                        preamble=False,
                        shear_cases=entry.get('shear_cases'),
                    ))

            if typst_mode and fragments:
                n_bad = sum(
                    s['n_inadequate']
                    for e in report_sources.values()
                    if e is not report_sources.get(ENVELOPE_NAME)
                    for _, s in list(e['cases']) + list(e.get('shear_cases') or [])
                )
                combined = os.path.join(method_output, f'{COMBINED_STEM}{ext}')
                write_document(render_combined_typst(
                    {
                        'title': 'Laporan Kebutuhan Tulangan',
                        'subtitle': mode_desc,
                        'rows': [
                            ('Dibuat', params['generated']),
                            ('Tebal pelat', f"{h_mm:.0f} mm"),
                            ("f'c / fy", f"{args.fc:.0f} / {args.fy:.0f} MPa"),
                            ('Selimut bersih', f"{args.cover:.0f} mm"),
                            ('Metode kontur', method.replace('-', ' ').title()),
                            ('Jumlah sumber', str(len(fragments))),
                            ('Titik SECTION INADEQUATE', str(n_bad)),
                            ('Koordinat', os.path.basename(k_file or '-')),
                            ('Konektivitas', os.path.basename(c_file or '-')),
                            ('Gaya', os.path.basename(g_file or '-')),
                        ],
                        'note': 'Dihasilkan oleh shell-kit menurut SNI 2847:2019. '
                                'Titik SECTION INADEQUATE tidak dapat diselesaikan '
                                'dengan memperbesar tulangan — tinjau tebal pelat '
                                'atau mutu beton.',
                    },
                    fragments,
                ), combined)
                written.append(combined)
                print(f"    {os.path.relpath(combined, method_output)}")

            if args.report_format == 'pdf':
                print("  Mengompilasi PDF...")
                _, n_failed = compile_pdfs(written, method_output)
                total_failed += n_failed

    # Failed plots used to exit 0 under a "[SUCCESS]" banner, so a run that
    # produced nothing looked identical to a good one.
    if total_failed:
        print(f"\n[FAILED] {total_failed} plot gagal dibuat. Lihat pesan di atas.")
        return 1

    print(f"\n[SUCCESS] Selesai. Output di: {timestamp_output}")
    return 0
