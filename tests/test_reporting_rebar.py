"""
Reinforcement report content, and the envelope rule it depends on.
"""

import numpy as np
import pytest

from shell_kit.reporting_rebar import (
    summarize_case, _label_selection, _fmt_depth,
    render_rebar_report_md, render_rebar_report_typst,
)

COORDS = (np.array([0.0, 1.0, 2.0, 3.0]), np.array([0.0, 0.0, 1.0, 1.0]))


def _params(**over):
    p = {
        'h_mm': 400.0, 'cover': 40.0, 'fc': 30.0, 'fy': 420.0,
        'method': 'average-nodal', 'mode_desc': 'Mode B: s=150mm',
        'apply_min': True, 'as_min': 720.0, 'rho_max': 0.018793,
        'beta1': 0.835714, 'generated': '2026-01-01 00:00:00',
    }
    p.update(over)
    return p


# =============================================================================
# Envelope semantics — np.maximum vs np.fmax
# =============================================================================

def test_envelope_must_propagate_failures_not_discard_them():
    """
    The envelope is what the design is taken from. np.fmax discards NaN, so a
    node would only read as inadequate if EVERY load case failed there — a
    node failing under one case would silently look fine.
    """
    case_a = np.array([np.nan, 500.0])
    case_b = np.array([300.0, 400.0])

    assert not np.isnan(np.fmax(case_a, case_b)[0])       # the old behaviour
    assert np.isnan(np.maximum(case_a, case_b)[0])        # what we now do


def test_envelope_still_takes_the_larger_demand():
    a = np.array([300.0, 900.0])
    b = np.array([500.0, 400.0])
    assert np.maximum(a, b).tolist() == [500.0, 900.0]


# =============================================================================
# summarize_case
# =============================================================================

def test_counts_and_locates_inadequate_points():
    As = np.array([100.0, np.nan, 800.0, np.nan])
    s = summarize_case(As, None, 350.0, COORDS)

    assert s['n_inadequate'] == 2
    assert s['inadequate_points'] == [(1.0, 0.0), (3.0, 1.0)]
    assert s['as_max'] == pytest.approx(800.0)
    assert s['max_loc'] == (2.0, 1.0)


def test_inadequate_listing_is_capped_and_flagged():
    n = 50
    As = np.full(n, np.nan)
    coords = (np.arange(n, dtype=float), np.zeros(n))
    s = summarize_case(As, None, 350.0, coords, max_listed=5)

    assert s['n_inadequate'] == n
    assert len(s['inadequate_points']) == 5
    assert s['inadequate_truncated'] is True


def test_clean_case_reports_nothing_to_fix():
    As = np.array([100.0, 200.0, 300.0, 400.0])
    s = summarize_case(As, None, 350.0, COORDS)
    assert s['n_inadequate'] == 0
    assert s['inadequate_points'] == []
    assert 'inadequate_truncated' not in s


def test_depth_range_reported_from_per_node_array():
    As = np.array([100.0, 200.0, 300.0, 400.0])
    d = np.array([344.0, 348.0, 352.0, 352.0])
    s = summarize_case(As, None, d, COORDS)
    assert s['d_min'] == 344.0
    assert s['d_max'] == 352.0
    assert _fmt_depth(s) == '344-352'


def test_uniform_depth_collapses_to_one_number():
    s = summarize_case(np.array([100.0] * 4), None, 352.0, COORDS)
    assert _fmt_depth(s) == '352'


def test_selection_at_max_uses_the_governing_node():
    As = np.array([100.0, 200.0, 900.0, 400.0])
    sel = np.array([13.0, 16.0, 32.0, 19.0])
    s = summarize_case(As, sel, 350.0, COORDS, kind='diameter')
    assert s['selection_at_max'] == 'D32'


# =============================================================================
# Selection labels
# =============================================================================

