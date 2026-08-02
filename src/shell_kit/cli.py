"""
Single entry point for shell-kit.

    shell-kit plot    kontur gaya dalam, momen, dan tegangan
    shell-kit rebar   kebutuhan tulangan lentur & geser

Shared options are defined ONCE here. Previously each command owned its own
parser, which is how `--comb-select` ended up on two commands but not the
third, and `--no-annotation` on only one.
"""

import argparse
import sys

from . import __version__
from .config import DEFAULT_THICKNESS, OUTPUT_FOLDER
from .rebar import DEFAULT_FC, DEFAULT_FY, DEFAULT_COVER

PROG = 'shell-kit'

EPILOG = """\
contoh:
  shell-kit plot  --method all --no-mesh
  shell-kit plot  --comb input/kombinasi_beban.csv --report --format typst
  shell-kit rebar --fc 30 --fy 420 --spacing 150 --report
  shell-kit rebar --diameter 2D25 --comb input/kombinasi_beban.csv --no-mesh
  shell-kit rebar --shear --shear-select 10 13 16 --report --format pdf
"""


def _add_input_args(p):
    """Input files, geometry, and output location — identical for every command."""
    g = p.add_argument_group('input & output')
    g.add_argument('--kordinat', type=str, help='Path ke CSV koordinat node')
    g.add_argument('--connectivity', type=str, help='Path ke CSV konektivitas elemen')
    g.add_argument('--gaya', type=str, help='Path ke CSV gaya/momen per load case')
    g.add_argument('--thickness', type=float, default=DEFAULT_THICKNESS,
                   help=f'Tebal pelat dalam meter (default: {DEFAULT_THICKNESS})')
    g.add_argument('--output', type=str, default=OUTPUT_FOLDER,
                   help=f'Folder output (default: {OUTPUT_FOLDER})')


def _add_analysis_args(p):
    """Contour method and load combination handling."""
    g = p.add_argument_group('metode & kombinasi')
    g.add_argument('--method', type=str,
                   choices=['average-nodal', 'element-nodal', 'element-center', 'all'],
                   default='average-nodal',
                   help='Metode kontur (default: average-nodal)')
    g.add_argument('--comb', type=str, default='',
                   help='Path ke CSV kombinasi beban')
    g.add_argument('--comb-select', type=str, nargs='*', default=['*'],
                   help='Filter nama kombinasi dengan wildcard (default: * = semua)')


def _add_style_args(p):
    """Visual styling — shared by both plotting commands."""
    g = p.add_argument_group('tampilan')
    g.add_argument('--theme', type=str, choices=['light', 'dark'], default='light',
                   help='Tema plot (default: light)')
    g.add_argument('--no-mesh', action='store_true', help='Sembunyikan wireframe mesh')
    g.add_argument('--no-annotation', action='store_true',
                   help='Sembunyikan marker MAX/MIN dan badge SECTION INADEQUATE')


def _add_report_args(p):
    """Report generation — available on every command."""
    g = p.add_argument_group('laporan')
    g.add_argument('--report', action='store_true',
                   help='Hasilkan dokumen ringkasan lengkap dengan diagram tersemat')
    g.add_argument('--format', type=str, choices=['md', 'typst', 'pdf'], default='md',
                   dest='report_format',
                   help='Format laporan: md, typst, atau pdf (default: md). '
                        'pdf dikompilasi dari typst di dalam Python; file .typ '
                        'tetap disimpan agar bisa disunting. Perlu --report')


