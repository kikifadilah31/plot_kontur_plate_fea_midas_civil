"""
Penyusun argumen UI.

Ini satu-satunya bagian UI yang bisa salah secara diam-diam: kalau ia
menghasilkan perintah yang tidak sah, pengguna melihat kegagalan yang tidak
ada hubungannya dengan pilihannya. Karena args.py tidak meng-import streamlit,
seluruh berkas ini berjalan tanpa streamlit terpasang.
"""

import pytest

from shell_kit.cli import build_parser
from shell_kit.rebar import DEFAULT_FC, DEFAULT_FY, DEFAULT_COVER
from shell_kit.config import DEFAULT_THICKNESS, OUTPUT_FOLDER
from shell_kit.ui.args import build_argv, format_command


def _defaults(**over):
    """Nilai formulir yang seluruhnya sama dengan default CLI."""
    v = {
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
    v.update(over)
    return v


# =============================================================================
# Nilai default tidak ikut muncul
# =============================================================================

def test_all_defaults_produce_a_bare_command():
    """Perintah yang ditampilkan harus tetap pendek dan terbaca."""
    assert build_argv('rebar', _defaults()) == ['rebar']
    assert build_argv('plot', _defaults()) == ['plot']


def test_changed_value_appears():
    argv = build_argv('rebar', _defaults(fc=35.0))
    assert argv == ['rebar', '--fc', '35']


def test_numbers_lose_the_pointless_decimal():
    """30.0 ditulis '30', tapi 0.45 tetap '0.45'."""
    assert '--fc' in build_argv('rebar', _defaults(fc=35.0))
    assert build_argv('rebar', _defaults(fc=35.0))[2] == '35'
    assert build_argv('rebar', _defaults(thickness=0.45))[2] == '0.45'


def test_empty_strings_are_not_emitted():
    argv = build_argv('rebar', _defaults(kordinat='', comb=''))
    assert '--kordinat' not in argv
    assert '--comb' not in argv


def test_missing_keys_are_treated_as_defaults():
    assert build_argv('rebar', {}) == ['rebar']
    assert build_argv('rebar', None) == ['rebar']


# =============================================================================
# Boolean jadi flag, atau tidak sama sekali
# =============================================================================

@pytest.mark.parametrize('key,flag', [
    ('no_mesh', '--no-mesh'),
    ('no_annotation', '--no-annotation'),
    ('no_as_min', '--no-as-min'),
])
def test_booleans_become_bare_flags(key, flag):
    assert flag in build_argv('rebar', _defaults(**{key: True}))
    assert flag not in build_argv('rebar', _defaults(**{key: False}))


def test_unchecking_as_min_reaches_the_command():
    """
    Permintaan pengguna: opsi mematikan As,min harus benar-benar tersambung
    dari checkbox ke perintah, bukan sekadar tampil di layar.
    """
    argv = build_argv('rebar', _defaults(no_as_min=True))
    assert '--no-as-min' in argv


def test_report_format_only_rides_along_with_report():
    """--format tanpa --report akan diperingatkan CLI; jangan kirim sendirian."""
    argv = build_argv('rebar', _defaults(report=False, report_format='pdf'))
    assert '--format' not in argv

    argv = build_argv('rebar', _defaults(report=True, report_format='pdf'))
    assert argv[-3:] == ['--report', '--format', 'pdf']


# =============================================================================
# Daftar jadi nilai berulang
# =============================================================================

def test_rebar_select_becomes_repeated_values():
    argv = build_argv('rebar', _defaults(rebar_select=['16', '22', '2D25']))
    i = argv.index('--rebar-select')
    assert argv[i + 1:i + 4] == ['16', '22', '2D25']


def test_shear_options_only_when_shear_is_on():
    off = build_argv('rebar', _defaults(shear=False, shear_select=[10, 13]))
    assert '--shear' not in off
    assert '--shear-select' not in off

    on = build_argv('rebar', _defaults(shear=True, shear_select=[10, 13]))
    assert '--shear' in on
    assert on[on.index('--shear-select') + 1:][:2] == ['10', '13']


def test_comb_select_wildcard_is_not_emitted():
    """['*'] adalah default CLI; mengirimnya hanya menambah kebisingan."""
    assert '--comb-select' not in build_argv('rebar', _defaults(comb_select=['*']))
    assert '--comb-select' in build_argv('rebar', _defaults(comb_select=['K_1*']))


def test_empty_lists_are_not_emitted():
    argv = build_argv('rebar', _defaults(rebar_select=[], shear=True,
                                         shear_select=[]))
    assert '--rebar-select' not in argv
    assert '--shear-select' not in argv


# =============================================================================
# Mode A dan Mode B tidak pernah terkirim bersamaan
# =============================================================================

def test_giving_a_bar_suppresses_spacing():
    """Mode A: tulangan diketahui, spasi adalah keluarannya — bukan masukan."""
    argv = build_argv('rebar', _defaults(diameter='2D25', spacing=200.0))
    assert '--diameter' in argv
    assert '--spacing' not in argv


def test_without_a_bar_spacing_is_the_input():
    argv = build_argv('rebar', _defaults(spacing=200.0))
    assert '--spacing' in argv
    assert '--diameter' not in argv


def test_rebar_only_options_never_leak_into_plot():
    argv = build_argv('plot', _defaults(fc=35.0, shear=True, no_as_min=True,
                                        spacing=200.0, diameter='16'))
    for flag in ('--fc', '--shear', '--no-as-min', '--spacing', '--diameter'):
        assert flag not in argv


# =============================================================================
# Celah antara UI dan CLI — test terpenting di berkas ini
# =============================================================================

@pytest.mark.parametrize('command,values', [
    ('rebar', {}),
    ('plot', {}),
    ('rebar', _defaults(fc=35.0, fy=500.0, cover=50.0, spacing=200.0,
                        no_as_min=True, no_mesh=True, report=True,
                        report_format='pdf')),
    ('rebar', _defaults(diameter='2D25', shear=True, shear_select=[10, 13],
                        as_min_surface_zone=300.0, method='all')),
    ('rebar', _defaults(rebar_select=['16', '22'], comb='k.csv',
                        comb_select=['K_1*', 'K_2*'], theme='dark',
                        no_annotation=True)),
    ('plot', _defaults(method='element-center', thickness=0.5,
                       kordinat='a.csv', connectivity='b.csv', gaya='c.csv',
                       output='hasil', report=True, report_format='typst')),
])
def test_every_generated_command_is_accepted_by_the_real_parser(command, values):
    """
    Membuktikan setiap perintah yang bisa dihasilkan UI benar-benar sah bagi
    CLI. Inilah satu-satunya tempat kesalahan bisa lolos diam-diam, karena
    formulirnya sendiri tidak diuji otomatis.
    """
    argv = build_argv(command, values)
    args = build_parser().parse_args(argv)     # SystemExit bila tidak sah
    assert args.command == command


def test_parsed_values_match_what_the_form_asked_for():
    values = _defaults(fc=35.0, no_as_min=True, report=True,
                       report_format='pdf', shear=True)
    args = build_parser().parse_args(build_argv('rebar', values))

    assert args.fc == 35.0
    assert args.no_as_min is True
    assert args.report is True
    assert args.report_format == 'pdf'
    assert args.shear is True


def test_defaults_round_trip_to_the_same_values():
    """Menghilangkan nilai default tidak boleh mengubah apa yang diterima CLI."""
    args = build_parser().parse_args(build_argv('rebar', _defaults()))
    assert args.fc == DEFAULT_FC
    assert args.thickness == DEFAULT_THICKNESS
    assert args.method == 'average-nodal'
    assert args.no_as_min is False


# =============================================================================
# Tampilan perintah
# =============================================================================

def test_command_string_starts_with_the_program_name():
    assert format_command(['rebar', '--fc', '35']).startswith('shell-kit rebar')


def test_paths_with_spaces_are_quoted():
    text = format_command(build_argv('rebar', _defaults(comb='my folder/k.csv')))
    assert "'my folder/k.csv'" in text or '"my folder/k.csv"' in text


def test_args_module_does_not_import_streamlit():
    """
    Penyusun argumen harus bisa dites tanpa streamlit terpasang, jadi ia tidak
    boleh mengimpornya. Diperiksa lewat AST, bukan pencarian teks — kata
    'streamlit' wajar muncul di komentar.
    """
    import ast
    import inspect
    import shell_kit.ui.args as mod

    tree = ast.parse(inspect.getsource(mod))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split('.')[0])

    assert 'streamlit' not in imported


