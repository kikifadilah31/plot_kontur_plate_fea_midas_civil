"""
End-to-end CLI smoke tests.

Primarily a guard for A1: `fea-rebar --method all` crashed with a NumPy
broadcast error because the envelope accumulators lived outside the per-method
loop, and each contour method produces arrays of a different length.

Marked slow — these render real plots. Run just the fast suite with:
    uv run pytest -m "not slow"
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / 'example_data_input' / 'example_1' / 'input'

pytestmark = pytest.mark.slow


def _inputs():
    return [
        '--kordinat', str(DATA / 'kordinat_node.csv'),
        '--connectivity', str(DATA / 'connectivity_data.csv'),
        '--gaya', str(DATA / 'gaya_elemen_per_load_case.csv'),
    ]


def _run(module, args, outdir):
    result = subprocess.run(
        [sys.executable, '-m', module, *args, '--output', str(outdir)],
        cwd=REPO, capture_output=True, text=True, timeout=900,
    )
    return result


def _assert_clean(r):
    """
    A run is only clean if nothing failed.

    Both CLIs used to print '[SUCCESS]' and exit 0 even when every single plot
    failed, so checking the return code alone proves nothing.
    """
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert 'plots failed' not in r.stdout, f"stdout:\n{r.stdout}"
    assert '[FAILED]' not in r.stdout, f"stdout:\n{r.stdout}"


@pytest.fixture(scope='module')
def data_available():
    if not (DATA / 'kordinat_node.csv').exists():
        pytest.skip('example_data_input/example_1 not present')


def test_rebar_all_methods_completes(tmp_path, data_available):
    """The exact command that used to die partway through method 2."""
    r = _run('fea_contour.cli_rebar',
             [*_inputs(), '--method', 'all', '--spacing', '150', '--no-mesh'],
             tmp_path)

    _assert_clean(r)
    assert 'broadcast' not in r.stderr
    assert list(tmp_path.rglob('*.png')), 'no plots were produced'

    # Every method must have produced its own envelope folder
    for method in ('average-nodal', 'element-nodal', 'element-center'):
        assert list(tmp_path.rglob(f'Method_{method}/Envelope_Rebar/*.png')), \
            f'no envelope plots for {method}'


@pytest.mark.parametrize('method', ['average-nodal', 'element-nodal', 'element-center'])
def test_every_rebar_method_renders(tmp_path, data_available, method):
    """
    element-center passes polygons and leaves x/y as None; the workers called
    len(x) on that and every single plot failed silently.
    """
    r = _run('fea_contour.cli_rebar',
             [*_inputs(), '--method', method, '--spacing', '150', '--no-mesh'],
             tmp_path)
    _assert_clean(r)
    assert list(tmp_path.rglob('*.png'))


@pytest.mark.parametrize('method', ['average-nodal', 'element-nodal', 'element-center'])
def test_every_plot_method_renders(tmp_path, data_available, method):
    r = _run('fea_contour.cli_plot',
             [*_inputs(), '--method', method, '--no-mesh'],
             tmp_path)
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
    r = _run('fea_contour.cli_rebar',
             [*_inputs(), '--rebar-select', *codes,
              '--spacing', '150', '--no-mesh'],
             tmp_path)

    _assert_clean(r)
    assert list(tmp_path.rglob('*config_s150*.png'))


def test_rebar_shear_runs(tmp_path, data_available):
    r = _run('fea_contour.cli_rebar',
             [*_inputs(), '--shear', '--spacing', '150', '--no-mesh'],
             tmp_path)
    _assert_clean(r)
    assert list(tmp_path.rglob('*Avs*.png'))


def test_no_as_min_flag_lowers_demand(tmp_path, data_available):
    """The escape hatch for reproducing pre-2.0 numbers must work."""
    r = _run('fea_contour.cli_rebar',
             [*_inputs(), '--no-as-min', '--spacing', '150', '--no-mesh'],
             tmp_path)
    _assert_clean(r)
    assert 'As minimum: NONAKTIF' in r.stdout


def test_plot_all_methods_completes(tmp_path, data_available):
    r = _run('fea_contour.cli_plot',
             [*_inputs(), '--method', 'all', '--no-mesh'],
             tmp_path)
    _assert_clean(r)
    assert list(tmp_path.rglob('*.png'))


def test_report_master_completes(tmp_path, data_available):
    r = _run('fea_contour.cli_report',
             [*_inputs(), '--master'],
             tmp_path)
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert list(tmp_path.rglob('MASTER_SUMMARY.md'))
