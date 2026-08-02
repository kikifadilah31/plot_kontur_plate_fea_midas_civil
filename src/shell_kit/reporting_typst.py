"""
Typst rendering engine — .typ output, compiled to PDF by shell_kit.pdf.

Every renderer takes `preamble` and `heading_offset` so the same function can
produce a standalone document or a chapter inside the combined report.
"""

from datetime import datetime

from .config import FORCE_COLUMNS, STRESS_COLUMNS, STRIP_WIDTH
from .math_utils import format_value
from .reporting import _format_loc


# =============================================================================
# Typst preamble — clean academic style
# =============================================================================
# "New Computer Modern" ships with the bundled compiler (verified against
# typst.Fonts(include_system_fonts=False)), so this resolves without a font
# warning and looks identical on every machine.
TYPST_PREAMBLE = """\
// Dihasilkan oleh shell-kit
// Compile: typst compile <nama>.typ   (atau gunakan --format pdf)

#set page(
  paper: "a4",
  margin: (x: 2cm, y: 2.5cm),
  numbering: "1",
)
#set text(font: "New Computer Modern", size: 10pt)
#set heading(numbering: "1.1")
#set table(
  inset: 6pt,
  stroke: 0.5pt + luma(180),
)
#show table.cell.where(y: 0): set text(weight: "bold")
#show heading.where(level: 1): set text(size: 16pt)
#show heading.where(level: 2): set text(size: 13pt)
#show heading.where(level: 3): set text(size: 11pt)
"""


def _h(level, text, offset=0):
    """
    Build a Typst heading, shifted `offset` levels deeper.

    The offset lets a standalone report be reused verbatim as a chapter of the
    combined document.
    """
    return f"{'=' * (level + offset)} {text}"


def _head(preamble):
    """Opening lines of a document: the preamble, or nothing for a fragment."""
    return [TYPST_PREAMBLE] if preamble else []


def _tv(v):
    """Format a numeric value for Typst table cell."""
    return format_value(v) if isinstance(v, (int, float)) else str(v)


def _tloc(loc, elem_id=None):
    """Format location for Typst table cell."""
    x, y = loc
    if elem_id is not None:
        return f"Elem {elem_id} ({x:.2f}, {y:.2f})"
    return f"({x:.2f}, {y:.2f})"


def _esc(text):
    """
    Escape characters Typst treats as markup inside a content block.

    Load case names come from the FEA export, so they are outside our control
    — a name containing '#' silently loses it ('As #1' renders as 'As 1'), and
    brackets nest into the surrounding block.
    """
    return (str(text)
            .replace('\\', '\\\\')
            .replace('[', '\\[')
            .replace(']', '\\]')
            .replace('#', '\\#')
            .replace('*', '\\*')
            .replace('_', '\\_')
            .replace('@', '\\@')
            .replace('$', '\\$')
            .replace('<', '\\<')
            .replace('>', '\\>'))


def _figure_block(figures, heading, offset=0):
    """
    Build a Typst section embedding each figure with a numbered caption.

    Returns an empty list when there is nothing to embed, so callers can
    extend() unconditionally.
    """
    if not figures:
        return []

    lines = [_h(2, heading, offset), ""]
    for caption, path in figures:
        lines.append("#figure(")
        lines.append(f'  image("{path}", width: 100%),')
        lines.append(f'  caption: [{_esc(caption)}],')
        lines.append(")")
        lines.append("")
    return lines


