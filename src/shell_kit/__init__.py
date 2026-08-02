"""
shell-kit — post-processing hasil pelat/shell Midas Civil.

Satu perintah dengan dua subcommand:
    shell-kit plot    kontur gaya dalam, momen, dan tegangan
    shell-kit rebar   kebutuhan tulangan lentur & geser (SNI 2847:2019)

Keduanya menerima --report untuk menghasilkan dokumen ringkasan lengkap
dengan diagram tersemat (Markdown, Typst, atau PDF).
"""

__version__ = "3.1.0"
