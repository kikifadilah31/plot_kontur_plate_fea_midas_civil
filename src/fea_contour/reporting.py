"""
Reporting engine — Markdown report generation and Master Summary.
"""

import os
import numpy as np
from datetime import datetime

from .config import FORCE_COLUMNS, STRESS_COLUMNS, STRESS_PAIRS, STRIP_WIDTH
from .math_utils import calculate_stress_vectorized, safe_filename, format_value


def process_load_case(gaya_df, thickness):
    """
    Process a single load case: group by element, calculate stresses.

    Parameters
    ----------
    gaya_df : DataFrame
        Force/moment data for a single load case.
    thickness : float
        Plate thickness in meters.

    Returns
    -------
    DataFrame — element-grouped with stress columns added.
    """
    available_force_cols = [c for c in FORCE_COLUMNS if c in gaya_df.columns]
    elem_grouped = gaya_df.groupby('Elem')[available_force_cols].mean()

    if 'Fxx (kN/m)' in elem_grouped.columns and 'Mxx (kN·m/m)' in elem_grouped.columns:
        top, bot = calculate_stress_vectorized(
            elem_grouped['Fxx (kN/m)'].values,
            elem_grouped['Mxx (kN·m/m)'].values,
            thickness,
        )
        elem_grouped['Sig-xx_Top (kPa)'] = top
        elem_grouped['Sig-xx_Bottom (kPa)'] = bot

    if 'Fyy (kN/m)' in elem_grouped.columns and 'Myy (kN·m/m)' in elem_grouped.columns:
        top, bot = calculate_stress_vectorized(
            elem_grouped['Fyy (kN/m)'].values,
            elem_grouped['Myy (kN·m/m)'].values,
            thickness,
        )
        elem_grouped['Sig-yy_Top (kPa)'] = top
        elem_grouped['Sig-yy_Bottom (kPa)'] = bot

    return elem_grouped


