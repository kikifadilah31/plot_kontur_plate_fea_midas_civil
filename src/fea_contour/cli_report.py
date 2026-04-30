"""
CLI entry point for FEA Report Generator.
Orchestrates load case processing and report generation
using the same mesh-interpolated pipeline as fea-plot/fea-rebar.
"""

import os
import sys
import argparse
import fnmatch
import numpy as np
from datetime import datetime

from . import __version__

from .config import (
    DEFAULT_THICKNESS, ALL_METHODS, FORCE_COLUMNS,
    OUTPUT_FOLDER,
)
from .math_utils import safe_filename
from .combination import parse_combination_file, validate_combinations
from .io_utils import load_csv_inputs, build_coord_dict, resolve_input_files
from .mesh import MeshTopology
from .values import ValueMapper
from .reporting import extract_statistics, compute_master_envelope, render_report_md, render_master_md
from .reporting_typst import render_report_typst, render_master_typst


def _get_column_arrays(value_mapper):
    """Extract all non-zero column arrays from a ValueMapper."""
    arrays = {}
    for col in FORCE_COLUMNS:
        z = value_mapper.get_z_array(col)
        if not np.all(z == 0):
            arrays[col] = z
    return arrays


def _superpose_arrays(value_mapper_cache, lc_factors):
    """Superpose Z-arrays for a load combination."""
    ref_lc = lc_factors[0][0]
    arrays = {}
    for col in FORCE_COLUMNS:
        z_comb = np.zeros_like(value_mapper_cache[ref_lc].get_z_array(col))
        for lc, fac in lc_factors:
            z_comb += fac * value_mapper_cache[lc].get_z_array(col)
        if not np.all(z_comb == 0):
            arrays[col] = z_comb
    return arrays


def _write_report(content, output_path):
    """Write report content to file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return output_path


def main():
    parser = argparse.ArgumentParser(description='FEA Results Summary Report Generator')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    parser.add_argument('--kordinat', type=str, help='Path to coordinate CSV')
    parser.add_argument('--connectivity', type=str, help='Path to connectivity CSV')
    parser.add_argument('--gaya', type=str, help='Path to force/moment CSV')
    parser.add_argument('--thickness', type=float, default=DEFAULT_THICKNESS,
                        help=f'Plate thickness in meters (default: {DEFAULT_THICKNESS})')
    parser.add_argument('--method', type=str,
                        choices=['average-nodal', 'element-nodal', 'element-center', 'all'],
                        default='average-nodal',
                        help='Contour method for interpolation (default: average-nodal)')
    parser.add_argument('--format', type=str, choices=['md', 'typst'], default='md',
                        help='Output format: md (Markdown) or typst (default: md)')
    parser.add_argument('--comb', type=str, default='',
                        help='Path to load combination CSV')
    parser.add_argument('--comb-select', type=str, nargs='*', default=['*'],
                        help='Filter combination names by wildcard pattern (default: * = all)')
    parser.add_argument('--master', action='store_true',
                        help='Generate Master Summary of all cases')
    parser.add_argument('--output', type=str, default=OUTPUT_FOLDER,
                        help=f'Output base folder (default: {OUTPUT_FOLDER})')
    args = parser.parse_args()

    thickness = args.thickness
    fmt = args.format
    ext = '.typ' if fmt == 'typst' else '.md'

    # Timestamped output
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    timestamp_output = os.path.join(args.output, f"report_{timestamp}")
    os.makedirs(timestamp_output, exist_ok=True)

    print("=" * 60)
    print("FEA RESULTS SUMMARY REPORT GENERATOR")
    print("=" * 60)
    print(f"Output Directory: {timestamp_output}")
    print(f"Plate Thickness:  {thickness * 1000:.0f} mm")
    print(f"Output Format:    {fmt.upper()}")

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

    print(f"Methods to run: {len(methods_to_run)} | Load Cases: {len(load_cases)}")

    for method in methods_to_run:
        print(f"\nProcessing Method: {method.upper()}")
        method_output = (
            os.path.join(timestamp_output, f"Method_{safe_filename(method)}")
            if args.method == 'all'
            else timestamp_output
        )

        # --- Build MeshTopology + ValueMappers ---
        print("  [1/3] Building Mesh & Value Mappers...")
        mesh = MeshTopology(df_conn, coord_dict, method)
        value_mapper_cache = {}

        for lc in load_cases:
            df_lc = df_gaya[df_gaya['Load'] == lc].copy()
            value_mapper_cache[lc] = ValueMapper(df_lc, mesh)

        # --- Generate Reports ---
        print("  [2/3] Generating Reports...")
        all_stats = {}
        report_count = 0

        # Process individual load cases
        if not use_combos:
            for lc in load_cases:
                vm = value_mapper_cache[lc]
                col_arrays = _get_column_arrays(vm)
                if not col_arrays:
                    continue

                stats, n_pts = extract_statistics(col_arrays, mesh, thickness)
                all_stats[lc] = (stats, n_pts)

                lc_folder = f"Load_{safe_filename(lc)}"
                report_name = f"Summary_{safe_filename(lc)}{ext}"
                report_path = os.path.join(method_output, lc_folder, report_name)

                if fmt == 'typst':
                    content = render_report_typst(f"Load Case: {lc}", stats, n_pts, thickness, method)
                else:
                    content = render_report_md(f"Load Case: {lc}", stats, n_pts, thickness, method)

                _write_report(content, report_path)
                report_count += 1
                print(f"    [{report_count}] {lc}")
        else:
            # Process load combinations
            _, matched_map = validate_combinations(combos, set(load_cases))
            valid_combos = []
            for combo in combos:
                resolved = []
                is_valid = True
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
                combo_name = combo['name']
                col_arrays = _superpose_arrays(value_mapper_cache, combo['lc_factors'])
                if not col_arrays:
                    continue

                stats, n_pts = extract_statistics(col_arrays, mesh, thickness)
                all_stats[f"Comb: {combo_name}"] = (stats, n_pts)

                combo_folder = f"Combination_{safe_filename(combo_name)}"
                report_name = f"Summary_{safe_filename(combo_name)}{ext}"
                report_path = os.path.join(method_output, combo_folder, report_name)

                if fmt == 'typst':
                    content = render_report_typst(f"Combination: {combo_name}", stats, n_pts, thickness, method)
                else:
                    content = render_report_md(f"Combination: {combo_name}", stats, n_pts, thickness, method)

                _write_report(content, report_path)
                report_count += 1
                print(f"    [{report_count}] {combo_name}")

        # --- Master Summary ---
        if args.master and all_stats:
            print("  [3/3] Generating Master Summary...")
            envelope = compute_master_envelope(all_stats)
            master_name = f"MASTER_SUMMARY{ext}"
            master_path = os.path.join(method_output, master_name)

            if fmt == 'typst':
                content = render_master_typst(envelope, thickness, method)
            else:
                content = render_master_md(envelope, thickness, method)

            _write_report(content, master_path)
            print(f"    Master Summary: {master_path}")
        else:
            print("  [3/3] Master Summary: Skipped (use --master to enable)")

        print(f"  [OK] Generated {report_count} reports for method {method}.")

    print(f"\n[SUCCESS] All reports generated.")
    return 0


def entry_point():
    """Console script entry point (called by pyproject.toml [project.scripts])."""
    import sys
    sys.exit(main())
