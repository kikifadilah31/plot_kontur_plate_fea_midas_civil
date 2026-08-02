"""
Report file writing — shared by `shell-kit plot` and `shell-kit rebar`.

Handles the parts that are identical whichever command asked for the report:
resolving figure paths relative to where the document will live, skipping
figures whose PNG never made it to disk, and writing the file.
"""

import os


def relative_figure(figure_path, doc_folder):
    """
    Path to `figure_path` as written inside a document stored in `doc_folder`.

    Markdown and Typst both resolve image paths relative to the document, and
    both want forward slashes even on Windows.
    """
    rel = os.path.relpath(figure_path, doc_folder)
    return rel.replace(os.sep, '/')


def prepare_figures(figures, doc_folder, generated=None, print_dir=None):
    """
    Turn absolute figure paths into document-relative ones, dropping any whose
    PNG was not actually produced.

    A report that links a plot which failed to render would send the reader to
    a broken image with no explanation, so those are filtered out here.

    Parameters
    ----------
    figures : list of (caption, absolute_path)
    doc_folder : str — folder the document will be written to.
    generated : set of str, optional — paths that were successfully written.
        When None, every figure is assumed present.
    print_dir : str, optional
        When set, each figure is swapped for a downscaled print copy kept in
        this folder. Used for PDF output, where embedding the full-resolution
        plots produced 16 MB per report.

    Returns
    -------
    list of (caption, relative_path)
    """
    out = []
    for caption, path in figures or []:
        if generated is not None and path not in generated:
            continue
        if generated is None and not os.path.exists(path):
            continue
        if print_dir:
            from .pdf import downscale_figure
            path = downscale_figure(path, print_dir)
        out.append((caption, relative_figure(path, doc_folder)))
    return out


def print_figure_dir(fmt, out_folder):
    """Folder for downscaled print copies, or None when they aren't needed."""
    if fmt != 'pdf':
        return None
    from .pdf import PRINT_FIGURE_DIR
    return os.path.join(out_folder, PRINT_FIGURE_DIR)


def write_document(content, output_path):
    """Write a report to disk, creating parent folders as needed."""
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return output_path


COMBINED_STEM = 'LAPORAN_LENGKAP'


def uses_typst(fmt):
    """True for the formats built on Typst — 'typst' and 'pdf'."""
    return fmt in ('typst', 'pdf')


def document_ext(fmt):
    """Extension of the SOURCE document (PDF is compiled from .typ)."""
    return '.typ' if uses_typst(fmt) else '.md'


def write_reports(sources, source_meta, envelope, thickness, method, fmt,
                  out_folder, generated=None, run_meta=None):
    """
    Write per-source reports plus the master summary for `shell-kit plot`.

    For Typst-based formats a combined document covering the whole run is
    written too, at `out_folder`.

    Parameters
    ----------
    sources : dict — {name: (stats, n_points)} from extract_statistics().
    source_meta : dict — {name: {'folder', 'figures', ...}}.
    envelope : dict or None — from compute_master_envelope().
    thickness : float
    method : str
    fmt : 'md', 'typst' or 'pdf'
    out_folder : str — where the master and combined documents go.
    generated : set of str, optional — successfully rendered PNG paths.
    run_meta : dict, optional — title page fields for the combined document.

    Returns
    -------
    list of str : written source-document paths (.md or .typ).
    """
    from .math_utils import safe_filename
    from .reporting import render_report_md, render_master_md
    from .reporting_typst import (
        render_report_typst, render_master_typst, render_combined_typst,
    )

    typst_mode = uses_typst(fmt)
    ext = document_ext(fmt)
    render_one = render_report_typst if typst_mode else render_report_md
    render_master = render_master_typst if typst_mode else render_master_md

    written = []
    fragments = []
    pdir = print_figure_dir(fmt, out_folder)

    for name, (stats, n_points) in sources.items():
        meta = source_meta.get(name, {})
        folder = meta.get('folder', out_folder)
        figures = prepare_figures(meta.get('figures'), folder, generated, pdir)

        title = name if name.startswith('Comb:') else f'Load Case: {name}'
        content = render_one(title, stats, n_points, thickness, method,
                             figures=figures)

        clean = name.replace('Comb: ', '')
        path = os.path.join(folder, f'Summary_{safe_filename(clean)}{ext}')
        written.append(write_document(content, path))

        if typst_mode:
            # Figures re-resolved against the COMBINED document's folder, so
            # the same image file is reachable from both documents.
            fragments.append(render_report_typst(
                title, stats, n_points, thickness, method,
                figures=prepare_figures(meta.get('figures'), out_folder,
                                        generated, pdir),
                preamble=False,
            ))

    master_body = None
    if envelope:
        written.append(write_document(
            render_master(envelope, thickness, method),
            os.path.join(out_folder, f'MASTER_SUMMARY{ext}'),
        ))
        if typst_mode:
            master_body = render_master_typst(
                envelope, thickness, method, preamble=False,
            )

    if typst_mode and fragments:
        written.append(write_document(
            render_combined_typst(run_meta or {'title': 'Laporan'},
                                  fragments, master_body),
            os.path.join(out_folder, f'{COMBINED_STEM}{ext}'),
        ))

    return written


def compile_pdfs(typ_paths, out_folder=None):
    """
    Compile written .typ documents to PDF and report what happened.

    Prints a per-file summary and any Typst warnings — a warning usually means
    a figure or font did not resolve, which silently degrades the document.

    Returns
    -------
    tuple of (pdf_paths, n_failed)
    """
    from .pdf import compile_many

    # Root spans the whole run folder: per-source documents reference the
    # shared print-figure folder that sits above them.
    written, warnings, failures = compile_many(typ_paths, root=out_folder)

    for typ_path, warning in warnings:
        print(f"  [WARN] {os.path.basename(typ_path)}: {warning}")

    for path in written:
        shown = os.path.relpath(path, out_folder) if out_folder else path
        print(f"    {shown}")

    return written, len(failures)
