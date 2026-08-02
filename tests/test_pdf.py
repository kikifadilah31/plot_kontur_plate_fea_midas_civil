"""
PDF compilation, image downscaling, and Typst document composition.

The Typst path went untested for a long time — a broken escape sequence
('m\\u00b2', which Typst renders as the literal text "mu00b2") survived
because nothing ever compiled the output. These tests compile for real.
"""

import os

import pytest

from shell_kit.pdf import (
    PdfCompileError, compile_to_pdf, compile_many, downscale_figure,
    PDF_IMAGE_MAX_PX,
)
from shell_kit.report_writer import prepare_figures, print_figure_dir
from shell_kit.reporting_typst import (
    render_report_typst, render_combined_typst, _esc, _h, TYPST_PREAMBLE,
)

MINIMAL = '= Judul\n\nIsi dokumen.\n'


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding='utf-8')
    return str(p)


def _png(path, size=(3000, 2000)):
    from PIL import Image
    Image.new('RGB', size, (200, 30, 30)).save(path)
    return str(path)


# =============================================================================
# Compilation
# =============================================================================

def test_minimal_document_compiles_to_a_real_pdf(tmp_path):
    typ = _write(tmp_path, 'a.typ', MINIMAL)
    pdf, warnings = compile_to_pdf(typ)

    assert os.path.exists(pdf)
    assert pdf.endswith('.pdf')
    with open(pdf, 'rb') as f:
        assert f.read(5) == b'%PDF-'
    assert warnings == []


def test_source_is_kept_after_a_successful_compile(tmp_path):
    """The .typ is the editable source; PDF output must not consume it."""
    typ = _write(tmp_path, 'a.typ', MINIMAL)
    compile_to_pdf(typ)
    assert os.path.exists(typ)


def test_explicit_output_path_is_honoured(tmp_path):
    typ = _write(tmp_path, 'a.typ', MINIMAL)
    target = str(tmp_path / 'lain.pdf')
    pdf, _ = compile_to_pdf(typ, pdf_path=target)
    assert pdf == target
    assert os.path.exists(target)


def test_broken_syntax_raises_with_the_compiler_diagnostic(tmp_path):
    typ = _write(tmp_path, 'bad.typ', '#let x = \n#tidak_ada_fungsi()\n')

    with pytest.raises(PdfCompileError) as excinfo:
        compile_to_pdf(typ)

    assert excinfo.value.typ_path == typ
    assert excinfo.value.diagnostic          # carries something actionable
    assert 'bad.typ' in str(excinfo.value)


def test_failed_compile_leaves_the_source_to_debug(tmp_path):
    """Deleting the .typ on failure would remove the only clue."""
    typ = _write(tmp_path, 'bad.typ', '#panic("gagal")\n')
    with pytest.raises(PdfCompileError):
        compile_to_pdf(typ)
    assert os.path.exists(typ)


def test_missing_image_is_a_failure_not_a_blank_page(tmp_path):
    typ = _write(tmp_path, 'a.typ', '#image("tidak-ada.png")\n')
    with pytest.raises(PdfCompileError):
        compile_to_pdf(typ)


def test_image_above_the_document_needs_a_wider_root(tmp_path):
    """
    Per-source reports link '../_figur_pdf/...', so root must span the run
    folder. Anchoring it at the document's own folder used to fail every one.
    """
    sub = tmp_path / 'Load_MS'
    sub.mkdir()
    shared = tmp_path / 'shared'
    shared.mkdir()
    _png(shared / 'plot.png', size=(200, 150))

    typ = _write(sub, 'r.typ', '#image("../shared/plot.png")\n')

    with pytest.raises(PdfCompileError):
        compile_to_pdf(typ)                       # root = document folder

    pdf, _ = compile_to_pdf(typ, root=str(tmp_path))
    assert os.path.exists(pdf)


def test_compile_many_keeps_going_after_one_failure(tmp_path):
    good1 = _write(tmp_path, 'g1.typ', MINIMAL)
    bad = _write(tmp_path, 'b.typ', '#panic("x")\n')
    good2 = _write(tmp_path, 'g2.typ', MINIMAL)

    written, warnings, failures = compile_many(
        [good1, bad, good2], on_error=lambda e: None,
    )
    assert len(written) == 2
    assert len(failures) == 1
    assert failures[0].typ_path == bad


