"""
PDF compilation — Typst source in, PDF out, entirely inside Python.

Uses the `typst` package, the official binding that bundles the Typst
compiler as a native extension. No external `typst` binary is required.

The .typ file is always kept: it is the editable source, and when compilation
fails it is the only thing that makes the error diagnosable.
"""

import hashlib
import os

# Plots are saved at 300 dpi on a 14-inch figure — about 4150 px, or ~620 dpi
# once placed at A4 text width. Embedding that verbatim produced 16 MB per
# report. 1600 px is ~240 dpi on A4: still sharp in print and when zoomed, at
# roughly a third of the size. The original PNGs are never modified.
PDF_IMAGE_MAX_PX = 1600
PRINT_FIGURE_DIR = '_figur_pdf'


class PdfCompileError(RuntimeError):
    """Typst refused to compile a document. Carries the compiler diagnostic."""

    def __init__(self, typ_path, diagnostic):
        self.typ_path = typ_path
        self.diagnostic = diagnostic
        super().__init__(f"gagal mengompilasi {os.path.basename(typ_path)}:\n{diagnostic}")


def downscale_figure(src, out_dir, max_px=PDF_IMAGE_MAX_PX):
    """
    Return a print-sized copy of `src`, creating it on first use.

    Images already at or below `max_px` are returned unchanged — no point
    writing a copy of the same thing.

    Copies land in one shared folder rather than beside each plot, so they are
    easy to spot and delete, and so the per-source and combined documents can
    reference the very same file.

    Parameters
    ----------
    src : str — path to the original PNG.
    out_dir : str — folder to hold the print copies.
    max_px : int — longest edge of the result.

    Returns
    -------
    str : path to the image a PDF-bound document should reference.
    """
    from PIL import Image

    with Image.open(src) as probe:
        if max(probe.size) <= max_px:
            return src

    # Hash the source path so plots with the same filename in different load
    # case folders cannot overwrite one another.
    digest = hashlib.sha1(os.path.abspath(src).encode('utf-8')).hexdigest()[:8]
    dst = os.path.join(out_dir, f'{digest}_{os.path.basename(src)}')

    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return dst  # already built this run (the combined document reuses it)

    os.makedirs(out_dir, exist_ok=True)
    with Image.open(src) as im:
        im = im.convert('RGB') if im.mode in ('P', 'RGBA') else im
        im.thumbnail((max_px, max_px), Image.LANCZOS)
        im.save(dst, format='PNG', optimize=True)

    return dst


def _load_typst():
    """
    Import the compiler, turning a missing package into actionable advice.

    The likely cause is an install predating the PDF feature, where the new
    dependency was never pulled in.
    """
    try:
        import typst
    except ImportError as exc:
        raise PdfCompileError(
            '<typst>',
            "Paket 'typst' tidak ditemukan. Ini dibutuhkan untuk --format pdf.\n"
            "  Perbarui instalasi Anda:\n"
            "    uv tool upgrade shell-kit\n"
            "  atau, bila menjalankan dari clone:\n"
            "    uv sync",
        ) from exc
    return typst


def compile_to_pdf(typ_path, pdf_path=None, root=None):
    """
    Compile a Typst document to PDF.

    Parameters
    ----------
    typ_path : str
        Path to the .typ source. Kept on disk either way.
    pdf_path : str, optional
        Output path. Defaults to the source path with a .pdf suffix.
    root : str, optional
        Directory Typst may read files from. Must contain every image the
        document references — a per-source report links '../_figur_pdf/...',
        which sits above its own folder, so the caller passes the run folder.
        Defaults to the document's own folder.

    Returns
    -------
    tuple of (pdf_path, warnings)
        warnings is a list of strings — surfaced by the caller rather than
        swallowed, since a missing font or unresolved image degrades the
        document silently otherwise.

    Raises
    ------
    PdfCompileError : compilation failed; .typ is left in place to inspect.
    """
    typst = _load_typst()

    if pdf_path is None:
        pdf_path = os.path.splitext(typ_path)[0] + '.pdf'

    root = os.path.abspath(root) if root else (
        os.path.dirname(os.path.abspath(typ_path)) or '.'
    )

    try:
        pdf_bytes, warnings = typst.compile_with_warnings(typ_path, root=root)
    except Exception as exc:
        raise PdfCompileError(typ_path, str(exc)) from exc

    # compile_with_warnings returns bytes for a single-page-format compile;
    # some versions hand back a list of per-page buffers.
    if isinstance(pdf_bytes, list):
        pdf_bytes = pdf_bytes[0]

    with open(pdf_path, 'wb') as f:
        f.write(pdf_bytes)

    return pdf_path, [str(w) for w in (warnings or [])]


def compile_many(typ_paths, root=None, on_error=None):
    """
    Compile several documents, carrying on after a failure.

    One broken report should not cost the user every other PDF in the run.

    Parameters
    ----------
    typ_paths : iterable of str
    root : str, optional — see compile_to_pdf().
    on_error : callable(PdfCompileError), optional
        Called for each failure. Defaults to printing the diagnostic.

    Returns
    -------
    tuple of (written, warnings, failures)
        written  : list of PDF paths produced
        warnings : list of (typ_path, warning_text)
        failures : list of PdfCompileError
    """
    written, warnings, failures = [], [], []

    for typ_path in typ_paths:
        try:
            pdf_path, warns = compile_to_pdf(typ_path, root=root)
        except PdfCompileError as exc:
            failures.append(exc)
            (on_error or _print_error)(exc)
            continue
        written.append(pdf_path)
        warnings.extend((typ_path, w) for w in warns)

    return written, warnings, failures


def _print_error(exc):
    print(f"  [ERROR] {exc}")
    if exc.typ_path != '<typst>':
        print(f"          Sumber dipertahankan untuk ditelusuri: {exc.typ_path}")