def generate_report(title, elem_grouped, output_path, thickness):
    """
    Generate a single Markdown report for a load case or combination.

    Parameters
    ----------
    title : str
    elem_grouped : DataFrame
    output_path : str
    thickness : float
    """
    force_cols = [c for c in FORCE_COLUMNS if c in elem_grouped.columns]
    stress_cols = [c for c in STRESS_COLUMNS if c in elem_grouped.columns]

    report = []
    report.append(f"# FEA Results Summary - {title}")
    report.append("")
    report.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    report.append(f"**Plate Thickness:** {thickness * 1000:.0f} mm")
    report.append(f"**Analysis Strip Width:** {STRIP_WIDTH:.1f} m")
    report.append("")
    report.append(f"**Total Elements:** {len(elem_grouped):,}")
    report.append("")

    # Section Properties
    report.append("## Section Properties")
    report.append("")
    report.append("| Parameter | Value | Unit |")
    report.append("|-----------|-------|------|")
    area = thickness * STRIP_WIDTH
    inertia = (STRIP_WIDTH * thickness ** 3) / 12
    report.append(f"| Area (A) | {area:.6f} | m² |")
    report.append(f"| Inertia (I) | {inertia:.6f} | m⁴ |")
    report.append("")

    # Force Summary
    for col in force_cols:
        report.append(f"### {col}")
        report.append("")
        report.append("| Statistic | Value | Element ID |")
        report.append("|-----------|-------|------------|")
        report.append(f"| **Maximum** | {format_value(elem_grouped[col].max())} | {elem_grouped[col].idxmax()} |")
        report.append(f"| **Minimum** | {format_value(elem_grouped[col].min())} | {elem_grouped[col].idxmin()} |")
        report.append(f"| Mean | {format_value(elem_grouped[col].mean())} | - |")
        report.append("")

    # Stress Summary
    if stress_cols:
        report.append("## Stress Summary (kPa)")
        report.append("")
        report.append("*Sign Convention: Positive Moment → Top Compression (-), Bottom Tension (+)*")
        report.append("")

        for col in stress_cols:
            report.append(f"### {col}")
            report.append("")
            report.append("| Statistic | Value | Element ID |")
            report.append("|-----------|-------|------------|")
            report.append(f"| **Maximum** | {format_value(elem_grouped[col].max())} | {elem_grouped[col].idxmax()} |")
            report.append(f"| **Minimum** | {format_value(elem_grouped[col].min())} | {elem_grouped[col].idxmin()} |")
            report.append(f"| Mean | {format_value(elem_grouped[col].mean())} | - |")
            report.append("")

    # Critical Elements Analysis
    report.append("## Critical Elements Analysis")
    report.append("")

    if 'Sig-xx_Top (kPa)' in stress_cols:
        idx = elem_grouped['Sig-xx_Top (kPa)'].idxmax()
        report.append(f"**Sig-xx_Top Maximum - Element {idx}**")
        report.append(f"- **Stress:** {format_value(elem_grouped.loc[idx, 'Sig-xx_Top (kPa)'])} kPa")
        if 'Fxx (kN/m)' in elem_grouped.columns:
            report.append(f"- Contributing: Fxx = {format_value(elem_grouped.loc[idx, 'Fxx (kN/m)'])} kN/m")
        if 'Mxx (kN·m/m)' in elem_grouped.columns:
            report.append(f"- Contributing: Mxx = {format_value(elem_grouped.loc[idx, 'Mxx (kN·m/m)'])} kN·m/m")
        report.append("")

    if 'Sig-yy_Top (kPa)' in stress_cols:
        idx = elem_grouped['Sig-yy_Top (kPa)'].idxmax()
        report.append(f"**Sig-yy_Top Maximum - Element {idx}**")
        report.append(f"- **Stress:** {format_value(elem_grouped.loc[idx, 'Sig-yy_Top (kPa)'])} kPa")
        if 'Fyy (kN/m)' in elem_grouped.columns:
            report.append(f"- Contributing: Fyy = {format_value(elem_grouped.loc[idx, 'Fyy (kN/m)'])} kN/m")
        if 'Myy (kN·m/m)' in elem_grouped.columns:
            report.append(f"- Contributing: Myy = {format_value(elem_grouped.loc[idx, 'Myy (kN·m/m)'])} kN·m/m")
        report.append("")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    return output_path


