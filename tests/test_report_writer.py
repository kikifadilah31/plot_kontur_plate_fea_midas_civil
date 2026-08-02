"""
Figure path resolution shared by both commands' reports.

A report links its images relative to itself, so getting this wrong produces a
document full of broken images that still looks like it worked.
"""

import os

import pytest

from shell_kit.report_writer import (
    relative_figure, prepare_figures, write_document,
)


def test_figure_in_same_folder_is_a_bare_filename(tmp_path):
    doc = tmp_path / 'case'
    fig = doc / 'plot.png'
    assert relative_figure(str(fig), str(doc)) == 'plot.png'


def test_figure_one_level_up_walks_out(tmp_path):
    doc = tmp_path / 'case'
    fig = tmp_path / 'plot.png'
    assert relative_figure(str(fig), str(doc)) == '../plot.png'


def test_paths_always_use_forward_slashes(tmp_path):
    """Markdown and Typst both need '/', including on Windows."""
    doc = tmp_path / 'case'
    fig = tmp_path / 'other' / 'deep' / 'plot.png'
    rel = relative_figure(str(fig), str(doc))
    assert '\\' not in rel
    assert rel.endswith('other/deep/plot.png')


def test_figures_that_failed_to_render_are_dropped(tmp_path):
    """
    Linking a plot that never made it to disk would send the reader to a
    broken image with no explanation.
    """
    ok = str(tmp_path / 'good.png')
    missing = str(tmp_path / 'bad.png')

    out = prepare_figures(
        [('good', ok), ('bad', missing)],
        str(tmp_path),
        generated={ok},
    )
    assert out == [('good', 'good.png')]


def test_without_a_generated_set_existence_on_disk_decides(tmp_path):
    ok = tmp_path / 'good.png'
    ok.write_bytes(b'x')
    missing = tmp_path / 'bad.png'

    out = prepare_figures(
        [('good', str(ok)), ('bad', str(missing))], str(tmp_path),
    )
    assert out == [('good', 'good.png')]


def test_empty_and_none_figure_lists_are_safe(tmp_path):
    assert prepare_figures(None, str(tmp_path)) == []
    assert prepare_figures([], str(tmp_path)) == []


def test_write_document_creates_missing_parents(tmp_path):
    target = tmp_path / 'a' / 'b' / 'report.md'
    write_document('halo', str(target))
    assert target.read_text(encoding='utf-8') == 'halo'


def test_write_document_uses_utf8(tmp_path):
    """Reports carry 'ρ', 'β₁', 'mm²' and Indonesian text."""
    target = tmp_path / 'report.md'
    write_document('ρ maksimum, β₁, mm²/m', str(target))
    assert 'ρ' in target.read_text(encoding='utf-8')