def render_report_typst(title, stats, n_points, thickness, method, figures=None,
                        preamble=True, heading_offset=0):
    """
    Render a single-source report as Typst string.

    Parameters
    ----------
    title : str
    stats : dict — output of extract_statistics()
    n_points : int
    thickness : float
    method : str
    figures : list of (caption, relative_path), optional
        Contour plots to embed. Paths must already be relative to where this
        document will be written.
    preamble : bool
        Emit the document preamble. False when this is a chapter of a larger
        document that already carries one.
    heading_offset : int
        Push every heading this many levels deeper.

    Returns
    -------
    str — complete Typst content
    """
    o = heading_offset
    lines = _head(preamble)

    # Title
    lines.append(_h(1, f"Ringkasan Hasil FEA — {_esc(title)}", o))
    lines.append("")
    lines.append(f"#text(size: 9pt)[")
    lines.append(f"  *Dibuat:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} \\")
    lines.append(f"  *Tebal pelat:* {thickness * 1000:.0f} mm \\")
    lines.append(f"  *Lebar pias:* {STRIP_WIDTH:.1f} m \\")
    lines.append(f"  *Metode kontur:* {method.replace('-', ' ').title()} \\")
    lines.append(f"  *Jumlah titik data:* {n_points:,}")
    lines.append(f"]")
    lines.append("")

    # Section Properties
    area = thickness * STRIP_WIDTH
    inertia = (STRIP_WIDTH * thickness ** 3) / 12
    lines.append(_h(2, "Properti Penampang", o))
    lines.append("")
    lines.append("#table(")
    lines.append("  columns: (1fr, 1fr, auto),")
    lines.append("  table.header([Parameter], [Nilai], [Satuan]),")
    # Literal UTF-8, not '\\u00b2': Typst reads that as an escaped 'u'
    # followed by the digits, and the cell renders as "mu00b2".
    lines.append(f'  [Area (A)], [{area:.6f}], [m²],')
    lines.append(f'  [Inersia (I)], [{inertia:.6f}], [m⁴],')
    lines.append(")")
    lines.append("")

    # Force/Moment Summary
    force_cols = [c for c in FORCE_COLUMNS if c in stats]
    if force_cols:
        lines.append(_h(2, "Ringkasan Gaya & Momen", o))
        lines.append("")
        for col in force_cols:
            e = stats[col]
            lines.append(_h(3, _esc(col), o))
            lines.append("")
            lines.append("#table(")
            lines.append("  columns: (auto, 1fr, auto),")
            lines.append("  table.header([Statistik], [Nilai], [Lokasi]),")
            lines.append(f'  [*Maksimum*], [{_tv(e["max"])}], [{_tloc(e["max_loc"], e.get("max_elem"))}],')
            lines.append(f'  [*Minimum*], [{_tv(e["min"])}], [{_tloc(e["min_loc"], e.get("min_elem"))}],')
            lines.append(f'  [Rata-rata], [{_tv(e["mean"])}], [-],')
            lines.append(")")
            lines.append("")

    # Stress Summary
    stress_cols = [c for c in STRESS_COLUMNS if c in stats]
    if stress_cols:
        lines.append(_h(2, "Ringkasan Tegangan (kPa)", o))
        lines.append("")
        lines.append("_Konvensi tanda: momen positif → serat atas tekan (-), serat bawah tarik (+)_")
        lines.append("")
        for col in stress_cols:
            e = stats[col]
            f_max = _tv(e.get('max_F', '-'))
            m_max = _tv(e.get('max_M', '-'))
            f_min = _tv(e.get('min_F', '-'))
            m_min = _tv(e.get('min_M', '-'))
            lines.append(_h(3, _esc(col), o))
            lines.append("")
            lines.append("#table(")
            lines.append("  columns: (auto, 1fr, auto, auto, auto),")
            lines.append("  table.header([Statistik], [Nilai], [Lokasi], [F (kN/m)], [M (kN·m/m)]),")
            lines.append(f'  [*Maksimum*], [{_tv(e["max"])}], [{_tloc(e["max_loc"], e.get("max_elem"))}], [{f_max}], [{m_max}],')
            lines.append(f'  [*Minimum*], [{_tv(e["min"])}], [{_tloc(e["min_loc"], e.get("min_elem"))}], [{f_min}], [{m_min}],')
            lines.append(f'  [Rata-rata], [{_tv(e["mean"])}], [-], [-], [-],')
            lines.append(")")
            lines.append("")

    lines.extend(_figure_block(figures, "Diagram Kontur", o))

    return '\n'.join(lines)