def generate_master_summary(all_data, output_folder, thickness):
    """
    Generate Master Summary Markdown combining all load cases and combinations.

    Parameters
    ----------
    all_data : dict
        {source_name: elem_grouped_df}
    output_folder : str
    thickness : float
    """
    report = []
    report.append("# FEA Master Summary - All Load Cases & Combinations")
    report.append("")
    report.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    total_lc = len([k for k in all_data if not k.startswith("Comb:")])
    total_combo = len([k for k in all_data if k.startswith("Comb:")])
    report.append(f"**Total Items Analyzed:** {len(all_data)} ({total_lc} Load Cases + {total_combo} Combinations)")
    report.append(f"**Plate Thickness:** {thickness * 1000:.0f} mm | **Strip Width:** {STRIP_WIDTH:.1f} m")
    report.append("")
    report.append("---")
    report.append("")

    # 1. Global Stress Envelope
    report.append("## Global Stress Envelope")
    report.append("")

    stress_cols = [c for c in STRESS_COLUMNS]
    global_stress_list = []

    for source_name, df in all_data.items():
        for col in stress_cols:
            if col not in df.columns:
                continue

            # MAX entry
            max_idx = df[col].idxmax()
            max_val = df[col].max()
            entry = {
                'Source': source_name, 'Column': col,
                'Value': max_val, 'Elem_ID': max_idx, 'Type': 'MAX',
            }
            if 'xx' in col and 'Fxx (kN/m)' in df.columns:
                entry['F'] = df.loc[max_idx, 'Fxx (kN/m)']
                entry['M'] = df.loc[max_idx, 'Mxx (kN·m/m)']
            elif 'yy' in col and 'Fyy (kN/m)' in df.columns:
                entry['F'] = df.loc[max_idx, 'Fyy (kN/m)']
                entry['M'] = df.loc[max_idx, 'Myy (kN·m/m)']
            global_stress_list.append(entry)

            # MIN entry
            min_idx = df[col].idxmin()
            min_val = df[col].min()
            entry_min = {
                'Source': source_name, 'Column': col,
                'Value': min_val, 'Elem_ID': min_idx, 'Type': 'MIN',
            }
            if 'xx' in col and 'Fxx (kN/m)' in df.columns:
                entry_min['F'] = df.loc[min_idx, 'Fxx (kN/m)']
                entry_min['M'] = df.loc[min_idx, 'Mxx (kN·m/m)']
            elif 'yy' in col and 'Fyy (kN/m)' in df.columns:
                entry_min['F'] = df.loc[min_idx, 'Fyy (kN/m)']
                entry_min['M'] = df.loc[min_idx, 'Myy (kN·m/m)']
            global_stress_list.append(entry_min)

    global_stress_list.sort(key=lambda x: abs(x['Value']), reverse=True)

    report.append("### Top 20 Absolute Maximum Stresses (All Sources)")
    report.append("")
    report.append("| Rank | Source | Stress Col | Value (kPa) | Element | Contributing F (kN/m) | Contributing M (kN·m/m) |")
    report.append("|------|--------|------------|-------------|---------|-----------------------|-------------------------|")

    for i, entry in enumerate(global_stress_list[:20], 1):
        f_val = entry.get('F', 'N/A')
        m_val = entry.get('M', 'N/A')
        f_str = format_value(f_val) if isinstance(f_val, float) else f_val
        m_str = format_value(m_val) if isinstance(m_val, float) else m_val
        report.append(
            f"| {i} | {entry['Source']} | {entry['Column']} | "
            f"{format_value(entry['Value'])} | {entry['Elem_ID']} | {f_str} | {m_str} |"
        )

    report.append("")
    report.append("---")
    report.append("")

    # 2. Detailed Breakdown per Stress Type
    for col in stress_cols:
        report.append(f"### {col} - Detailed Extremes")
        report.append("")
        report.append("| Type | Value (kPa) | Element | Source | Contributing Force | Contributing Moment |")
        report.append("|------|-------------|---------|--------|--------------------|---------------------|")

        candidates = []
        for source_name, df in all_data.items():
            if col in df.columns:
                candidates.append((source_name, df[col].max(), df[col].idxmax()))
                candidates.append((source_name, df[col].min(), df[col].idxmin()))

        candidates.sort(key=lambda x: abs(x[1]), reverse=True)

        if candidates:
            best_max = max(candidates, key=lambda x: x[1])
            best_min = min(candidates, key=lambda x: x[1])

            for label, (src, val, idx) in [("**Global Max**", best_max), ("**Global Min**", best_min)]:
                df_src = all_data[src]
                if 'xx' in col:
                    f_v = df_src.loc[idx, 'Fxx (kN/m)'] if 'Fxx (kN/m)' in df_src.columns else 'N/A'
                    m_v = df_src.loc[idx, 'Mxx (kN·m/m)'] if 'Mxx (kN·m/m)' in df_src.columns else 'N/A'
                elif 'yy' in col:
                    f_v = df_src.loc[idx, 'Fyy (kN/m)'] if 'Fyy (kN/m)' in df_src.columns else 'N/A'
                    m_v = df_src.loc[idx, 'Myy (kN·m/m)'] if 'Myy (kN·m/m)' in df_src.columns else 'N/A'
                else:
                    f_v = m_v = 'N/A'
                f_str = format_value(f_v) if isinstance(f_v, float) else f_v
                m_str = format_value(m_v) if isinstance(m_v, float) else m_v
                report.append(f"| {label} | {format_value(val)} | {idx} | {src} | {f_str} | {m_str} |")
            report.append("")

    # 3. Global Force/Moment Envelope
    report.append("---")
    report.append("")
    report.append("## Global Force & Moment Envelope")
    report.append("")

    force_moment_cols = [
        ('Fxx (kN/m)', 'Axial Force X', 'kN/m'),
        ('Fyy (kN/m)', 'Axial Force Y', 'kN/m'),
        ('Mxx (kN·m/m)', 'Moment X', 'kN·m/m'),
        ('Myy (kN·m/m)', 'Moment Y', 'kN·m/m'),
        ('Vxx (kN/m)', 'Shear Force X', 'kN/m'),
        ('Vyy (kN/m)', 'Shear Force Y', 'kN/m'),
    ]

    for col_name, desc, unit in force_moment_cols:
        report.append(f"### {desc} ({unit})")
        report.append("")
        report.append("| Rank | Source | Value | Element | Contributing Stress |")
        report.append("|------|--------|-------|---------|---------------------|")

        candidates = []
        for source_name, df in all_data.items():
            if col_name in df.columns:
                candidates.append((source_name, df[col_name].max(), df[col_name].idxmax()))
                candidates.append((source_name, df[col_name].min(), df[col_name].idxmin()))

        candidates.sort(key=lambda x: abs(x[1]), reverse=True)

        for i, (src, val, idx) in enumerate(candidates[:5], 1):
            df_src = all_data[src]
            stress_val = 'N/A'
            if 'xx' in col_name and 'Sig-xx_Top (kPa)' in df_src.columns:
                stress_val = format_value(df_src.loc[idx, 'Sig-xx_Top (kPa)'])
            elif 'yy' in col_name and 'Sig-yy_Top (kPa)' in df_src.columns:
                stress_val = format_value(df_src.loc[idx, 'Sig-yy_Top (kPa)'])
            report.append(f"| {i} | {src} | {format_value(val)} | {idx} | {stress_val} |")
        report.append("")

    # 4. Critical Element Identification
    report.append("---")
    report.append("")
    report.append("## Critical Element Identification")
    report.append("")
    report.append("*Elements that appear most frequently in top 5 extremes.*")
    report.append("")

    element_counts = {}
    all_check_cols = force_moment_cols + [(c, c, 'kPa') for c in stress_cols]
    for col_check, _, _ in all_check_cols:
        candidates = []
        for source_name, df in all_data.items():
            if col_check in df.columns:
                candidates.append((df[col_check].max(), df[col_check].idxmax()))
                candidates.append((df[col_check].min(), df[col_check].idxmin()))
        candidates.sort(key=lambda x: abs(x[0]), reverse=True)
        for val, idx in candidates[:5]:
            element_counts[idx] = element_counts.get(idx, 0) + 1

    if element_counts:
        sorted_elems = sorted(element_counts.items(), key=lambda x: x[1], reverse=True)
        report.append("| Rank | Element ID | Appearances |")
        report.append("|------|------------|-------------|")
        for i, (elem, count) in enumerate(sorted_elems[:20], 1):
            report.append(f"| {i} | {elem} | {count} |")
        report.append("")

    report_path = os.path.join(output_folder, "MASTER_SUMMARY.md")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    return report_path


