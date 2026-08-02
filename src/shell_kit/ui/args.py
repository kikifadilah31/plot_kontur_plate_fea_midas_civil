"""
Menyusun daftar argumen CLI dari nilai-nilai formulir UI.

Sengaja dipisahkan dari app.py dan TIDAK meng-import streamlit, karena inilah
satu-satunya bagian UI yang bisa salah secara diam-diam — dan dengan begini ia
bisa diuji tanpa streamlit terpasang sama sekali.
"""

import shlex

from ..config import DEFAULT_THICKNESS, OUTPUT_FOLDER
from ..rebar import DEFAULT_FC, DEFAULT_FY, DEFAULT_COVER

PROG = 'shell-kit'

# Nilai yang sama dengan default CLI tidak ikut disertakan, supaya perintah
# yang ditampilkan tetap pendek dan terbaca. Diambil dari sumber yang sama
# dengan parser agar tidak ada dua daftar yang bisa melenceng.
DEFAULTS = {
    'thickness': DEFAULT_THICKNESS,
    'output': OUTPUT_FOLDER,
    'method': 'average-nodal',
    'theme': 'light',
    'report_format': 'md',
    'fc': DEFAULT_FC,
    'fy': DEFAULT_FY,
    'cover': DEFAULT_COVER,
    'spacing': 150.0,
    'shear_spacing_long': 150.0,
    'shear_spacing_trans': 150.0,
}


def _num(value):
    """Tulis angka tanpa '.0' yang tidak perlu: 30.0 -> '30', 0.45 -> '0.45'."""
    f = float(value)
    return str(int(f)) if f == int(f) else str(f)


def _same_as_default(key, value):
    if key not in DEFAULTS:
        return False
    ref = DEFAULTS[key]
    if isinstance(ref, (int, float)):
        try:
            return float(value) == float(ref)
        except (TypeError, ValueError):
            return False
    return value == ref


def build_argv(command, values):
    """
    Susun argumen CLI dari nilai formulir.

    Parameters
    ----------
    command : 'plot' atau 'rebar'
    values : dict — nilai widget, memakai nama yang sama dengan dest argparse
        (mis. 'no_mesh', 'report_format', 'as_min_surface_zone').
        Kunci yang tidak ada dianggap memakai default.

    Returns
    -------
    list of str : argumen siap diteruskan ke shell_kit.cli, mis.
        ['rebar', '--fc', '35', '--no-mesh', '--report', '--format', 'pdf']

    Catatan
    -------
    Hanya nilai yang berbeda dari default yang disertakan. Perintah yang
    dihasilkan selalu setara dengan yang tampil di layar — keduanya berasal
    dari fungsi ini.
    """
    v = dict(values or {})
    argv = [command]

    def add(flag, key, formatter=str):
        val = v.get(key)
        if val in (None, ''):
            return
        if _same_as_default(key, val):
            return
        argv.extend([flag, formatter(val)])

    def add_flag(flag, key):
        if v.get(key):
            argv.append(flag)

    def add_list(flag, key):
        items = v.get(key)
        if not items:
            return
        argv.append(flag)
        argv.extend(str(i) for i in items)

    # --- Input & output ---
    add('--kordinat', 'kordinat')
    add('--connectivity', 'connectivity')
    add('--gaya', 'gaya')
    add('--thickness', 'thickness', _num)
    add('--output', 'output')

    # --- Metode & kombinasi ---
    add('--method', 'method')
    add('--comb', 'comb')
    comb_select = v.get('comb_select')
    if comb_select and list(comb_select) != ['*']:
        add_list('--comb-select', 'comb_select')

    # --- Material & tulangan (hanya rebar) ---
    if command == 'rebar':
        add('--fc', 'fc', _num)
        add('--fy', 'fy', _num)
        add('--cover', 'cover', _num)

        # Mode A dan Mode B saling meniadakan: bila tulangan terpasang
        # diberikan, spasi adalah keluarannya — bukan masukan.
        if v.get('diameter'):
            argv.extend(['--diameter', str(v['diameter'])])
        else:
            add('--spacing', 'spacing', _num)
            add_list('--rebar-select', 'rebar_select')

        add_flag('--no-as-min', 'no_as_min')
        add('--as-min-surface-zone', 'as_min_surface_zone', _num)

        # --- Geser ---
        if v.get('shear'):
            argv.append('--shear')
            add('--shear-spacing-long', 'shear_spacing_long', _num)
            add('--shear-spacing-trans', 'shear_spacing_trans', _num)
            add_list('--shear-select', 'shear_select')

    # --- Tampilan ---
    add('--theme', 'theme')
    add_flag('--no-mesh', 'no_mesh')
    add_flag('--no-annotation', 'no_annotation')

    # --- Laporan ---
    if v.get('report'):
        argv.append('--report')
        add('--format', 'report_format')

    return argv


def format_command(argv):
    """
    Perintah setara yang bisa disalin ke terminal.

    Bukan hiasan: pengguna bisa menempelkannya di terminal atau mengirimkannya
    ke rekan, dan perlahan mengenali CLI-nya.
    """
    return ' '.join([PROG] + [shlex.quote(a) for a in argv])