@pytest.mark.parametrize('value,kind,labels,expected', [
    (25.0, 'diameter', None, 'D25'),
    (0.0, 'diameter', None, '-'),
    (np.nan, 'diameter', None, 'TIDAK MEMADAI'),
    (2.0, 'config', ['16', '2D25', '3D32'], '2D25'),
    (np.nan, 'config', ['16'], 'TIDAK MEMADAI'),
    (180.0, 'spacing', None, 's = 180 mm'),
    (np.inf, 'spacing', None, 'tanpa tulangan'),
    (np.nan, 'spacing', None, 'TIDAK MEMADAI'),
])
def test_selection_labels_read_correctly_per_mode(value, kind, labels, expected):
    assert _label_selection(value, kind, labels) == expected


def test_out_of_range_config_index_does_not_crash():
    assert _label_selection(9.0, 'config', ['16']) == 'idx 9'


# =============================================================================
# Rendering
# =============================================================================

def _sample_cases():
    good = summarize_case(np.array([100.0, 200.0, 300.0, 400.0]),
                          np.array([13.0, 16.0, 19.0, 22.0]),
                          350.0, COORDS, kind='diameter')
    bad = summarize_case(np.array([100.0, np.nan, 300.0, np.nan]),
                         np.array([13.0, np.nan, 19.0, np.nan]),
                         np.array([344.0, 344.0, 352.0, 352.0]),
                         COORDS, kind='diameter')
    return [('Tulangan Bawah (Arah X)', good), ('Tulangan Atas (Arah Y)', bad)]


def test_markdown_report_contains_every_required_section():
    doc = render_rebar_report_md('LC1', _sample_cases(), _params())
    for heading in ('Parameter Desain', 'Ringkasan per Lapis',
                    'Zona SECTION INADEQUATE'):
        assert heading in doc
    assert 'As minimum (SNI 24.4.3.2) | 720' in doc
    assert '0.01879' in doc            # rho_max
    assert 'Tulangan Bawah (Arah X)' in doc


def test_markdown_report_lists_failure_coordinates():
    doc = render_rebar_report_md('LC1', _sample_cases(), _params())
    assert '1.000' in doc and '3.000' in doc
    assert 'tebal pelat' in doc.lower()   # the actionable advice


def test_markdown_report_says_so_when_nothing_fails():
    cases = [_sample_cases()[0]]
    doc = render_rebar_report_md('LC1', cases, _params())
    assert 'Tidak ada titik yang gagal' in doc


def test_disabled_as_min_is_called_out_not_hidden():
    doc = render_rebar_report_md('LC1', _sample_cases(),
                                 _params(apply_min=False))
    assert 'NONAKTIF' in doc


def test_markdown_embeds_figures():
    figs = [('As perlu', 'rebar_As_Mxx_Bottom_X.png')]
    doc = render_rebar_report_md('LC1', _sample_cases(), _params(), figures=figs)
    assert '![As perlu](rebar_As_Mxx_Bottom_X.png)' in doc


def test_typst_report_renders_and_embeds_figures():
    figs = [('As perlu', 'rebar_As_Mxx_Bottom_X.png')]
    doc = render_rebar_report_typst('LC1', _sample_cases(), _params(),
                                    figures=figs)
    assert '#figure(' in doc
    assert 'image("rebar_As_Mxx_Bottom_X.png"' in doc
    assert 'Parameter Desain' in doc
    assert 'SECTION INADEQUATE' in doc


def test_typst_escapes_markup_characters_in_captions():
    """An unescaped '#' or '[' would break Typst compilation."""
    figs = [('As #1 [atas]', 'a.png')]
    doc = render_rebar_report_typst('LC1', _sample_cases(), _params(),
                                    figures=figs)
    assert '\\#1' in doc
    assert '\\[atas\\]' in doc


def test_reports_render_without_figures():
    for render in (render_rebar_report_md, render_rebar_report_typst):
        doc = render('LC1', _sample_cases(), _params())
        assert 'Parameter Desain' in doc