# =============================================================================
# NEW: Mesh-interpolated statistics extraction + rendering (v1.3)
# =============================================================================

def _format_loc(loc, elem_id=None):
    """Format location for display: (x, y) or Elem ID (x, y)."""
    x, y = loc
    if elem_id is not None:
        return f"Elem {elem_id} ({x:.2f}, {y:.2f})"
    return f"({x:.2f}, {y:.2f})"


def extract_statistics(column_arrays, mesh, thickness):
    """
    Extract statistical summary from mesh-interpolated Z-arrays.

    Parameters
    ----------
    column_arrays : dict
        {column_name: np.ndarray} — pre-computed Z-arrays from ValueMapper
        or superposed combination arrays.
    mesh : MeshTopology
        The mesh used for interpolation.
    thickness : float
        Plate thickness in meters.

    Returns
    -------
    tuple : (stats_dict, n_points)
        stats_dict: {column_name: {max, min, mean, max_loc, min_loc, ...}}
        n_points: int — number of data points in the arrays
    """
    is_center = mesh.method == 'element-center'

    if is_center:
        cx = np.array([c[0] for c in mesh.centroids])
        cy = np.array([c[1] for c in mesh.centroids])
        elem_ids = mesh.valid_elem_ids
    else:
        cx, cy = mesh.x, mesh.y
        elem_ids = None

    n_points = len(cx)
    stats = {}

    def _stat_entry(z, f_arr=None, m_arr=None):
        """Build a stat entry for one Z-array."""
        max_idx = int(np.argmax(z))
        min_idx = int(np.argmin(z))
        entry = {
            'max': float(z[max_idx]),
            'min': float(z[min_idx]),
            'mean': float(np.mean(z)),
            'max_loc': (float(cx[max_idx]), float(cy[max_idx])),
            'min_loc': (float(cx[min_idx]), float(cy[min_idx])),
        }
        if elem_ids is not None:
            entry['max_elem'] = int(elem_ids[max_idx])
            entry['min_elem'] = int(elem_ids[min_idx])
        if f_arr is not None:
            entry['max_F'] = float(f_arr[max_idx])
            entry['min_F'] = float(f_arr[min_idx])
        if m_arr is not None:
            entry['max_M'] = float(m_arr[max_idx])
            entry['min_M'] = float(m_arr[min_idx])
        return entry

    # Force/moment columns
    for col in FORCE_COLUMNS:
        z = column_arrays.get(col)
        if z is None or len(z) == 0 or np.all(z == 0):
            continue
        stats[col] = _stat_entry(z)

    # Compute stress from interpolated force/moment arrays
    stress_cache = {}
    for stress_col, (force_col, moment_col) in STRESS_PAIRS.items():
        f_arr = column_arrays.get(force_col)
        m_arr = column_arrays.get(moment_col)
        if f_arr is None or m_arr is None:
            continue

        pair_key = (force_col, moment_col)
        if pair_key not in stress_cache:
            top, bot = calculate_stress_vectorized(f_arr, m_arr, thickness)
            stress_cache[pair_key] = (top, bot)

        top, bot = stress_cache[pair_key]
        z = top if 'Top' in stress_col else bot
        stats[stress_col] = _stat_entry(z, f_arr, m_arr)

    return stats, n_points


