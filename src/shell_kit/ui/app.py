"""
Halaman Streamlit shell-kit: formulir opsi, lalu jalankan CLI.

Halaman ini TIDAK menghitung apa pun sendiri. Ia menyusun daftar argumen,
memanggil `python -m shell_kit.cli`, dan menampilkan keluarannya. Seluruh
perhitungan, pemeriksaan code, dan penulisan berkas terjadi di jalur kode yang
sama persis dengan CLI — sehingga UI tidak mungkin melenceng dari CLI.
"""

import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import streamlit as st

from shell_kit import __version__
from shell_kit.config import ALL_METHODS, DEFAULT_THICKNESS, OUTPUT_FOLDER
from shell_kit.io_utils import auto_detect_files
from shell_kit.rebar import (
    DEFAULT_FC, DEFAULT_FY, DEFAULT_COVER,
    SHEAR_DIAMETERS, get_available_config_codes,
)
from shell_kit.ui.args import build_argv, format_command
from shell_kit.ui.launcher import CWD_ENV

# Folder tempat `shell-kit ui` dipanggil. Hasil mendarat di sini, sama seperti
# menjalankan CLI langsung.
WORKDIR = Path(os.environ.get(CWD_ENV) or os.getcwd())

# Bilah progres tqdm menulis ke stderr dengan carriage return; tidak berguna
# ditampilkan sebagai teks.
PROGRESS_NOISE = re.compile(r'\r|\d+%\|| it/s\]|it/s\]')

MAX_LOG_LINES = 300

st.set_page_config(
    page_title='shell-kit',
    page_icon=':material/grid_on:',
    layout='centered',
)

st.session_state.setdefault('last_argv', None)
st.session_state.setdefault('last_returncode', None)
st.session_state.setdefault('last_stderr', '')

st.title('shell-kit')
st.caption(f'Versi {__version__} — post-processing pelat/shell Midas Civil')

with st.container(border=True):
    st.markdown(f'**Folder kerja:** `{WORKDIR}`')
    st.caption(
        'Hasil disimpan di folder ini, persis seperti menjalankan CLI. '
        'Formulir ini hanya menyusun perintah lalu menjalankannya — '
        'perhitungannya memakai jalur kode yang sama.'
    )

# Di luar form: mengubahnya harus langsung mengganti isi formulir.
command = st.segmented_control(
    'Perintah',
    ['rebar', 'plot'],
    default='rebar',
    format_func=lambda c: ('Tulangan (rebar)' if c == 'rebar'
                           else 'Kontur gaya (plot)'),
    key='command',
)
if not command:
    st.stop()

detected = auto_detect_files(str(WORKDIR / 'input'))