# =============================================================================
# Shear summary
# =============================================================================

from shell_kit.reporting_rebar import summarize_shear_case


def test_shear_summary_separates_crushing_from_demand():
    """
    Av/s = nan means web crushing — no stirrup solves it. That must not be
    lumped in with nodes that merely need stirrups.
    """
    Av_s = np.array([0.0, 0.5, np.nan, 1.2])
    D = np.array([0.0, 10.0, np.nan, 13.0])
    s = summarize_shear_case(Av_s, D, 350.0, COORDS)

    assert s['n_inadequate'] == 1            # crushing
    assert s['n_needing_stirrups'] == 2      # 0.5 and 1.2
    assert s['avs_max'] == pytest.approx(1.2)
    assert s['diameter_at_max'] == 'D13'
    assert s['inadequate_points'] == [(2.0, 1.0)]


def test_shear_case_with_no_stirrups_needed_is_quiet():
    s = summarize_shear_case(np.zeros(4), np.zeros(4), 350.0, COORDS)
    assert s['n_inadequate'] == 0
    assert s['n_needing_stirrups'] == 0
    assert s['max_loc'] is None


# =============================================================================
# Section failure vs no bar that fits — different problems, different fixes
# =============================================================================

def test_no_bar_fits_is_counted_separately_from_section_failure():
    """
    As computable but no available diameter satisfies it is NOT the same as
    the section being unable to carry the moment. Counting only the latter
    left a real problem invisible: the report showed 'TIDAK MEMADAI' in the
    bar column beside a failure count of zero.
    """
    As = np.array([100.0, 5000.0, np.nan, 200.0])
    selection = np.array([13.0, np.nan, np.nan, 16.0])

    s = summarize_case(As, selection, 350.0, COORDS, kind='diameter')

    assert s['n_inadequate'] == 1     # only the nan As
    assert s['n_no_bar'] == 1         # As fine, but nothing fits


def test_no_bar_count_is_zero_when_everything_fits():
    As = np.array([100.0, 200.0, 300.0, 400.0])
    sel = np.array([13.0, 16.0, 19.0, 22.0])
    assert summarize_case(As, sel, 350.0, COORDS)['n_no_bar'] == 0


def test_markdown_shows_both_failure_columns():
    cases = [('Atas (X)', summarize_case(
        np.array([100.0, 5000.0, np.nan, 200.0]),
        np.array([13.0, np.nan, np.nan, 16.0]),
        350.0, COORDS, kind='diameter'))]
    doc = render_rebar_report_md('LC1', cases, _params())

    assert 'Penampang gagal' in doc
    assert 'Tulangan tak muat' in doc
    assert 'rebar-select' in doc          # the actionable remedy


def test_typst_report_with_shear_compiles():
    from shell_kit.pdf import compile_to_pdf
    import tempfile, os

    shear = [('Geser Arah X', summarize_shear_case(
        np.array([0.0, 0.5, np.nan, 1.2]),
        np.array([0.0, 10.0, np.nan, 13.0]), 350.0, COORDS))]
    doc = render_rebar_report_typst('LC1', _sample_cases(), _params(),
                                    shear_cases=shear)
    assert 'Ringkasan Tulangan Geser' in doc

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'r.typ')
        open(p, 'w', encoding='utf-8').write(doc)
        pdf, warns = compile_to_pdf(p)
        assert os.path.exists(pdf)
        assert warns == []


def test_shear_failures_appear_in_the_coordinate_listing():
    shear = [('Geser Arah X', summarize_shear_case(
        np.array([0.0, np.nan, 0.0, 0.0]),
        np.array([0.0, np.nan, 0.0, 0.0]), 350.0, COORDS))]
    doc = render_rebar_report_md('LC1', [_sample_cases()[0]], _params(),
                                 shear_cases=shear)
    assert 'Geser Arah X' in doc
    assert '1.000' in doc               # coordinate of the crushing node
