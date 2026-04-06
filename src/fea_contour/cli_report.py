"""
CLI entry point for FEA Report Generator.
Orchestrates load case processing and report generation.
"""

import os
import sys
import argparse
import pandas as pd
from datetime import datetime

from .config import DEFAULT_THICKNESS, OUTPUT_FOLDER, INPUT_FOLDER
from .math_utils import safe_filename
from .combination import parse_combination_file, validate_combinations
from .reporting import process_load_case, generate_report, generate_master_summary


def main():
    parser = argparse.ArgumentParser(description='FEA Results Summary Report Generator')
    parser.add_argument('--comb', action='store_true', help='Include Load Combinations')
    parser.add_argument('--master', action='store_true', help='Generate Master Summary of all cases')
    parser.add_argument('--thickness', type=float, default=DEFAULT_THICKNESS,
                        help=f'Plate thickness in meters (default: {DEFAULT_THICKNESS})')
    parser.add_argument('--gaya', type=str,
                        default=os.path.join(INPUT_FOLDER, 'gaya_elemen_per_load_case.csv'),
                        help='Path to force/moment CSV')
    parser.add_argument('--kombinasi', type=str,
                        default=os.path.join(INPUT_FOLDER, 'kombinasi_beban.csv'),
                        help='Path to combination CSV')
    parser.add_argument('--output', type=str, default=OUTPUT_FOLDER,
                        help=f'Output base folder (default: {OUTPUT_FOLDER})')
    args = parser.parse_args()

    thickness = args.thickness

    # Create timestamped output folder
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    timestamp_output = os.path.join(args.output, timestamp)
    os.makedirs(timestamp_output, exist_ok=True)

    print("=" * 70)
    print("FEA RESULTS SUMMARY REPORT GENERATOR")
    print("=" * 70)
    print(f"Output Directory: {timestamp_output}")
    print(f"Plate Thickness:  {thickness * 1000:.0f} mm")

    # 1. Read Gaya Data
    gaya_file = args.gaya
    print(f"\nReading {gaya_file}...")
    if not os.path.exists(gaya_file):
        print(f"ERROR: File not found: {gaya_file}")
        return 1

    gaya_df = pd.read_csv(gaya_file, low_memory=False)
    gaya_df.columns = gaya_df.columns.str.strip()

    load_cases_cache = {}
    for lc_name, df_lc in gaya_df.groupby('Load'):
        lc_clean = str(lc_name).strip()
        load_cases_cache[lc_clean] = df_lc

    load_cases = list(load_cases_cache.keys())
    print(f"  OK Loaded {len(gaya_df):,} records across {len(load_cases)} Load Cases.")

    # Store all data for master summary
    all_data = {}

    # 2. Process Load Cases
    print("\nProcessing Load Cases...")
    for lc_name in load_cases:
        print(f"  - {lc_name}")
        elem_grouped = process_load_case(load_cases_cache[lc_name], thickness)
        all_data[lc_name] = elem_grouped

        lc_folder = f"Load_{safe_filename(lc_name)}"
        report_path = os.path.join(
            timestamp_output, lc_folder, f"Summary_{safe_filename(lc_name)}.md",
        )
        generate_report(f"Load Case: {lc_name}", elem_grouped, report_path, thickness)
        elem_grouped.to_csv(
            os.path.join(timestamp_output, lc_folder, f"Data_{safe_filename(lc_name)}.csv"),
        )

    # 3. Process Combinations
    if args.comb:
        print("\nProcessing Load Combinations...")
        kombination_file = args.kombinasi
        combos = parse_combination_file(kombination_file)
        missing, matched_map = validate_combinations(combos, set(load_cases))

        valid_combos = []
        for combo in combos:
            resolved = []
            valid = True
            for lc, fac in combo['lc_factors']:
                actual_lc = matched_map.get(lc, lc)
                if actual_lc in load_cases_cache:
                    resolved.append((actual_lc, fac))
                else:
                    valid = False
            if valid and resolved:
                valid_combos.append({'name': combo['name'], 'lc_factors': resolved})

        print(f"  Found {len(valid_combos)} valid combinations out of {len(combos)}.")

        for combo in valid_combos:
            combo_name = combo['name']

            grouped_combos = {}
            for lc, fac in combo['lc_factors']:
                if lc not in grouped_combos:
                    grouped_combos[lc] = process_load_case(load_cases_cache[lc], thickness)

            total_grouped = grouped_combos[combo['lc_factors'][0][0]] * combo['lc_factors'][0][1]
            for lc, fac in combo['lc_factors'][1:]:
                total_grouped = total_grouped.add(grouped_combos[lc] * fac, fill_value=0)

            all_data[f"Comb: {combo_name}"] = total_grouped

            combo_folder = f"Combination_{safe_filename(combo_name)}"
            report_path = os.path.join(
                timestamp_output, combo_folder, f"Summary_{safe_filename(combo_name)}.md",
            )
            generate_report(f"Combination: {combo_name}", total_grouped, report_path, thickness)
            total_grouped.to_csv(
                os.path.join(timestamp_output, combo_folder, f"Data_{safe_filename(combo_name)}.csv"),
            )
            print(f"  OK Generated report for {combo_name}")

    # 4. Generate Master Summary
    if args.master:
        print("\nGenerating Master Summary...")
        master_path = generate_master_summary(all_data, timestamp_output, thickness)
        print(f"  OK Master Summary generated: {master_path}")

    print("\n[SUCCESS] All reports generated.")
    return 0


def entry_point():
    """Console script entry point (called by pyproject.toml [project.scripts])."""
    import sys
    sys.exit(main())
