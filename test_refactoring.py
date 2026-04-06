# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pandas>=2.0",
#   "numpy>=1.24",
#   "matplotlib>=3.7",
#   "tqdm>=4.65",
# ]
# ///
"""
Test script untuk verifikasi refactoring package fea_contour.
Jalankan dengan: uv run test_refactoring.py
"""

import sys
import os
import traceback

# Add src/ to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

passed = 0
failed = 0
errors = []

def test(name, fn):
    global passed, failed, errors
    try:
        fn()
        print(f"  [OK] {name}")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        errors.append((name, traceback.format_exc()))
        failed += 1

print("=" * 60)
print("FEA CONTOUR PLOTTER — REFACTORING VERIFICATION")
print("=" * 60)

# --- Test 1: Package imports ---
print("\n1. Testing package imports...")

test("import fea_contour", lambda: __import__('fea_contour'))

test("import config", lambda: (
    exec("from fea_contour.config import PLOTTABLE_COLUMNS, STRESS_PAIRS, DEFAULT_THICKNESS")
))

test("import math_utils", lambda: (
    exec("from fea_contour.math_utils import calculate_stress_vectorized, safe_filename, format_value")
))

test("import combination", lambda: (
    exec("from fea_contour.combination import parse_combination_file, validate_combinations")
))

test("import io_utils", lambda: (
    exec("from fea_contour.io_utils import auto_detect_files, load_csv_inputs, build_coord_dict")
))

test("import mesh", lambda: (
    exec("from fea_contour.mesh import MeshTopology")
))

test("import values", lambda: (
    exec("from fea_contour.values import ValueMapper")
))

test("import plotting", lambda: (
    exec("from fea_contour.plotting import init_worker, generate_plot_worker")
))

test("import reporting", lambda: (
    exec("from fea_contour.reporting import generate_report, generate_master_summary, process_load_case")
))

test("import cli_plot", lambda: (
    exec("from fea_contour.cli_plot import main")
))

test("import cli_report", lambda: (
    exec("from fea_contour.cli_report import main")
))

# --- Test 2: Version check ---
print("\n2. Testing version...")
from fea_contour import __version__
test(f"version = {__version__}", lambda: None)

# --- Test 3: Config validation ---
print("\n3. Testing config values...")
from fea_contour.config import (
    PLOTTABLE_COLUMNS, STRESS_PAIRS, FORCE_COLUMNS, STRESS_COLUMNS,
    DEFAULT_THICKNESS, STRIP_WIDTH, ALL_METHODS, CONTOUR_LEVELS,
)

test(f"PLOTTABLE_COLUMNS has {len(PLOTTABLE_COLUMNS)} items", lambda: (
    None if len(PLOTTABLE_COLUMNS) == 16 else (_ for _ in ()).throw(
        AssertionError(f"Expected 16, got {len(PLOTTABLE_COLUMNS)}"))
))

test(f"STRESS_PAIRS has {len(STRESS_PAIRS)} entries", lambda: (
    None if len(STRESS_PAIRS) == 4 else (_ for _ in ()).throw(
        AssertionError(f"Expected 4, got {len(STRESS_PAIRS)}"))
))

test(f"DEFAULT_THICKNESS = {DEFAULT_THICKNESS}", lambda: (
    None if DEFAULT_THICKNESS == 0.4 else (_ for _ in ()).throw(
        AssertionError(f"Expected 0.4"))
))

test(f"STRIP_WIDTH = {STRIP_WIDTH}", lambda: (
    None if STRIP_WIDTH == 1.0 else (_ for _ in ()).throw(
        AssertionError(f"Expected 1.0"))
))

test(f"ALL_METHODS = {ALL_METHODS}", lambda: (
    None if len(ALL_METHODS) == 3 else (_ for _ in ()).throw(
        AssertionError(f"Expected 3 methods"))
))

test(f"CONTOUR_LEVELS = {CONTOUR_LEVELS}", lambda: (
    None if CONTOUR_LEVELS == 24 else (_ for _ in ()).throw(
        AssertionError(f"Expected 24"))
))