def render_master_typst(envelope, thickness, method,
                        preamble=True, heading_offset=0):
    """
    Render master summary as Typst string.

    Parameters
    ----------
    envelope : dict — output of compute_master_envelope()
    thickness : float
    method : str
    preamble : bool — emit the document preamble.
    heading_offset : int — push every heading this many levels deeper.

    Returns
    -------
    str — complete Typst content
    """
    o = heading_offset
    lines = _head(preamble)

    lines.append(_h(1, "Master Summary — Seluruh Load Case & Kombinasi", o))
    lines.append("")
    lines.append("#text(size: 9pt)[")
    lines.append(f"  *Dibuat:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} \\")
    lines.append(f"  *Total dianalisis:* {envelope['total_sources']} "
                 f"({envelope['total_lc']} load case + {envelope['total_combo']} kombinasi) \\")
    lines.append(f"  *Tebal pelat:* {thickness * 1000:.0f} mm | "
                 f"*Lebar pias:* {STRIP_WIDTH:.1f} m | "
                 f"*Metode:* {method.replace('-', ' ').title()}")
    lines.append("]")
    lines.append("")
    lines.append("#line(length: 100%, stroke: 0.5pt + luma(180))")
    lines.append("")

    # 1. Global Stress Envelope — Top 20
    lines.append(_h(2, "Envelope Tegangan Global", o))
    lines.append("")
    lines.append(_h(3, "20 Tegangan Absolut Tertinggi (seluruh sumber)", o))
    lines.append("")
    lines.append("#table(")
    lines.append("  columns: (auto, auto, auto, 1fr, auto, auto, auto),")
    lines.append("  table.header([Rank], [Sumber], [Kolom], [Nilai (kPa)], [Lokasi], [F (kN/m)], [M (kN·m/m)]),")

    for i, e in enumerate(envelope['stress_entries'][:20], 1):
        f_str = _tv(e['F']) if 'F' in e else '-'
        m_str = _tv(e['M']) if 'M' in e else '-'
        loc_str = _tloc(e['loc'], e.get('elem'))
        lines.append(f'  [{i}], [{_esc(e["source"])}], [{_esc(e["col"])}], '
                     f'[{_tv(e["value"])}], [{loc_str}], [{f_str}], [{m_str}],')

    lines.append(")")
    lines.append("")
    lines.append("#line(length: 100%, stroke: 0.5pt + luma(180))")
    lines.append("")

    # 2. Detailed Extremes per Stress Type
    for col in STRESS_COLUMNS:
        col_entries = [e for e in envelope['stress_entries'] if e['col'] == col]
        if not col_entries:
            continue
        lines.append(_h(3, f"{_esc(col)} — Ekstrem Terperinci", o))
        lines.append("")
        lines.append("#table(")
        lines.append("  columns: (auto, 1fr, auto, auto, auto, auto),")
        lines.append("  table.header([Tipe], [Nilai (kPa)], [Lokasi], [Sumber], [F (kN/m)], [M (kN·m/m)]),")

        maxes = [e for e in col_entries if e['type'] == 'MAX']
        mins = [e for e in col_entries if e['type'] == 'MIN']
        if maxes:
            best = max(maxes, key=lambda x: x['value'])
            f_s = _tv(best.get('F', 0)) if 'F' in best else '-'
            m_s = _tv(best.get('M', 0)) if 'M' in best else '-'
            lines.append(f'  [*Global Max*], [{_tv(best["value"])}], '
                         f'[{_tloc(best["loc"], best.get("elem"))}], [{_esc(best["source"])}], [{f_s}], [{m_s}],')
        if mins:
            best = min(mins, key=lambda x: x['value'])
            f_s = _tv(best.get('F', 0)) if 'F' in best else '-'
            m_s = _tv(best.get('M', 0)) if 'M' in best else '-'
            lines.append(f'  [*Global Min*], [{_tv(best["value"])}], '
                         f'[{_tloc(best["loc"], best.get("elem"))}], [{_esc(best["source"])}], [{f_s}], [{m_s}],')

        lines.append(")")
        lines.append("")

    # 3. Global Force/Moment Envelope
    lines.append("#line(length: 100%, stroke: 0.5pt + luma(180))")
    lines.append("")
    lines.append(_h(2, "Envelope Gaya & Momen Global", o))
    lines.append("")

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
        lines.append(_h(3, _esc(col), o))
        lines.append("")
        lines.append("#table(")
        lines.append("  columns: (auto, auto, 1fr, auto),")
        lines.append("  table.header([Rank], [Sumber], [Nilai], [Lokasi]),")
        for i, e in enumerate(entries[:5], 1):
            lines.append(f'  [{i}], [{_esc(e["source"])}], [{_tv(e["value"])}], '
                         f'[{_tloc(e["loc"], e.get("elem"))}],')
        lines.append(")")
        lines.append("")

    return '\n'.join(lines)


