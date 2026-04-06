"""
Load combination parsing and validation — single source of truth.
Eliminates duplication between plotter and reporter.
"""

import os
import pandas as pd


def parse_combination_file(csv_path):
    """
    Parse a load combination CSV file into a list of combination dicts.

    Each combination dict has:
      - 'name': str — combination name
      - 'lc_factors': list of (load_case_name, factor) tuples

    Parameters
    ----------
    csv_path : str
        Path to the combination CSV file.

    Returns
    -------
    list of dict
    """
    if not os.path.exists(csv_path):
        return []

    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = df.columns.str.strip()

    combos = []
    case_cols = [c for c in df.columns if c.startswith('Case ') and c.split()[-1].isdigit()]
    case_nums = sorted([int(c.split()[-1]) for c in case_cols])
    factor_cols = [c for c in df.columns if c.startswith('Factor')]

    for _, row in df.iterrows():
        name = str(row.get('Name', '')).strip()
        active = str(row.get('Active', '')).strip()
        if not name or active != 'Active':
            continue

        lc_factors = []
        for i, num in enumerate(case_nums):
            lc_col = f'Case {num}'
            f_col = factor_cols[i] if i < len(factor_cols) else None
            if lc_col not in df.columns:
                continue

            lc = str(row[lc_col]).strip()
            factor = 1.0
            if f_col and f_col in df.columns:
                try:
                    factor = float(row[f_col])
                except (ValueError, TypeError):
                    factor = 1.0

            if lc and lc.lower() not in ['nan', 'none', '']:
                lc_factors.append((lc, factor))

        if lc_factors:
            combos.append({'name': name, 'lc_factors': lc_factors})

    return combos


def validate_combinations(combos, available_lcs):
    """
    Validate combinations against available load cases.
    Includes fuzzy matching for '(RS)' suffix.

    Parameters
    ----------
    combos : list of dict
        Parsed combinations from parse_combination_file().
    available_lcs : set of str
        Set of available load case names.

    Returns
    -------
    tuple of (missing, matched_map)
        - missing: list of (combo_name, lc_name) for unresolvable load cases
        - matched_map: dict mapping original name → resolved name
    """
    missing = []
    matched_map = {}

    for combo in combos:
        for lc, _ in combo['lc_factors']:
            if lc not in available_lcs:
                matched = next(
                    (a for a in available_lcs if lc in a or a.replace('(RS)', '') == lc),
                    None
                )
                if matched:
                    matched_map[lc] = matched
                else:
                    missing.append((combo['name'], lc))

    return missing, matched_map