# --- Test 4: Math functions ---
print("\n4. Testing math functions...")
import numpy as np
from fea_contour.math_utils import calculate_stress_vectorized, safe_filename, format_value

def test_stress_calc():
    axial = np.array([100.0])   # 100 kN/m tension
    moment = np.array([50.0])   # 50 kN·m/m
    thickness = 0.4
    top, bot = calculate_stress_vectorized(axial, moment, thickness)
    # σ = N/A - M*y/I
    # A = 0.4*1 = 0.4, I = 1*0.4³/12 = 0.005333
    # N/A = 100/0.4 = 250
    # M*y_top/I = 50*0.2/0.005333 = 1875
    # top = 250 - 1875 = -1625
    # M*y_bot/I = 50*(-0.2)/0.005333 = -1875
    # bot = 250 - (-1875) = 2125
    assert abs(top[0] - (-1625.0)) < 0.1, f"Top stress: expected -1625, got {top[0]}"
    assert abs(bot[0] - 2125.0) < 0.1, f"Bot stress: expected 2125, got {bot[0]}"

test("stress calculation (N=100, M=50, t=0.4)", test_stress_calc)

test("safe_filename('Fxx (kN/m)')", lambda: (
    None if safe_filename('Fxx (kN/m)') == 'Fxx_kN_per_m' else (_ for _ in ()).throw(
        AssertionError(f"Got: {safe_filename('Fxx (kN/m)')}"))
))

test("format_value(123.456)", lambda: (
    None if format_value(123.456) == '+123.46' else (_ for _ in ()).throw(
        AssertionError(f"Got: {format_value(123.456)}"))
))

test("format_value(NaN)", lambda: (
    None if format_value(float('nan')) == 'N/A' else (_ for _ in ()).throw(
        AssertionError(f"Got: {format_value(float('nan'))}"))
))

# --- Test 5: Combination parsing ---
print("\n5. Testing combination parsing...")
from fea_contour.combination import parse_combination_file, validate_combinations

def test_parse_combo():
    combo_file = os.path.join('input', 'kombinasi_beban.csv')
    if os.path.exists(combo_file):
        combos = parse_combination_file(combo_file)
        assert len(combos) > 0, "No combinations parsed"
        assert 'name' in combos[0], "Missing 'name' key"
        assert 'lc_factors' in combos[0], "Missing 'lc_factors' key"
        print(f"    → Parsed {len(combos)} combinations")
    else:
        print(f"    → Skipped (file not found: {combo_file})")

test("parse kombinasi_beban.csv", test_parse_combo)

# --- Test 6: Auto-detect files ---
print("\n6. Testing file auto-detection...")
from fea_contour.io_utils import auto_detect_files

def test_auto_detect():
    detected = auto_detect_files()
    for key, path in detected.items():
        status = "FOUND" if path else "NOT FOUND"
        print(f"    → {key}: {path or '(none)'} [{status}]")
    assert detected.get('kordinat') is not None, "kordinat file not detected"
    assert detected.get('connectivity') is not None, "connectivity file not detected"
    assert detected.get('gaya') is not None, "gaya file not detected"

test("auto-detect input files", test_auto_detect)

# --- Test 7: No duplicate functions ---
print("\n7. Checking code deduplication...")

def test_no_duplication():
    # Check that root files are thin wrappers (< 30 lines)
    with open('plot_contur_fea.py', 'r') as f:
        lines = len(f.readlines())
    assert lines < 30, f"plot_contur_fea.py should be thin wrapper, but has {lines} lines"
    
    with open('generate_reports.py', 'r') as f:
        lines = len(f.readlines())
    assert lines < 30, f"generate_reports.py should be thin wrapper, but has {lines} lines"

test("root files are thin wrappers", test_no_duplication)

# --- Summary ---
print("\n" + "=" * 60)
total = passed + failed
if failed == 0:
    print(f"ALL {total} TESTS PASSED!")
else:
    print(f"RESULTS: {passed}/{total} passed, {failed} FAILED")
    print("\nFailed tests:")
    for name, tb in errors:
        print(f"\n--- {name} ---")
        print(tb)
print("=" * 60)
