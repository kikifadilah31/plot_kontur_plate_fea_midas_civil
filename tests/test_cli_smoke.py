"""
End-to-end smoke tests for the unified `shell-kit` CLI.

Guards several bugs that only surface when the whole pipeline runs:
  - `rebar --method all` crashed on a NumPy broadcast error
  - `--method element-center` produced zero plots in both commands
  - both commands printed [SUCCESS] and exited 0 even when everything failed

Marked slow — these render real plots. Run just the fast suite with:
    uv run pytest -m "not slow"
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / 'example_data_input' / 'example_1' / 'input'
MODULE = 'shell_kit.cli'

pytestmark = pytest.mark.slow


def _inputs():
    return [
        '--kordinat', str(DATA / 'kordinat_node.csv'),
        '--connectivity', str(DATA / 'connectivity_data.csv'),
        '--gaya', str(DATA / 'gaya_elemen_per_load_case.csv'),
    ]


def _run(subcommand, args, outdir):
    return subprocess.run(
        [sys.executable, '-m', MODULE, subcommand, *args,
         '--output', str(outdir)],
        cwd=REPO, capture_output=True, text=True, timeout=900,
    )


def _assert_clean(r):
    """
    A run is only clean if nothing failed.

    Both commands used to print '[SUCCESS]' and exit 0 even when every single
    plot failed, so checking the return code alone proves nothing.
    """
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert 'plots failed' not in r.stdout, f"stdout:\n{r.stdout}"
    assert '[FAILED]' not in r.stdout, f"stdout:\n{r.stdout}"


@pytest.fixture(scope='module')
def data_available():
    if not (DATA / 'kordinat_node.csv').exists():
        pytest.skip('example_data_input/example_1 not present')


# =============================================================================
# Command surface
# =============================================================================

def test_bare_command_shows_help_and_exits_nonzero():
    r = subprocess.run([sys.executable, '-m', MODULE],
                       cwd=REPO, capture_output=True, text=True, timeout=60)
    assert r.returncode == 2
    assert 'plot' in r.stdout and 'rebar' in r.stdout


def test_old_commands_are_gone():
    """fea-plot / fea-report / fea-rebar were removed outright."""
    pyproject = (REPO / 'pyproject.toml').read_text(encoding='utf-8')
    assert 'shell-kit = "shell_kit.cli:entry_point"' in pyproject
    for old in ('fea-plot', 'fea-rebar', 'fea-report'):
        assert old not in pyproject


@pytest.mark.parametrize('sub', ['plot', 'rebar'])
def test_report_flags_exist_on_every_subcommand(sub):
    r = subprocess.run([sys.executable, '-m', MODULE, sub, '--help'],
                       cwd=REPO, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0
    assert '--report' in r.stdout
    assert '--format' in r.stdout
    # Shared options must reach both subcommands
    assert '--comb-select' in r.stdout
    assert '--no-annotation' in r.stdout


# =============================================================================
# Rendering
# =============================================================================

def test_rebar_all_methods_completes(tmp_path, data_available):
    """The exact command that used to die partway through method 2."""
    r = _run('rebar', [*_inputs(), '--method', 'all',
                       '--spacing', '150', '--no-mesh'], tmp_path)

    _assert_clean(r)
    assert 'broadcast' not in r.stderr
    assert list(tmp_path.rglob('*.png')), 'no plots were produced'

    for method in ('average-nodal', 'element-nodal', 'element-center'):
        assert list(tmp_path.rglob(f'Method_{method}/Envelope_Rebar/*.png')), \
            f'no envelope plots for {method}'


@pytest.mark.parametrize('method', ['average-nodal', 'element-nodal', 'element-center'])
def test_every_rebar_method_renders(tmp_path, data_available, method):
    """
    element-center passes polygons and leaves x/y as None; the workers called
    len(x) on that and every single plot failed silently.
    """
    r = _run('rebar', [*_inputs(), '--method', method,
                       '--spacing', '150', '--no-mesh'], tmp_path)
    _assert_clean(r)
    assert list(tmp_path.rglob('*.png'))


@pytest.mark.parametrize('method', ['average-nodal', 'element-nodal', 'element-center'])
def test_every_plot_method_renders(tmp_path, data_available, method):
    r = _run('plot', [*_inputs(), '--method', method, '--no-mesh'], tmp_path)
    _assert_clean(r)
    assert list(tmp_path.rglob('*.png'))


def test_rebar_with_every_config_selected(tmp_path, data_available):
    """All 24 configs need 26 colour bins — this used to fail every plot."""
    codes = [
        '13', '16', '19', '22', '25', '32',
        '2D13', '2D16', '2D19', '2D22', '2D25', '2D32',
        '3D13', '3D16', '3D19', '3D22', '3D25', '3D32',
        '4D13', '4D16', '4D19', '4D22', '4D25', '4D32',
    ]
    r = _run('rebar', [*_inputs(), '--rebar-select', *codes,
                       '--spacing', '150', '--no-mesh'], tmp_path)
    _assert_clean(r)
    assert list(tmp_path.rglob('*config_s150*.png'))


def test_rebar_shear_runs(tmp_path, data_available):
    r = _run('rebar', [*_inputs(), '--shear', '--spacing', '150',
                       '--no-mesh'], tmp_path)
    _assert_clean(r)
    assert list(tmp_path.rglob('*Avs*.png'))


def test_no_as_min_flag_lowers_demand(tmp_path, data_available):
    """The escape hatch for reproducing pre-2.0 numbers must work."""
    r = _run('rebar', [*_inputs(), '--no-as-min', '--spacing', '150',
                       '--no-mesh'], tmp_path)
    _assert_clean(r)
    assert 'As minimum: NONAKTIF' in r.stdout


def test_plot_all_methods_completes(tmp_path, data_available):
    r = _run('plot', [*_inputs(), '--method', 'all', '--no-mesh'], tmp_path)
    _assert_clean(r)
    assert list(tmp_path.rglob('*.png'))


# =============================================================================
# Reports
# =============================================================================

def _figures_resolve(doc, pattern):
    """Every embedded image path in `doc` must exist relative to the document."""
    import re
    refs = re.findall(pattern, doc.read_text(encoding='utf-8'))
    assert refs, f'no figures embedded in {doc.name}'
    for rel in refs:
        assert (doc.parent / rel).is_file(), f'broken figure link: {rel}'
    return refs


def test_plot_report_markdown_embeds_working_figures(tmp_path, data_available):
    r = _run('plot', [*_inputs(), '--no-mesh', '--report'], tmp_path)
    _assert_clean(r)

    reports = list(tmp_path.rglob('Summary_*.md'))
    assert reports
    assert list(tmp_path.rglob('MASTER_SUMMARY.md'))
    _figures_resolve(reports[0], r'!\[[^\]]*\]\(([^)]+)\)')


def test_plot_report_typst(tmp_path, data_available):
    r = _run('plot', [*_inputs(), '--no-mesh', '--report',
                      '--format', 'typst'], tmp_path)
    _assert_clean(r)

    reports = list(tmp_path.rglob('Summary_*.typ'))
    assert reports
    assert list(tmp_path.rglob('MASTER_SUMMARY.typ'))
    _figures_resolve(reports[0], r'image\("([^"]+)"')


def test_rebar_report_markdown_has_content_and_figures(tmp_path, data_available):
    r = _run('rebar', [*_inputs(), '--spacing', '150', '--shear',
                       '--no-mesh', '--report'], tmp_path)
    _assert_clean(r)

    reports = list(tmp_path.rglob('Laporan_Tulangan_*.md'))
    assert reports
    doc = reports[0].read_text(encoding='utf-8')

    # The sections an engineer needs
    assert 'Parameter Desain' in doc
    assert 'Ringkasan per Lapis' in doc
    assert 'SECTION INADEQUATE' in doc
    assert 'As minimum (SNI 24.4.3.2)' in doc
    assert 'ρ maksimum' in doc

    _figures_resolve(reports[0], r'!\[[^\]]*\]\(([^)]+)\)')


def test_rebar_report_typst(tmp_path, data_available):
    r = _run('rebar', [*_inputs(), '--spacing', '150', '--no-mesh',
                       '--report', '--format', 'typst'], tmp_path)
    _assert_clean(r)

    reports = list(tmp_path.rglob('Laporan_Tulangan_*.typ'))
    assert reports
    _figures_resolve(reports[0], r'image\("([^"]+)"')


def test_format_without_report_warns(tmp_path, data_available):
    """Silently ignoring the flag would leave the user waiting for a file."""
    r = _run('rebar', [*_inputs(), '--spacing', '150', '--no-mesh',
                       '--format', 'typst'], tmp_path)
    _assert_clean(r)
    assert '--format typst diabaikan' in r.stdout


def test_no_reports_written_without_the_flag(tmp_path, data_available):
    r = _run('rebar', [*_inputs(), '--spacing', '150', '--no-mesh'], tmp_path)
    _assert_clean(r)
    assert not list(tmp_path.rglob('Laporan_Tulangan_*'))


# =============================================================================
# PDF
# =============================================================================

def _assert_real_pdfs(paths, min_kb=20):
    assert paths, 'tidak ada PDF dihasilkan'
    for p in paths:
        data = p.read_bytes()
        assert data[:5] == b'%PDF-', f'{p.name} bukan PDF'
        assert len(data) > min_kb * 1024, f'{p.name} mencurigakan kecil'


def test_rebar_pdf_compiles_every_report(tmp_path, data_available):
    """
    The end-to-end proof that the Typst output is valid: every report the
    pipeline emits is handed to the compiler for real.
    """
    r = _run('rebar', [*_inputs(), '--spacing', '150', '--shear',
                       '--no-mesh', '--report', '--format', 'pdf'], tmp_path)
    _assert_clean(r)

    per_source = list(tmp_path.rglob('Laporan_Tulangan_*.pdf'))
    combined = list(tmp_path.rglob('LAPORAN_LENGKAP.pdf'))
    _assert_real_pdfs(per_source)
    _assert_real_pdfs(combined)

    # The .typ source is kept alongside so layout can be edited and recompiled
    assert list(tmp_path.rglob('Laporan_Tulangan_*.typ'))
    assert list(tmp_path.rglob('LAPORAN_LENGKAP.typ'))


def test_plot_pdf_compiles_reports_and_master(tmp_path, data_available):
    r = _run('plot', [*_inputs(), '--no-mesh', '--report',
                      '--format', 'pdf'], tmp_path)
    _assert_clean(r)

    _assert_real_pdfs(list(tmp_path.rglob('Summary_*.pdf')))
    _assert_real_pdfs(list(tmp_path.rglob('MASTER_SUMMARY.pdf')), min_kb=5)
    _assert_real_pdfs(list(tmp_path.rglob('LAPORAN_LENGKAP.pdf')))


def test_pdf_images_are_downscaled_not_embedded_whole(tmp_path, data_available):
    """
    Embedding the 620 dpi plots verbatim produced 16 MB per report and a
    178 MB combined document — too big to send anywhere.
    """
    r = _run('rebar', [*_inputs(), '--spacing', '150', '--no-mesh',
                       '--report', '--format', 'pdf'], tmp_path)
    _assert_clean(r)

    assert list(tmp_path.rglob('_figur_pdf/*.png')), 'gambar print tidak dibuat'

    for pdf in tmp_path.rglob('Laporan_Tulangan_*.pdf'):
        size_mb = pdf.stat().st_size / 1048576
        assert size_mb < 12, f'{pdf.name} = {size_mb:.1f} MB, terlalu besar'

    # Originals must be untouched — they are the high-resolution deliverable.
    # Check pixel dimensions, not file size: a diameter plot is mostly flat
    # colour and compresses to a fraction of an As plot at identical
    # resolution, so size proves nothing.
    from PIL import Image
    from shell_kit.pdf import PDF_IMAGE_MAX_PX

    originals = list(tmp_path.rglob('Load_*/rebar_*.png'))
    assert originals
    for png in originals:
        with Image.open(png) as im:
            assert max(im.size) > PDF_IMAGE_MAX_PX, f'{png.name} ikut diperkecil'

    for png in tmp_path.rglob('_figur_pdf/*.png'):
        with Image.open(png) as im:
            assert max(im.size) == PDF_IMAGE_MAX_PX


def test_typst_format_leaves_images_at_full_resolution(tmp_path, data_available):
    """Downscaling is a PDF concern; --format typst must not alter figures."""
    r = _run('rebar', [*_inputs(), '--spacing', '150', '--no-mesh',
                       '--report', '--format', 'typst'], tmp_path)
    _assert_clean(r)
    assert not list(tmp_path.rglob('_figur_pdf'))
    assert not list(tmp_path.rglob('*.pdf'))
