"""
CLI entry point for FEA Streamlit UI.
Launches the Streamlit server and opens the browser.
"""

import subprocess
import sys
from pathlib import Path


def main():
    """Launch Streamlit UI server."""
    app_path = str(Path(__file__).parent / 'ui.py')

    import time
    print("=" * 60)
    print("  ⚠️ DEPRECATION WARNING ⚠️")
    print("  Fitur FEA Contour Plotter Web UI (fea-ui) berstatus DEPRECATED.")
    print("  Karena ketidakstabilan framework Streamlit, fitur ini")
    print("  tidak lagi direkomendasikan untuk analisis skala besar.")
    print("  ")
    print("  Silakan gunakan alternatif Command Line Interface (CLI):")
    print("  👉 uv run fea-rebar")
    print("  👉 uv run fea-plot")
    print("  👉 uv run fea-report")
    print("=" * 60)
    print("  Launching legacy Streamlit UI in 3 seconds...")
    print("  Close this window to stop the server.")
    print()
    time.sleep(3)

    subprocess.run([
        sys.executable, '-m', 'streamlit', 'run', app_path,
        '--server.headless=false',
        '--browser.gatherUsageStats=false',
        '--theme.base=light',
    ])


def entry_point():
    """Console script entry point (called by pyproject.toml [project.scripts])."""
    sys.exit(main() or 0)
