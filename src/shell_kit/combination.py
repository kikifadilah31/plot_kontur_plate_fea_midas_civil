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


def resolve_load_case(lc, available_sorted):
    """
    Resolve a combination's load case name against the available names.

    Matching is tiered, and every tier scans a SORTED list so the result never
    depends on set iteration order (Python randomises string hashing per
    process, which previously made resolution vary between runs).

    Tiers, most to least trustworthy:
      1. exact match
      2. equal after dropping a parenthetical suffix — 'EQ_X_POS(RS)' → 'EQ_X_POS'
      3. prefix match
      4. substring match anywhere (kept only so existing combination files
         keep working; always reported as a guess)

    Parameters
    ----------
    lc : str
        Load case name as written in the combination file.
    available_sorted : list of str
        Sorted list of load case names present in the force CSV.

    Returns
    -------
    tuple of (resolved_name or None, tier, candidates)
        tier: 1-4 as above, or 0 when unresolved.
        candidates: all names matched at the winning tier — more than one
        means the choice was ambiguous.
    """
    if lc in available_sorted:
        return lc, 1, [lc]

    tiers = (
        [a for a in available_sorted if a.split('(')[0].strip() == lc],
        [a for a in available_sorted if a.startswith(lc)],
        [a for a in available_sorted if lc in a],
    )
    for offset, candidates in enumerate(tiers, start=2):
        if candidates:
            return candidates[0], offset, candidates

    return None, 0, []


def validate_combinations(combos, available_lcs):
    """
    Validate combinations against available load cases.

    Parameters
    ----------
    combos : list of dict
        Parsed combinations from parse_combination_file().
    available_lcs : iterable of str
        Available load case names.

    Returns
    -------
    tuple of (missing, matched_map, uncertain)
        - missing: list of (combo_name, lc_name) for unresolvable load cases
        - matched_map: dict mapping original name → resolved name
        - uncertain: list of (lc_name, resolved, tier, candidates) for every
          name that was not an exact match, so callers can warn the user
    """
    available_sorted = sorted(available_lcs)
    missing = []
    matched_map = {}
    uncertain = []
    seen = set()

    for combo in combos:
        for lc, _ in combo['lc_factors']:
            if lc in available_sorted or lc in seen:
                continue
            seen.add(lc)

            resolved, tier, candidates = resolve_load_case(lc, available_sorted)
            if resolved is None:
                missing.append((combo['name'], lc))
            else:
                matched_map[lc] = resolved
                uncertain.append((lc, resolved, tier, candidates))

    return missing, matched_map, uncertain


def format_resolution_warnings(uncertain):
    """
    Turn the `uncertain` list from validate_combinations() into printable lines.

    Returns an empty list when every name matched exactly.
    """
    tier_desc = {
        2: 'suffix dropped',
        3: 'prefix match',
        4: 'substring match',
    }
    lines = []
    for lc, resolved, tier, candidates in uncertain:
        note = tier_desc.get(tier, 'guess')
        line = f"    '{lc}' -> '{resolved}' ({note})"
        if len(candidates) > 1:
            others = ', '.join(repr(c) for c in candidates[1:])
            line += f"  [AMBIGUOUS: also matched {others}]"
        lines.append(line)
    return lines
