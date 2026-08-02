"""
Reinforcement report — Markdown and Typst.

Answers the questions an engineer actually asks of a rebar run: how much steel
is needed, what bar satisfies it, and — above all — WHERE the section fails.
Inadequate zones get their own table with coordinates, because a count alone
tells you there is a problem without telling you where to look.
"""

import numpy as np

from .rebar import calc_as_min, calc_rho_max, calc_beta1
from .reporting_typst import TYPST_PREAMBLE, _esc, _figure_block, _h, _head


# =============================================================================
# Statistics
# =============================================================================

def summarize_case(As, selection, d_eff, coords, kind='diameter',
                   config_labels=None, max_listed=15):
    """
    Condense one rebar case (e.g. Mxx bottom, X-direction) into report figures.

    Parameters
    ----------
    As : array — required steel area in mm²/m (np.nan = inadequate).
    selection : array or None — the answer for this mode: spacing in mm,
        diameter in mm, or a 1-based config index.
    d_eff : float or array — effective depth in mm.
    coords : tuple of (x_array, y_array) — node/centroid coordinates.
    kind : 'spacing' | 'diameter' | 'config' — how to read `selection`.
    config_labels : list of str, optional — labels when kind == 'config'.
    max_listed : int — cap on individually listed inadequate points.

    Returns
    -------
    dict
    """
    As = np.asarray(As, dtype=float)
    cx, cy = coords

    bad = np.isnan(As)
    finite = ~bad & (As > 0)

    out = {
        'n_points': int(As.size),
        'n_inadequate': int(bad.sum()),
        'as_max': float(np.max(As[finite])) if np.any(finite) else 0.0,
        'as_mean': float(np.mean(As[finite])) if np.any(finite) else 0.0,
        'd_min': float(np.min(np.broadcast_to(np.asarray(d_eff, float), As.shape))),
        'd_max': float(np.max(np.broadcast_to(np.asarray(d_eff, float), As.shape))),
        'max_loc': None,
        'selection_at_max': None,
        'inadequate_points': [],
    }

    if np.any(finite):
        idx = int(np.argmax(np.where(finite, As, -np.inf)))
        out['max_loc'] = (float(cx[idx]), float(cy[idx]))
        if selection is not None:
            out['selection_at_max'] = _label_selection(
                np.asarray(selection, float)[idx], kind, config_labels,
            )

    if out['n_inadequate']:
        where = np.flatnonzero(bad)
        # Cap the listing — a fully failing slab would otherwise bury the
        # report under thousands of rows.
        for i in where[:max_listed]:
            out['inadequate_points'].append((float(cx[i]), float(cy[i])))
        out['inadequate_truncated'] = len(where) > max_listed

    return out


def _label_selection(value, kind='diameter', config_labels=None):
    """Render a selection value as a human-readable label for its mode."""
    if value is None or np.isnan(value):
        return 'TIDAK MEMADAI'

    if kind == 'spacing':
        if np.isinf(value):
            return 'tanpa tulangan'
        return f's = {value:.0f} mm'

    if value == 0:
        return '-'

    if kind == 'config':
        i = int(value) - 1
        if config_labels and 0 <= i < len(config_labels):
            return config_labels[i]
        return f'idx {int(value)}'

    return f'D{int(value)}'


def _fmt_depth(summary):
    lo, hi = summary['d_min'], summary['d_max']
    return f"{lo:.0f}" if abs(hi - lo) < 0.5 else f"{lo:.0f}-{hi:.0f}"


# =============================================================================
# Markdown
# =============================================================================

