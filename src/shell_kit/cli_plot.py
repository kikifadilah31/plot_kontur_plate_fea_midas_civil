"""
`shell-kit plot` — contour plots of forces, moments and fibre stresses.

Driven by shell_kit.cli, which owns the argument parser.
"""

import os
import fnmatch
import numpy as np
from datetime import datetime
from tqdm import tqdm
from multiprocessing import Pool, cpu_count

from .config import (
    ALL_METHODS, PLOTTABLE_COLUMNS, STRESS_PAIRS,
)
from .math_utils import calculate_stress_vectorized, safe_filename
from .combination import (
    parse_combination_file, validate_combinations, format_resolution_warnings,
)
from .io_utils import load_csv_inputs, build_coord_dict, resolve_input_files
from .mesh import MeshTopology
from .values import ValueMapper
from .plotting import init_worker, generate_plot_worker
from .reporting import extract_statistics, compute_master_envelope
from .report_writer import write_reports, compile_pdfs


def run(args):
    show_mesh = not args.no_mesh
    thickness = args.thickness

    # Timestamped output
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    timestamp_output = os.path.join(args.output, timestamp)
    os.makedirs(timestamp_output, exist_ok=True)

    print("=" * 60)
    print("SHELL-KIT — KONTUR GAYA DALAM & TEGANGAN")
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

    total_failed = 0

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
        if mesh.n_invalid:
            print(f"  [WARN] {mesh.n_invalid} elemen dilewati "
                  f"(node tidak ada di CSV koordinat).")
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
        # {source_name: {'folder', 'arrays', 'figures'}} — feeds --report
        sources = {}

        def _plot_path(folder, col, suffix):
            """Mirror the filename the worker will write, so reports can link it."""
            return os.path.join(
                folder,
                f"contour_{safe_filename(col)}_{safe_filename(suffix)}.png",
            )

        # Union across ALL load cases — taking only the first one silently
        # dropped columns that happen to be absent from it.
        available_cols = set()
        for vm in value_mapper_cache.values():
            available_cols.update(vm.cached_z.keys())
        cols_to_plot = [c for c in PLOTTABLE_COLUMNS if c in available_cols]

        # --- Load case tasks ---
        for lc in load_cases:
            vm = value_mapper_cache[lc]
            load_folder = os.path.join(method_output, f"Load_{safe_filename(lc)}")
            os.makedirs(load_folder, exist_ok=True)
            entry = sources.setdefault(
                lc, {'folder': load_folder, 'arrays': {}, 'figures': []},
            )

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
                    entry['arrays'][col] = z
                    entry['figures'].append(
                        (f'{col} {suf}'.strip(), _plot_path(load_folder, col, suf))
                    )

        # --- Combination tasks ---
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

        # --comb-select used to exist on rebar and report but not here
        if args.comb_select != ['*'] and valid_combos:
            filtered = [
                c for c in valid_combos
                if any(fnmatch.fnmatch(c['name'], pat) for pat in args.comb_select)
            ]
            print(f"  Filtered: {len(filtered)} / {len(valid_combos)} combinations")
            valid_combos = filtered

        for combo in valid_combos:
            lc_factors = combo['lc_factors']
            combo_name = combo['name']
            combo_folder = os.path.join(method_output, f"Combination_{safe_filename(combo_name)}")
            os.makedirs(combo_folder, exist_ok=True)
            combo_entry = sources.setdefault(
                f"Comb: {combo_name}",
                {'folder': combo_folder, 'arrays': {}, 'figures': []},
            )

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
                    combo_entry['arrays'][col] = z_comb
                    combo_entry['figures'].append(
                        (f'{col} {suf}'.strip(), _plot_path(combo_folder, col, suf))
                    )

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
            total_failed += len(errors)
            print(f"  [WARN] {len(errors)} plots failed:")
            for err in errors[:5]:
                print(f"    - {err.get('task', '?')}: {err.get('error', '?')}")

        # --- Reports (--report) ---
        if args.report and sources:
            print("  [4/4] Menyusun laporan...")
            all_stats = {}
            for name, entry in sources.items():
                if not entry['arrays']:
                    continue
                stats, n_pts = extract_statistics(entry['arrays'], mesh, thickness)
                all_stats[name] = (stats, n_pts)
                entry['stats'] = stats
                entry['n_points'] = n_pts

            written = write_reports(
                sources=all_stats,
                source_meta=sources,
                envelope=compute_master_envelope(all_stats) if all_stats else None,
                thickness=thickness,
                method=method,
                fmt=args.report_format,
                out_folder=method_output,
                generated=set(generated_files),
                run_meta={
                    'title': 'Laporan Kontur Gaya Dalam & Tegangan',
                    'subtitle': f'Metode {method.replace("-", " ").title()}',
                    'rows': [
                        ('Dibuat', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                        ('Tebal pelat', f'{thickness * 1000:.0f} mm'),
                        ('Metode kontur', method.replace('-', ' ').title()),
                        ('Jumlah sumber', str(len(all_stats))),
                        ('Koordinat', os.path.basename(k_file or '-')),
                        ('Konektivitas', os.path.basename(c_file or '-')),
                        ('Gaya', os.path.basename(g_file or '-')),
                    ],
                    'note': 'Dihasilkan oleh shell-kit. Nilai pada dokumen ini '
                            'diinterpolasi mengikuti metode kontur di atas.',
                },
            )
            for path in written:
                print(f"    {os.path.relpath(path, method_output)}")

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
