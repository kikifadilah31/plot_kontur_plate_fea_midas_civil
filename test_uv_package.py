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
Test script untuk verifikasi fitur uv run dari package.
Jalankan dengan: uv run test_uv_package.py
"""

import sys
import os
import subprocess

passed = 0
failed = 0

def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  [OK] {name}")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        failed += 1

print("=" * 60)
print("UV PACKAGE VERIFICATION")
print("=" * 60)

# --- Test 1: pyproject.toml exists ---
print("\n1. Checking project files...")
test("pyproject.toml exists", lambda: (
    None if os.path.exists('pyproject.toml') else (_ for _ in ()).throw(
        FileNotFoundError("pyproject.toml not found"))
))

test(".gitignore exists", lambda: (
    None if os.path.exists('.gitignore') else (_ for _ in ()).throw(
        FileNotFoundError(".gitignore not found"))
))

# --- Test 2: pyproject.toml content ---
print("\n2. Validating pyproject.toml...")
with open('pyproject.toml', 'r') as f:
    toml_content = f.read()

test("has [project] section", lambda: (
    None if '[project]' in toml_content else (_ for _ in ()).throw(
        ValueError("Missing [project]"))
))

test("has name = 'fea-contour-plotter'", lambda: (
    None if 'fea-contour-plotter' in toml_content else (_ for _ in ()).throw(
        ValueError("Missing project name"))
))

test("has fea-plot entry point", lambda: (
    None if 'fea-plot' in toml_content else (_ for _ in ()).throw(
        ValueError("Missing fea-plot entry point"))
))

test("has fea-report entry point", lambda: (
    None if 'fea-report' in toml_content else (_ for _ in ()).throw(
        ValueError("Missing fea-report entry point"))
))

test("has [build-system]", lambda: (
    None if '[build-system]' in toml_content else (_ for _ in ()).throw(
        ValueError("Missing [build-system]"))
))

test("has hatchling backend", lambda: (
    None if 'hatchling' in toml_content else (_ for _ in ()).throw(
        ValueError("Missing hatchling"))
))

test("has src/fea_contour packages directive", lambda: (
    None if 'src/fea_contour' in toml_content else (_ for _ in ()).throw(
        ValueError("Missing packages directive"))
))

# --- Test 3: Package structure ---
print("\n3. Checking package structure...")
required_files = [
    'src/fea_contour/__init__.py',
    'src/fea_contour/config.py',
    'src/fea_contour/math_utils.py',
    'src/fea_contour/combination.py',
    'src/fea_contour/io_utils.py',
    'src/fea_contour/mesh.py',
    'src/fea_contour/values.py',
    'src/fea_contour/plotting.py',
    'src/fea_contour/reporting.py',
    'src/fea_contour/cli_plot.py',
    'src/fea_contour/cli_report.py',
]
for f in required_files:
    test(f"exists: {f}", lambda f=f: (
        None if os.path.exists(f) else (_ for _ in ()).throw(
            FileNotFoundError(f"{f} not found"))
    ))

# --- Test 4: Entry point functions ---
print("\n4. Checking entry_point() functions...")
sys.path.insert(0, 'src')

def test_entry_point_plot():
    from fea_contour.cli_plot import entry_point, main
    assert callable(entry_point), "entry_point is not callable"
    assert callable(main), "main is not callable"

def test_entry_point_report():
    from fea_contour.cli_report import entry_point, main
    assert callable(entry_point), "entry_point is not callable"
    assert callable(main), "main is not callable"

test("cli_plot has entry_point()", test_entry_point_plot)
test("cli_report has entry_point()", test_entry_point_report)

# --- Test 5: fea-plot --help via uv run ---
print("\n5. Testing 'uv run fea-plot --help'...")
try:
    result = subprocess.run(
        ['uv', 'run', 'fea-plot', '--help'],
        capture_output=True, text=True, timeout=60,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    if result.returncode == 0:
        test("fea-plot --help works", lambda: None)
        # Check help output contains expected content
        test("help shows --method", lambda: (
            None if '--method' in result.stdout else (_ for _ in ()).throw(
                ValueError("--method not in help output"))
        ))
        test("help shows --thickness", lambda: (
            None if '--thickness' in result.stdout else (_ for _ in ()).throw(
                ValueError("--thickness not in help output"))
        ))
        test("help shows --no-mesh", lambda: (
            None if '--no-mesh' in result.stdout else (_ for _ in ()).throw(
                ValueError("--no-mesh not in help output"))
        ))
    else:
        test("fea-plot --help works", lambda: (_ for _ in ()).throw(
            RuntimeError(f"Exit code {result.returncode}: {result.stderr[:200]}")))
except FileNotFoundError:
    test("fea-plot --help works", lambda: (_ for _ in ()).throw(
        RuntimeError("uv not found — install uv first")))

# --- Test 6: fea-report --help via uv run ---
print("\n6. Testing 'uv run fea-report --help'...")
try:
    result = subprocess.run(
        ['uv', 'run', 'fea-report', '--help'],
        capture_output=True, text=True, timeout=60,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    if result.returncode == 0:
        test("fea-report --help works", lambda: None)
        test("help shows --comb", lambda: (
            None if '--comb' in result.stdout else (_ for _ in ()).throw(
                ValueError("--comb not in help output"))
        ))
        test("help shows --master", lambda: (
            None if '--master' in result.stdout else (_ for _ in ()).throw(
                ValueError("--master not in help output"))
        ))
        test("help shows --thickness", lambda: (
            None if '--thickness' in result.stdout else (_ for _ in ()).throw(
                ValueError("--thickness not in help output"))
        ))
    else:
        test("fea-report --help works", lambda: (_ for _ in ()).throw(
            RuntimeError(f"Exit code {result.returncode}: {result.stderr[:200]}")))
except FileNotFoundError:
    test("fea-report --help works", lambda: (_ for _ in ()).throw(
        RuntimeError("uv not found")))

# --- Summary ---
print("\n" + "=" * 60)
total = passed + failed
if failed == 0:
    print(f"ALL {total} TESTS PASSED!")
    print()
    print("Langkah selanjutnya:")
    print("  1. Upload ke GitHub:")
    print("     git init && git add -A && git commit -m 'v1.0.0'")
    print("     git remote add origin https://github.com/USERNAME/PY_PLOT_KONTUR_PLATE_MIDAS.git")
    print("     git push -u origin main")
    print()
    print("  2. Test dari GitHub:")
    print("     uvx --from git+https://github.com/USERNAME/PY_PLOT_KONTUR_PLATE_MIDAS fea-plot --help")
    print()
    print("  3. Install permanen:")
    print("     uv tool install git+https://github.com/USERNAME/PY_PLOT_KONTUR_PLATE_MIDAS")
else:
    print(f"RESULTS: {passed}/{total} passed, {failed} FAILED")
print("=" * 60)