def compute_master_envelope(all_stats):
    """
    Aggregate per-source statistics into master envelope data.

    Parameters
    ----------
    all_stats : dict
        {source_name: (stats_dict, n_points)}

    Returns
    -------
    dict with keys: stress_entries, force_entries, total_sources, total_lc, total_combo
    """
    stress_entries = []
    force_entries = []

    stress_col_set = set(STRESS_COLUMNS)

    for source_name, (stats, _n_pts) in all_stats.items():
        for col, entry in stats.items():
            is_stress = col in stress_col_set

            max_item = {
                'source': source_name, 'col': col, 'type': 'MAX',
                'value': entry['max'], 'loc': entry['max_loc'],
            }
            min_item = {
                'source': source_name, 'col': col, 'type': 'MIN',
                'value': entry['min'], 'loc': entry['min_loc'],
            }
            if 'max_elem' in entry:
                max_item['elem'] = entry['max_elem']
                min_item['elem'] = entry['min_elem']
            if 'max_F' in entry:
                max_item['F'] = entry['max_F']
                max_item['M'] = entry['max_M']
                min_item['F'] = entry['min_F']
                min_item['M'] = entry['min_M']

            if is_stress:
                stress_entries.extend([max_item, min_item])
            else:
                force_entries.extend([max_item, min_item])

    stress_entries.sort(key=lambda x: abs(x['value']), reverse=True)
    force_entries.sort(key=lambda x: abs(x['value']), reverse=True)

    return {
        'stress_entries': stress_entries,
        'force_entries': force_entries,
        'total_sources': len(all_stats),
        'total_lc': len([k for k in all_stats if not k.startswith('Comb:')]),
        'total_combo': len([k for k in all_stats if k.startswith('Comb:')]),
    }


