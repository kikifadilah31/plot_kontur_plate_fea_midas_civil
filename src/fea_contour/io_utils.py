"""
I/O utilities — CSV loading, auto-detection, and coordinate parsing.
"""

import os
import sys
import glob
import pandas as pd
from .config import INPUT_FOLDER, FILE_PATTERNS


def auto_detect_files(input_folder=None):
    """
    Auto-detect input CSV files based on filename patterns.

    Returns
    -------
    dict with keys 'kordinat', 'connectivity', 'gaya' → file paths or None
    """
    folder = input_folder or INPUT_FOLDER
    detected = {}
    for file_type, pattern in FILE_PATTERNS.items():
        found = sorted(glob.glob(os.path.join(folder, pattern)), key=len)
        detected[file_type] = found[0] if found else None
    return detected


def load_csv_inputs(k_file, c_file, g_file):
    """
    Load and validate the three input CSV files.

    Parameters
    ----------
    k_file : str — path to coordinate CSV
    c_file : str — path to connectivity CSV
    g_file : str — path to force/moment CSV

    Returns
    -------
    tuple of (df_kordinat, df_conn, df_gaya)

    Raises
    ------
    SystemExit if any file is missing.
    """
    if not all([k_file, c_file, g_file]):
        print("ERROR: Missing input files.")
        print(f"  Kordinat:     {k_file or '(not found)'}")
        print(f"  Connectivity: {c_file or '(not found)'}")
        print(f"  Gaya:         {g_file or '(not found)'}")
        sys.exit(1)

    df_kordinat = pd.read_csv(k_file, low_memory=False)
    df_conn = pd.read_csv(c_file, low_memory=False)
    df_gaya = pd.read_csv(g_file, low_memory=False)

    # Strip whitespace from all column headers
    for df in [df_kordinat, df_conn, df_gaya]:
        df.columns = df.columns.str.strip()

    return df_kordinat, df_conn, df_gaya


def build_coord_dict(df_kordinat):
    """Convert coordinate DataFrame to {node_id: {'X': x, 'Y': y}} dict."""
    return df_kordinat.set_index('ID')[['X', 'Y']].to_dict('index')


def resolve_input_files(args_kordinat, args_connectivity, args_gaya, input_folder=None):
    """
    Resolve input file paths: use CLI args if provided, else auto-detect.

    Parameters
    ----------
    args_kordinat : str or None
    args_connectivity : str or None
    args_gaya : str or None
    input_folder : str or None

    Returns
    -------
    tuple of (k_file, c_file, g_file)
    """
    k_file = args_kordinat
    c_file = args_connectivity
    g_file = args_gaya

    if not all([k_file, c_file, g_file]):
        detected = auto_detect_files(input_folder)
        if not k_file:
            k_file = detected.get('kordinat')
        if not c_file:
            c_file = detected.get('connectivity')
        if not g_file:
            g_file = detected.get('gaya')

    return k_file, c_file, g_file