with st.form('opsi', border=False):
    values = {}

    # ------------------------------------------------------------------
    with st.expander('Berkas input', expanded=not all(detected.values())):
        found = [f'`{k}` → `{Path(v).name}`'
                 for k, v in detected.items() if v]
        missing = [k for k, v in detected.items() if not v]

        if found:
            st.success('Terdeteksi otomatis di folder `input/`:\n\n'
                       + '\n\n'.join(f'- {f}' for f in found),
                       icon=':material/check_circle:')
        if missing:
            st.warning(
                'Belum ketemu di `input/`: ' + ', '.join(f'`{m}`' for m in missing)
                + '. Isi path-nya di bawah.',
                icon=':material/warning:')

        values['kordinat'] = st.text_input(
            'Path CSV koordinat', value='',
            placeholder=detected.get('kordinat') or 'input/kordinat_node.csv',
            help='Kosongkan untuk memakai hasil deteksi otomatis.')
        values['connectivity'] = st.text_input(
            'Path CSV konektivitas', value='',
            placeholder=detected.get('connectivity') or 'input/connectivity_data.csv',
            help='Kosongkan untuk memakai hasil deteksi otomatis.')
        values['gaya'] = st.text_input(
            'Path CSV gaya/momen', value='',
            placeholder=detected.get('gaya') or 'input/gaya_elemen_per_load_case.csv',
            help='Kosongkan untuk memakai hasil deteksi otomatis.')

    # ------------------------------------------------------------------
    with st.container(border=True):
        st.markdown('**Geometri & metode**')
        values['thickness'] = st.number_input(
            'Tebal pelat (m)', min_value=0.01, max_value=10.0,
            value=float(DEFAULT_THICKNESS), step=0.05, format='%.3f')
        values['method'] = st.selectbox(
            'Metode kontur', ALL_METHODS + ['all'],
            index=ALL_METHODS.index('average-nodal'))
        values['comb'] = st.text_input(
            'Path CSV kombinasi beban', value='',
            placeholder='input/kombinasi_beban.csv',
            help='Kosongkan untuk menghitung tiap load case tunggal.')
        comb_select = st.text_input(
            'Filter kombinasi', value='',
            placeholder='K_1*  (kosong = semua)',
            help='Pola wildcard, pisahkan dengan spasi bila lebih dari satu.')
        values['comb_select'] = comb_select.split() if comb_select.strip() else None

    # ------------------------------------------------------------------
    if command == 'rebar':
        with st.container(border=True):
            st.markdown('**Material & tulangan**')
            values['fc'] = st.number_input(
                "f'c — kuat tekan beton (MPa)", min_value=10.0, max_value=100.0,
                value=float(DEFAULT_FC), step=1.0)
            values['fy'] = st.number_input(
                'fy — kuat leleh baja (MPa)', min_value=200.0, max_value=700.0,
                value=float(DEFAULT_FY), step=10.0)
            values['cover'] = st.number_input(
                'Selimut beton bersih (mm)', min_value=10.0, max_value=150.0,
                value=float(DEFAULT_COVER), step=5.0)

            mode = st.segmented_control(
                'Mode perhitungan',
                ['spasi', 'tulangan'],
                default='tulangan',
                format_func=lambda m: ('Spasi diketahui → cari tulangan'
                                       if m == 'tulangan'
                                       else 'Tulangan diketahui → cari spasi'),
                key='mode')

            if mode == 'spasi':
                values['diameter'] = st.selectbox(
                    'Tulangan terpasang', get_available_config_codes(),
                    index=get_available_config_codes().index('16'))
            else:
                values['spacing'] = st.number_input(
                    'Spasi terpasang (mm)', min_value=25.0, max_value=500.0,
                    value=150.0, step=25.0)
                values['rebar_select'] = st.multiselect(
                    'Batasi pilihan konfigurasi',
                    get_available_config_codes(),
                    default=[],
                    help='Kosongkan untuk memakai daftar bawaan D13–D32.')

        with st.container(border=True):
            st.markdown('**Tulangan minimum (SNI 24.4.3.2)**')
            hitung_as_min = st.checkbox(
                'Hitung tulangan minimum', value=True,
                help='Bila dilepas, perhitungan As minimum dimatikan '
                     'sepenuhnya — setara perilaku tool versi awal.')
            values['no_as_min'] = not hitung_as_min

            if hitung_as_min:
                pakai_zona = st.checkbox(
                    'Batasi zona permukaan untuk penampang tebal',
                    value=False,
                    help='Untuk rakit/pilecap. Meminjam ACI 350-06 §7.12.2.1 — '
                         'di luar huruf SNI 2847, dan dicatat di laporan.')
                if pakai_zona:
                    values['as_min_surface_zone'] = st.number_input(
                        'Tebal zona permukaan per muka (mm)',
                        min_value=50.0, max_value=1000.0, value=300.0, step=50.0)
            else:
                st.info('As minimum dimatikan — hasilnya setara tool versi awal.',
                        icon=':material/info:')

        with st.container(border=True):
            st.markdown('**Geser**')
            values['shear'] = st.checkbox('Hitung tulangan geser', value=False)
            values['shear_spacing_long'] = st.number_input(
                'Spasi sengkang memanjang (mm)', min_value=25.0, max_value=500.0,
                value=150.0, step=25.0)
            values['shear_spacing_trans'] = st.number_input(
                'Spasi sengkang melintang (mm)', min_value=25.0, max_value=500.0,
                value=150.0, step=25.0)
            values['shear_select'] = st.multiselect(
                'Batasi diameter sengkang',
                [int(d) for d in SHEAR_DIAMETERS], default=[],
                help='Kosongkan untuk memakai daftar bawaan D10–D25.')

    # ------------------------------------------------------------------
    with st.container(border=True):
        st.markdown('**Laporan & tampilan**')
        values['report'] = st.checkbox(
            'Hasilkan laporan', value=True,
            help='Dokumen ringkasan dengan seluruh diagram tersemat.')
        values['report_format'] = st.selectbox(
            'Format laporan', ['md', 'typst', 'pdf'], index=0,
            help='pdf dikompilasi dari typst di dalam Python; '
                 'berkas .typ tetap disimpan.')
        values['theme'] = st.selectbox('Tema plot', ['light', 'dark'], index=0)
        values['no_mesh'] = not st.checkbox('Tampilkan wireframe mesh', value=False)
        values['no_annotation'] = not st.checkbox(
            'Tampilkan marker MAX dan badge SECTION INADEQUATE', value=True)
        values['output'] = st.text_input('Folder output', value=OUTPUT_FOLDER)

    submitted = st.form_submit_button(
        'Jalankan', type='primary', icon=':material/play_arrow:')


# ----------------------------------------------------------------------
# Menjalankan
# ----------------------------------------------------------------------
if submitted:
    argv = build_argv(command, values)
    st.session_state['last_argv'] = argv

    st.markdown('**Perintah setara**')
    st.caption('Bisa disalin dan dijalankan langsung di terminal.')
    st.code(format_command(argv), language='bash')

    err_lines = []

    def _drain_stderr(stream):
        # Dikuras di thread terpisah: tqdm membanjiri stderr, dan pipe yang
        # penuh akan membuat proses menggantung bila hanya stdout yang dibaca.
        for line in stream:
            err_lines.append(line)

    with st.status('Menjalankan…', expanded=True) as status:
        log_slot = st.empty()
        lines = []

        proc = subprocess.Popen(
            [sys.executable, '-m', 'shell_kit.cli', *argv],
            cwd=str(WORKDIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            encoding='utf-8',
            errors='replace',
        )

        drainer = threading.Thread(
            target=_drain_stderr, args=(proc.stderr,), daemon=True)
        drainer.start()

        for line in proc.stdout:
            lines.append(line.rstrip())
            log_slot.code('\n'.join(lines[-MAX_LOG_LINES:]))

        proc.wait()
        drainer.join(timeout=5)

        st.session_state['last_returncode'] = proc.returncode
        stderr_text = ''.join(
            l for l in err_lines if not PROGRESS_NOISE.search(l))
        st.session_state['last_stderr'] = stderr_text

        if proc.returncode == 0:
            status.update(label='Selesai', state='complete', expanded=False)
        else:
            status.update(label=f'Gagal (exit {proc.returncode})',
                          state='error', expanded=True)

    if proc.returncode == 0:
        st.success(
            f'Selesai. Hasil ada di `{(WORKDIR / values["output"]).resolve()}`',
            icon=':material/check_circle:')
    else:
        st.error(
            f'Gagal dengan exit code {proc.returncode}. '
            'Periksa log di atas.',
            icon=':material/error:')
        if stderr_text.strip():
            with st.expander('Pesan kesalahan', expanded=True):
                st.code(stderr_text)