def render_rebar_report_md(title, cases, params, figures=None):
    """
    Render a reinforcement report as Markdown.

    Parameters
    ----------
    title : str — source name (load case or combination).
    cases : list of (case_title, summary_dict) from summarize_case().
    params : dict — run parameters (fc, fy, cover, h_mm, mode_desc, ...).
    figures : list of (caption, relative_path), optional.
    """
    r = []
    r.append(f"# Laporan Kebutuhan Tulangan — {title}")
    r.append("")
    r.append(f"**Dibuat:** {params['generated']}")
    r.append("")

    # --- Parameter ---
    r.append("## Parameter Desain")
    r.append("")
    r.append("| Parameter | Nilai |")
    r.append("|-----------|-------|")
    r.append(f"| Tebal pelat (h) | {params['h_mm']:.0f} mm |")
    r.append(f"| Selimut bersih | {params['cover']:.0f} mm |")
    r.append(f"| f'c | {params['fc']:.0f} MPa |")
    r.append(f"| fy | {params['fy']:.0f} MPa |")
    r.append(f"| Metode kontur | {params['method'].replace('-', ' ').title()} |")
    r.append(f"| Mode perhitungan | {params['mode_desc']} |")
    if params.get('apply_min'):
        r.append(f"| As minimum (SNI 24.4.3.2) | {params['as_min']:.0f} mm²/m |")
    else:
        r.append("| As minimum | **NONAKTIF** (`--no-as-min`) |")
    r.append(f"| ρ maksimum (SNI Tabel 21.2.2) | {params['rho_max']:.5f} |")
    r.append(f"| β₁ (SNI 22.2.2.4.3) | {params['beta1']:.4f} |")
    r.append("")

    # --- Ringkasan per kasus ---
    r.append("## Ringkasan per Lapis")
    r.append("")
    r.append("| Kasus | d_eff (mm) | As maks (mm²/m) | Lokasi maks | Tulangan di titik maks | Titik gagal |")
    r.append("|-------|-----------|-----------------|-------------|------------------------|-------------|")
    for case_title, s in cases:
        loc = (f"({s['max_loc'][0]:.2f}, {s['max_loc'][1]:.2f})"
               if s['max_loc'] else '-')
        sel = s['selection_at_max'] or '-'
        bad = f"**{s['n_inadequate']}**" if s['n_inadequate'] else "0"
        r.append(f"| {case_title} | {_fmt_depth(s)} | {s['as_max']:.0f} | "
                 f"{loc} | {sel} | {bad} |")
    r.append("")

    # --- Zona gagal ---
    total_bad = sum(s['n_inadequate'] for _, s in cases)
    r.append("## Zona SECTION INADEQUATE")
    r.append("")
    if not total_bad:
        r.append("Tidak ada titik yang gagal memenuhi syarat. ✅")
        r.append("")
    else:
        r.append(f"Total **{total_bad} titik** tidak memenuhi syarat. Penyebab yang "
                 "mungkin: momen melampaui kapasitas lentur penampang, rasio "
                 "tulangan melewati ρ maksimum (penampang tidak daktail), atau "
                 "spasi hasil hitungan lebih rapat dari batas minimum.")
        r.append("")
        r.append("> Menambah diameter tulangan **tidak** menyelesaikan kondisi ini. "
                 "Yang perlu ditinjau: tebal pelat, mutu beton, atau tata letak "
                 "struktur di zona tersebut.")
        r.append("")
        for case_title, s in cases:
            if not s['n_inadequate']:
                continue
            r.append(f"### {case_title} — {s['n_inadequate']} titik")
            r.append("")
            r.append("| # | X (m) | Y (m) |")
            r.append("|---|-------|-------|")
            for i, (x, y) in enumerate(s['inadequate_points'], 1):
                r.append(f"| {i} | {x:.3f} | {y:.3f} |")
            r.append("")
            if s.get('inadequate_truncated'):
                shown = len(s['inadequate_points'])
                r.append(f"*Menampilkan {shown} dari {s['n_inadequate']} titik. "
                         "Lihat diagram untuk sebaran lengkapnya.*")
                r.append("")

    # --- Diagram ---
    if figures:
        r.append("## Diagram")
        r.append("")
        for i, (caption, path) in enumerate(figures, 1):
            r.append(f"### Gambar {i}. {caption}")
            r.append("")
            r.append(f"![{caption}]({path})")
            r.append("")

    return '\n'.join(r)


# =============================================================================
# Typst
# =============================================================================