def render_report_md(title, stats, n_points, thickness, method):
    """
    Render a single-source report as Markdown string.

    Parameters
    ----------
    title : str
    stats : dict — output of extract_statistics()
    n_points : int
    thickness : float
    method : str

    Returns
    -------
    str — complete Markdown content
    """
    rpt = []
    rpt.append(f"# FEA Results Summary - {title}")
    rpt.append("")
    rpt.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    rpt.append("")
    rpt.append(f"**Plate Thickness:** {thickness * 1000:.0f} mm")
    rpt.append(f"**Analysis Strip Width:** {STRIP_WIDTH:.1f} m")
    rpt.append(f"**Contour Method:** {method.replace('-', ' ').title()}")
    rpt.append(f"**Total Data Points:** {n_points:,}")
    rpt.append("")

    # Section Properties
    rpt.append("## Section Properties")
    rpt.append("")
    rpt.append("| Parameter | Value | Unit |")
    rpt.append("|-----------|-------|------|")
    area = thickness * STRIP_WIDTH
    inertia = (STRIP_WIDTH * thickness ** 3) / 12
    rpt.append(f"| Area (A) | {area:.6f} | m\u00b2 |")
    rpt.append(f"| Inertia (I) | {inertia:.6f} | m\u2074 |")
    rpt.append("")

    # Force/Moment Summary
    force_cols = [c for c in FORCE_COLUMNS if c in stats]
    if force_cols:
        rpt.append("## Force & Moment Summary")
        rpt.append("")
        for col in force_cols:
            e = stats[col]
            rpt.append(f"### {col}")
            rpt.append("")
            rpt.append("| Statistic | Value | Location |")
            rpt.append("|-----------|-------|----------|")
            rpt.append(f"| **Maximum** | {format_value(e['max'])} | {_format_loc(e['max_loc'], e.get('max_elem'))} |")
            rpt.append(f"| **Minimum** | {format_value(e['min'])} | {_format_loc(e['min_loc'], e.get('min_elem'))} |")
            rpt.append(f"| Mean | {format_value(e['mean'])} | - |")
            rpt.append("")

    # Stress Summary
    stress_cols = [c for c in STRESS_COLUMNS if c in stats]
    if stress_cols:
        rpt.append("## Stress Summary (kPa)")
        rpt.append("")
        rpt.append("*Sign Convention: Positive Moment -> Top Compression (-), Bottom Tension (+)*")
        rpt.append("")
        for col in stress_cols:
            e = stats[col]
            rpt.append(f"### {col}")
            rpt.append("")
            rpt.append("| Statistic | Value | Location | F (kN/m) | M (kN.m/m) |")
            rpt.append("|-----------|-------|----------|----------|------------|")
            f_max = format_value(e['max_F']) if 'max_F' in e else '-'
            m_max = format_value(e['max_M']) if 'max_M' in e else '-'
            f_min = format_value(e['min_F']) if 'min_F' in e else '-'
            m_min = format_value(e['min_M']) if 'min_M' in e else '-'
            rpt.append(f"| **Maximum** | {format_value(e['max'])} | {_format_loc(e['max_loc'], e.get('max_elem'))} | {f_max} | {m_max} |")
            rpt.append(f"| **Minimum** | {format_value(e['min'])} | {_format_loc(e['min_loc'], e.get('min_elem'))} | {f_min} | {m_min} |")
            rpt.append(f"| Mean | {format_value(e['mean'])} | - | - | - |")
            rpt.append("")

    return '\n'.join(rpt)