# =============================================================================
# Image downscaling
# =============================================================================

def test_large_image_is_downscaled(tmp_path):
    from PIL import Image
    src = _png(tmp_path / 'big.png', size=(4152, 4022))
    out = tmp_path / 'print'

    dst = downscale_figure(src, str(out))
    assert dst != src
    with Image.open(dst) as im:
        assert max(im.size) == PDF_IMAGE_MAX_PX
    assert os.path.getsize(dst) < os.path.getsize(src)


def test_small_image_is_left_alone(tmp_path):
    """No point writing a copy of something already small enough."""
    src = _png(tmp_path / 'small.png', size=(800, 600))
    assert downscale_figure(src, str(tmp_path / 'print')) == src


def test_same_filename_in_different_folders_does_not_collide(tmp_path):
    a = tmp_path / 'Load_A'
    b = tmp_path / 'Load_B'
    a.mkdir(); b.mkdir()
    src_a = _png(a / 'plot.png', size=(2500, 2000))
    src_b = _png(b / 'plot.png', size=(2500, 2000))

    out = str(tmp_path / 'print')
    assert downscale_figure(src_a, out) != downscale_figure(src_b, out)


def test_second_call_reuses_the_existing_copy(tmp_path):
    """The combined document re-resolves the same figures."""
    src = _png(tmp_path / 'big.png', size=(3000, 2400))
    out = str(tmp_path / 'print')

    first = downscale_figure(src, out)
    stamp = os.path.getmtime(first)
    second = downscale_figure(src, out)

    assert first == second
    assert os.path.getmtime(second) == stamp


def test_originals_are_never_modified(tmp_path):
    src = _png(tmp_path / 'big.png', size=(3000, 2400))
    before = os.path.getsize(src)
    downscale_figure(src, str(tmp_path / 'print'))
    assert os.path.getsize(src) == before


# =============================================================================
# Wiring into figure preparation
# =============================================================================

def test_print_dir_only_requested_for_pdf(tmp_path):
    assert print_figure_dir('md', str(tmp_path)) is None
    assert print_figure_dir('typst', str(tmp_path)) is None
    assert print_figure_dir('pdf', str(tmp_path)) is not None


def test_prepare_figures_swaps_in_the_downscaled_copy(tmp_path):
    src = _png(tmp_path / 'big.png', size=(3000, 2400))
    out = str(tmp_path / 'print')

    plain = prepare_figures([('c', src)], str(tmp_path))
    reduced = prepare_figures([('c', src)], str(tmp_path), print_dir=out)

    assert plain[0][1] == 'big.png'
    assert reduced[0][1] != 'big.png'
    assert (tmp_path / reduced[0][1]).is_file()


def test_failed_plots_are_dropped_before_downscaling(tmp_path):
    """Downscaling a file that was never rendered would crash the run."""
    missing = str(tmp_path / 'never-rendered.png')
    out = prepare_figures([('c', missing)], str(tmp_path),
                          generated=set(), print_dir=str(tmp_path / 'p'))
    assert out == []


# =============================================================================
# Document composition
# =============================================================================

STATS = {'Fxx (kN/m)': {'max': 10.0, 'min': -5.0, 'mean': 1.0,
                        'max_loc': (1.0, 2.0), 'min_loc': (3.0, 4.0)}}


def test_default_render_is_a_standalone_document():
    doc = render_report_typst('LC1', STATS, 10, 0.4, 'average-nodal')
    assert doc.startswith(TYPST_PREAMBLE[:20])
    assert '\n= ' in doc


def test_fragment_has_no_preamble():
    frag = render_report_typst('LC1', STATS, 10, 0.4, 'average-nodal',
                               preamble=False)
    assert '#set page' not in frag


@pytest.mark.parametrize('offset,expected', [(0, '= '), (1, '== '), (2, '=== ')])
def test_heading_offset_pushes_every_level_down(offset, expected):
    frag = render_report_typst('LC1', STATS, 10, 0.4, 'average-nodal',
                               preamble=False, heading_offset=offset)
    assert frag.lstrip().startswith(expected)


