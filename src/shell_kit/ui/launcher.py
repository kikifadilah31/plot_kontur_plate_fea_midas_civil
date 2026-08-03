"""
Peluncur `shell-kit ui`: menyalakan server Streamlit pada halaman app.py.

Streamlit bersifat opsional, jadi ketiadaannya harus berujung petunjuk yang
bisa ditindaklanjuti — bukan traceback.
"""

import os
import subprocess
import sys
from pathlib import Path

# Diteruskan ke app.py supaya folder kerja pasti, tidak bergantung pada
# perilaku Streamlit soal direktori aktif.
CWD_ENV = 'SHELL_KIT_UI_CWD'

INSTALL_HINT = """\
Paket 'streamlit' tidak ditemukan. Antarmuka grafis bersifat opsional.

  Pasang permanen:
    uv tool install "shell-kit[ui] @ git+https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil"

  Atau jalankan sekali tanpa memasang:
    uvx --with streamlit --from git+https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil shell-kit ui

  Dari clone lokal:
    uv sync --extra ui
"""


def streamlit_available():
    """True bila streamlit bisa di-import."""
    try:
        import streamlit  # noqa: F401
    except ImportError:
        return False
    return True


def launch(argv=None):
    """
    Jalankan server Streamlit. Mengembalikan exit code.

    Folder kerja saat ini diteruskan lewat environment agar hasil mendarat di
    tempat pengguna memanggil perintah — sama seperti menjalankan CLI langsung.
    """
    if not streamlit_available():
        print(INSTALL_HINT)
        return 1

    app_path = Path(__file__).parent / 'app.py'
    env = dict(os.environ)
    env[CWD_ENV] = os.getcwd()

    print("=" * 60)
    print("SHELL-KIT — ANTARMUKA GRAFIS")
    print("=" * 60)
    print(f"Folder kerja: {os.getcwd()}")
    print("Hasil akan disimpan di folder itu, sama seperti menjalankan CLI.")
    print("Tutup jendela ini untuk menghentikan server.")
    print()

    result = subprocess.run(
        [sys.executable, '-m', 'streamlit', 'run', str(app_path),
         '--browser.gatherUsageStats=false'],
        env=env,
        cwd=os.getcwd(),
    )
    return result.returncode