def render_master_md(envelope, thickness, method):
    """
    Render master summary as Markdown string.

    Parameters
    ----------
    envelope : dict — output of compute_master_envelope()
    thickness : float
    method : str

    Returns
    -------
    str — complete Markdown content
    """
    rpt = []
    rpt.append("# FEA Master Summary - All Load Cases & Combinations")
    rpt.append("")
    rpt.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    rpt.append("")
    rpt.append(f"**Total Items Analyzed:** {envelope['total_sources']} "
               f"({envelope['total_lc']} Load Cases + {envelope['total_combo']} Combinations)")
    rpt.append(f"**Plate Thickness:** {thickness * 1000:.0f} mm | "
               f"**Strip Width:** {STRIP_WIDTH:.1f} m | "
               f"**Method:** {method.replace('-', ' ').title()}")
    rpt.append("")
    rpt.append("---")
    rpt.append("")

    # 1. Global Stress Envelope — Top 20
    rpt.append("## Global Stress Envelope")
    rpt.append("")
    rpt.append("### Top 20 Absolute Maximum Stresses (All Sources)")
    rpt.append("")
    rpt.append("| Rank | Source | Stress Col | Value (kPa) | Location | F (kN/m) | M (kN.m/m) |")
    rpt.append("|------|--------|------------|-------------|----------|----------|------------|")

    for i, e in enumerate(envelope['stress_entries'][:20], 1):
        f_str = format_value(e['F']) if 'F' in e else '-'
        m_str = format_value(e['M']) if 'M' in e else '-'
        loc_str = _format_loc(e['loc'], e.get('elem'))
        rpt.append(f"| {i} | {e['source']} | {e['col']} | "
                   f"{format_value(e['value'])} | {loc_str} | {f_str} | {m_str} |")
    rpt.append("")
    rpt.append("---")
    rpt.append("")

    # 2. Detailed Extremes per Stress Type
    for col in STRESS_COLUMNS:
        col_entries = [e for e in envelope['stress_entries'] if e['col'] == col]
        if not col_entries:
            continue
        rpt.append(f"### {col} - Detailed Extremes")
        rpt.append("")
        rpt.append("| Type | Value (kPa) | Location | Source | F (kN/m) | M (kN.m/m) |")
        rpt.append("|------|-------------|----------|--------|----------|------------|")

        maxes = [e for e in col_entries if e['type'] == 'MAX']
        mins = [e for e in col_entries if e['type'] == 'MIN']
        if maxes:
            best = max(maxes, key=lambda x: x['value'])
            f_s = format_value(best.get('F', 0)) if 'F' in best else '-'
            m_s = format_value(best.get('M', 0)) if 'M' in best else '-'
            rpt.append(f"| **Global Max** | {format_value(best['value'])} | "
                       f"{_format_loc(best['loc'], best.get('elem'))} | {best['source']} | {f_s} | {m_s} |")
        if mins:
            best = min(mins, key=lambda x: x['value'])
            f_s = format_value(best.get('F', 0)) if 'F' in best else '-'
            m_s = format_value(best.get('M', 0)) if 'M' in best else '-'
            rpt.append(f"| **Global Min** | {format_value(best['value'])} | "
                       f"{_format_loc(best['loc'], best.get('elem'))} | {best['source']} | {f_s} | {m_s} |")
        rpt.append("")

    # 3. Global Force/Moment Envelope
    rpt.append("---")
    rpt.append("")
    rpt.append("## Global Force & Moment Envelope")
    rpt.append("")

    force_col_groups = {}
    for e in envelope['force_entries']:
        col = e['col']
        if col not in force_col_groups:
            force_col_groups[col] = []
        force_col_groups[col].append(e)

    for col in FORCE_COLUMNS:
        entries = force_col_groups.get(col, [])
        if not entries:
            continue
        entries.sort(key=lambda x: abs(x['value']), reverse=True)
        rpt.append(f"### {col}")
        rpt.append("")
        rpt.append("| Rank | Source | Value | Location |")
        rpt.append("|------|--------|-------|----------|")
        for i, e in enumerate(entries[:5], 1):
            rpt.append(f"| {i} | {e['source']} | {format_value(e['value'])} | "
                       f"{_format_loc(e['loc'], e.get('elem'))} |")
        rpt.append("")

    return '\n'.join(rpt)