def _add_rebar_args(p):
    """Options specific to reinforcement design."""
    g = p.add_argument_group('material & tulangan')
    g.add_argument('--fc', type=float, default=DEFAULT_FC,
                   help=f"Kuat tekan beton f'c dalam MPa (default: {DEFAULT_FC})")
    g.add_argument('--fy', type=float, default=DEFAULT_FY,
                   help=f'Kuat leleh baja fy dalam MPa (default: {DEFAULT_FY})')
    g.add_argument('--cover', type=float, default=DEFAULT_COVER,
                   help=f'Selimut beton bersih dalam mm (default: {DEFAULT_COVER})')
    g.add_argument('--diameter', type=str, default=None,
                   help='Mode A — kode tulangan terpasang, output = spasi. '
                        'Contoh: 16, 2D25, 3D32')
    g.add_argument('--spacing', type=float, default=150,
                   help='Mode B — spasi terpasang dalam mm, output = tulangan '
                        '(default: 150)')
    g.add_argument('--rebar-select', type=str, nargs='+', default=None,
                   help='Batasi pilihan konfigurasi untuk Mode B. '
                        'Contoh: --rebar-select 16 22 25 2D25')
    g.add_argument('--no-as-min', action='store_true',
                   help='Nonaktifkan tulangan minimum SNI 24.4.3.2 (hanya untuk '
                        'membandingkan dengan hasil v1.x)')
    g.add_argument('--as-min-surface-zone', type=float, default=None,
                   metavar='MM',
                   help='Batasi tebal per muka yang dipakai menghitung tulangan '
                        'minimum, mis. 300. Untuk penampang tebal (rakit, '
                        'pilecap) rho x h penuh menghasilkan tulangan berlebih. '
                        'Meminjam ACI 350-06 7.12.2.1 — di luar huruf SNI 2847, '
                        'dan dicatat di laporan bila dipakai.')

    s = p.add_argument_group('geser')
    s.add_argument('--shear', action='store_true',
                   help='Aktifkan analisis tulangan geser (Av/s dari Vxx, Vyy)')
    s.add_argument('--shear-spacing-long', type=float, default=150,
                   help='Spasi sengkang arah memanjang dalam mm (default: 150)')
    s.add_argument('--shear-spacing-trans', type=float, default=150,
                   help='Spasi sengkang melintang dalam mm (default: 150)')
    s.add_argument('--shear-select', type=int, nargs='+', default=None,
                   help='Batasi diameter sengkang yang tersedia dalam mm. '
                        'Contoh: --shear-select 10 13 16')


def build_parser():
    parser = argparse.ArgumentParser(
        prog=PROG,
        description='Post-processing hasil pelat/shell Midas Civil: kontur gaya '
                    'dalam, desain tulangan SNI 2847:2019, dan laporan.',
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--version', action='version',
                        version=f'{PROG} {__version__}')

    sub = parser.add_subparsers(dest='command', metavar='<perintah>')

    p_plot = sub.add_parser(
        'plot',
        help='Kontur gaya dalam, momen, dan tegangan',
        description='Menghasilkan contour plot gaya dalam, momen, dan tegangan '
                    'serat atas/bawah dari hasil FEM.',
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_input_args(p_plot)
    _add_analysis_args(p_plot)
    _add_style_args(p_plot)
    _add_report_args(p_plot)

    p_rebar = sub.add_parser(
        'rebar',
        help='Kebutuhan tulangan lentur & geser (SNI 2847:2019)',
        description='Menghitung kebutuhan tulangan pelat dari momen dan geser '
                    'hasil FEM, lalu memetakannya sebagai contour plot.',
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_input_args(p_rebar)
    _add_analysis_args(p_rebar)
    _add_rebar_args(p_rebar)
    _add_style_args(p_rebar)
    _add_report_args(p_rebar)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 2

    # --format only means something alongside --report; say so rather than
    # silently ignoring it.
    if args.report_format != 'md' and not args.report:
        print(f"[WARN] --format {args.report_format} diabaikan karena "
              f"--report tidak diaktifkan.")

    if args.command == 'plot':
        from .cli_plot import run
    else:
        from .cli_rebar import run

    return run(args)


def entry_point():
    """Console script entry point (declared in pyproject.toml [project.scripts])."""
    from multiprocessing import freeze_support
    freeze_support()
    sys.exit(main())


if __name__ == '__main__':
    entry_point()