def render_rebar_report_typst(title, cases, params, figures=None,
                              preamble=True, heading_offset=0):
    """
    Render the same reinforcement report as Typst.

    `preamble=False` and `heading_offset` let this be reused as a chapter of
    the combined document without duplicating the preamble.
    """
    o = heading_offset
    t = _head(preamble)
    t.append(_h(1, f"Laporan Kebutuhan Tulangan — {_esc(title)}", o))
    t.append("")
    t.append("#text(size: 9pt)[")
    t.append(f"  *Dibuat:* {params['generated']}")
    t.append("]")
    t.append("")

    # --- Parameter ---
    t.append(_h(2, "Parameter Desain", o))
    t.append("")
    t.append("#table(")
    t.append("  columns: (1fr, 1fr),")
    t.append("  table.header([Parameter], [Nilai]),")
    t.append(f'  [Tebal pelat (h)], [{params["h_mm"]:.0f} mm],')
    t.append(f'  [Selimut bersih], [{params["cover"]:.0f} mm],')
    t.append(f'  [f\'c], [{params["fc"]:.0f} MPa],')
    t.append(f'  [fy], [{params["fy"]:.0f} MPa],')
    t.append(f'  [Metode kontur], [{params["method"].replace("-", " ").title()}],')
    t.append(f'  [Mode perhitungan], [{_esc(params["mode_desc"])}],')
    if params.get('apply_min'):
        t.append(f'  [As minimum (SNI 24.4.3.2)], [{params["as_min"]:.0f} mm#super[2]/m],')
    else:
        t.append('  [As minimum], [*NONAKTIF*],')
    t.append(f'  [#sym.rho maksimum], [{params["rho_max"]:.5f}],')
    t.append(f'  [#sym.beta #sub[1]], [{params["beta1"]:.4f}],')
    t.append(")")
    t.append("")

    # --- Ringkasan ---
    t.append(_h(2, "Ringkasan per Lapis", o))
    t.append("")
    t.append("#table(")
    t.append("  columns: (auto, auto, auto, auto, auto, auto),")
    t.append("  table.header([Kasus], [d#sub[eff] (mm)], [As maks], [Lokasi maks], "
             "[Tulangan], [Titik gagal]),")
    for case_title, s in cases:
        loc = (f"({s['max_loc'][0]:.2f}, {s['max_loc'][1]:.2f})"
               if s['max_loc'] else '-')
        sel = s['selection_at_max'] or '-'
        bad = f"*{s['n_inadequate']}*" if s['n_inadequate'] else "0"
        t.append(f'  [{_esc(case_title)}], [{_fmt_depth(s)}], [{s["as_max"]:.0f}], '
                 f'[{loc}], [{_esc(sel)}], [{bad}],')
    t.append(")")
    t.append("")

    # --- Zona gagal ---
    total_bad = sum(s['n_inadequate'] for _, s in cases)
    t.append(_h(2, "Zona SECTION INADEQUATE", o))
    t.append("")
    if not total_bad:
        t.append("Tidak ada titik yang gagal memenuhi syarat.")
        t.append("")
    else:
        t.append(f"Total *{total_bad} titik* tidak memenuhi syarat. Penyebab yang "
                 "mungkin: momen melampaui kapasitas lentur penampang, rasio "
                 "tulangan melewati #sym.rho maksimum, atau spasi hasil hitungan "
                 "lebih rapat dari batas minimum.")
        t.append("")
        t.append("#block(fill: luma(240), inset: 8pt, radius: 3pt)[")
        t.append("  Menambah diameter tulangan *tidak* menyelesaikan kondisi ini. "
                 "Yang perlu ditinjau: tebal pelat, mutu beton, atau tata letak "
                 "struktur di zona tersebut.")
        t.append("]")
        t.append("")
        for case_title, s in cases:
            if not s['n_inadequate']:
                continue
            t.append(_h(3, f"{_esc(case_title)} — {s['n_inadequate']} titik", o))
            t.append("")
            t.append("#table(")
            t.append("  columns: (auto, 1fr, 1fr),")
            t.append("  table.header([\\#], [X (m)], [Y (m)]),")
            for i, (x, y) in enumerate(s['inadequate_points'], 1):
                t.append(f'  [{i}], [{x:.3f}], [{y:.3f}],')
            t.append(")")
            t.append("")
            if s.get('inadequate_truncated'):
                shown = len(s['inadequate_points'])
                t.append(f"_Menampilkan {shown} dari {s['n_inadequate']} titik._")
                t.append("")

    t.extend(_figure_block(figures, "Diagram", o))

    return '\n'.join(t)


def build_params(args, h_mm, mode_desc, method, apply_min, generated):
    """Collect the run parameters both renderers need."""
    return {
        'h_mm': h_mm,
        'cover': args.cover,
        'fc': args.fc,
        'fy': args.fy,
        'method': method,
        'mode_desc': mode_desc,
        'apply_min': apply_min,
        'as_min': calc_as_min(args.fy, h_mm),
        'rho_max': calc_rho_max(args.fc, args.fy),
        'beta1': calc_beta1(args.fc),
        'generated': generated,
    }
