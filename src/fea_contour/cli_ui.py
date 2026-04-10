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

    print("=" * 50)
    print("  FEA Contour Plotter - Web UI")
    print("=" * 50)
    print("  Launching Streamlit...")
    print("  Close this window to stop the server.")
    print()

    subprocess.run([
        sys.executable, '-m', 'streamlit', 'run', app_path,
        '--server.headless=false',
        '--browser.gatherUsageStats=false',
        '--theme.base=light',
    ])


def entry_point():
    """Console script entry point (called by pyproject.toml [project.scripts])."""
    sys.exit(main() or 0)