def test_args_module_does_not_touch_the_engine():
    """
    Pembeda dari UI lama: lapisan UI tidak boleh memanggil pipeline. Ia hanya
    boleh membaca konstanta default supaya tidak ada daftar yang ditulis ulang.
    """
    import ast
    import inspect
    import shell_kit.ui.args as mod

    tree = ast.parse(inspect.getsource(mod))
    engine_modules = {'cli_plot', 'cli_rebar', 'mesh', 'values', 'plotting',
                      'plotting_rebar', 'report_writer'}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            leaf = node.module.split('.')[-1]
            assert leaf not in engine_modules, (
                f'ui/args.py mengimpor {leaf} — UI harus memanggil CLI, '
                f'bukan menjalankan engine sendiri'
            )


# =============================================================================
# Perintah `shell-kit ui`
# =============================================================================

def test_ui_is_a_recognised_command():
    args = build_parser().parse_args(['ui'])
    assert args.command == 'ui'


def test_ui_carries_no_analysis_arguments():
    """
    'ui' sengaja tanpa argumen analisis. main() harus keluar dari jalur
    dispatch sebelum atribut laporan disentuh, kalau tidak AttributeError.
    """
    args = build_parser().parse_args(['ui'])
    assert not hasattr(args, 'report_format')
    assert not hasattr(args, 'fc')


def test_ui_does_not_fall_through_to_rebar(monkeypatch):
    """
    Dispatch lama memakai `else: from .cli_rebar import run`, sehingga setiap
    perintah selain 'plot' berakhir di rebar.
    """
    from shell_kit import cli
    import shell_kit.ui.launcher as launcher

    called = {}

    def _fake_launch():
        called['ui'] = True
        return 0

    monkeypatch.setattr(launcher, 'launch', _fake_launch)

    assert cli.main(['ui']) == 0
    assert called.get('ui') is True


def test_launch_without_streamlit_gives_instructions(monkeypatch, capsys):
    """Ketiadaan paket opsional harus berujung petunjuk, bukan traceback."""
    import shell_kit.ui.launcher as launcher

    monkeypatch.setattr(launcher, 'streamlit_available', lambda: False)
    code = launcher.launch()

    assert code == 1
    out = capsys.readouterr().out
    assert 'streamlit' in out.lower()
    assert 'shell-kit[ui]' in out


def test_launcher_does_not_import_the_engine():
    """Peluncur hanya menyalakan server; ia tidak boleh menyentuh pipeline."""
    import ast
    import inspect
    import shell_kit.ui.launcher as mod

    tree = ast.parse(inspect.getsource(mod))
    engine = {'cli_plot', 'cli_rebar', 'mesh', 'values', 'plotting'}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split('.')[-1] not in engine