def test_heading_helper_builds_the_right_depth():
    assert _h(1, 'A') == '= A'
    assert _h(2, 'A', 1) == '=== A'


def test_section_units_are_real_characters_not_escape_text():
    """
    'm\\u00b2' is not a Typst escape — it renders as the literal text
    "mu00b2". The unit must be a real character.
    """
    doc = render_report_typst('LC1', STATS, 10, 0.4, 'average-nodal')
    assert '[m²]' in doc
    assert '[m⁴]' in doc
    assert 'u00b2' not in doc
    assert 'u2074' not in doc


def test_generated_report_actually_compiles(tmp_path):
    doc = render_report_typst('LC1', STATS, 10, 0.4, 'average-nodal')
    typ = _write(tmp_path, 'r.typ', doc)
    pdf, warnings = compile_to_pdf(typ)
    assert os.path.exists(pdf)
    assert warnings == []


def test_markup_characters_in_names_survive_compilation(tmp_path):
    """A load case called 'K #1 [uji]' must not break or lose characters."""
    doc = render_report_typst('K #1 [uji] *tebal*', STATS, 10, 0.4,
                              'average-nodal')
    typ = _write(tmp_path, 'r.typ', doc)
    compile_to_pdf(typ)          # must not raise


@pytest.mark.parametrize('raw,fragment', [
    ('a#b', '\\#'),
    ('a[b]', '\\['),
    ('a_b', '\\_'),
    ('a*b', '\\*'),
    ('a$b', '\\$'),
    ('a<b', '\\<'),
])
def test_escape_covers_typst_markup(raw, fragment):
    assert fragment in _esc(raw)


# =============================================================================
# Combined document
# =============================================================================

def _meta():
    return {'title': 'Laporan Uji', 'subtitle': 'Sub',
            'rows': [('Dibuat', '2026-01-01'), ('Tebal', '400 mm')],
            'note': 'Catatan.'}


def test_combined_document_carries_exactly_one_preamble():
    frags = [render_report_typst(f'LC{i}', STATS, 10, 0.4, 'average-nodal',
                                 preamble=False) for i in range(3)]
    doc = render_combined_typst(_meta(), frags)
    assert doc.count('#set page(') == 1


def test_combined_document_has_a_contents_page_and_breaks():
    frags = [render_report_typst(f'LC{i}', STATS, 10, 0.4, 'average-nodal',
                                 preamble=False) for i in range(3)]
    doc = render_combined_typst(_meta(), frags)
    assert '#outline(' in doc
    assert doc.count('#pagebreak()') >= 3      # title, contents, between chapters


def test_combined_chapter_title_is_not_duplicated():
    """
    Fragments already open with their own level-1 heading; adding another
    would print every load case name twice.
    """
    frag = render_report_typst('LC-UNIK', STATS, 10, 0.4, 'average-nodal',
                               preamble=False)
    doc = render_combined_typst(_meta(), [frag])
    assert doc.count('LC-UNIK') == frag.count('LC-UNIK')


def test_combined_document_compiles(tmp_path):
    frags = [render_report_typst(f'LC{i}', STATS, 10, 0.4, 'average-nodal',
                                 preamble=False) for i in range(3)]
    typ = _write(tmp_path, 'gabungan.typ',
                 render_combined_typst(_meta(), frags))
    pdf, warnings = compile_to_pdf(typ)
    assert os.path.exists(pdf)
    assert warnings == []


def test_combined_document_embeds_images_from_subfolders(tmp_path):
    """The combined report sits above the per-source folders its figures live in."""
    sub = tmp_path / 'Load_MS'
    sub.mkdir()
    png = _png(sub / 'plot.png', size=(600, 400))

    figures = prepare_figures([('Kontur', png)], str(tmp_path))
    assert figures[0][1] == 'Load_MS/plot.png'

    frag = render_report_typst('LC1', STATS, 10, 0.4, 'average-nodal',
                               figures=figures, preamble=False)
    typ = _write(tmp_path, 'gabungan.typ',
                 render_combined_typst(_meta(), [frag]))
    pdf, _ = compile_to_pdf(typ, root=str(tmp_path))
    assert os.path.exists(pdf)