# =============================================================================
# Combined document — one file covering the whole run
# =============================================================================

def render_combined_typst(run_meta, sections, master_body=None):
    """
    Stitch every per-source report into one document with a title page.

    Sections are fragments from a renderer called with `preamble=False` and
    the default `heading_offset=0` — each already opens with its own level-1
    heading, which becomes the chapter title. No extra heading is added here,
    otherwise every chapter would carry its name twice.

    Parameters
    ----------
    run_meta : dict
        Keys shown on the title page: 'title', 'subtitle',
        'rows' (list of (label, value) pairs), and optional 'note'.
    sections : list of str — per-source fragments, in order.
    master_body : str, optional
        Master summary fragment, placed before the per-source chapters.

    Returns
    -------
    str — complete Typst document
    """
    lines = [TYPST_PREAMBLE]

    # --- Title page ---
    lines.append("#align(center)[")
    lines.append("  #v(4cm)")
    lines.append(f"  #text(size: 24pt, weight: \"bold\")[{_esc(run_meta['title'])}]")
    lines.append("")
    lines.append("  #v(0.5cm)")
    lines.append(f"  #text(size: 14pt)[{_esc(run_meta.get('subtitle', ''))}]")
    lines.append("")
    lines.append("  #v(1.5cm)")
    lines.append("]")
    lines.append("")

    rows = run_meta.get('rows') or []
    if rows:
        lines.append("#align(center)[")
        lines.append("  #block(width: 80%)[")
        lines.append("    #table(")
        lines.append("      columns: (auto, 1fr),")
        lines.append("      align: (right, left),")
        lines.append("      stroke: none,")
        for label, value in rows:
            lines.append(f'      [*{_esc(label)}*], [{_esc(value)}],')
        lines.append("    )")
        lines.append("  ]")
        lines.append("]")
        lines.append("")

    if run_meta.get('note'):
        lines.append("#v(1cm)")
        lines.append("#align(center)[")
        lines.append(f"  #block(width: 80%, fill: luma(240), inset: 10pt, radius: 3pt)[")
        lines.append(f"    #text(size: 9pt)[{_esc(run_meta['note'])}]")
        lines.append("  ]")
        lines.append("]")
        lines.append("")

    lines.append("#pagebreak()")
    lines.append("")

    # --- Table of contents ---
    lines.append("#outline(title: [Daftar Isi], depth: 2)")
    lines.append("")
    lines.append("#pagebreak()")
    lines.append("")

    # --- Master summary, then one chapter per source ---
    if master_body:
        lines.append(master_body)
        lines.append("")
        lines.append("#pagebreak()")
        lines.append("")

    for i, fragment in enumerate(sections):
        if i:
            lines.append("#pagebreak()")
            lines.append("")
        lines.append(fragment)
        lines.append("")

    return '\n'.join(lines)
