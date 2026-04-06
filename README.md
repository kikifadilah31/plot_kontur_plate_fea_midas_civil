# FEA 2D Contour Plot Generator
**Version 1.0.0 | Professional FEA Visualization & Reporting**

High-performance Python tool for generating FEA contour plots and comprehensive technical reports from Midas Civil (or similar) plate/shell results.

---

## 🚀 Quick Start

### Cara 1: Jalankan langsung dari GitHub (tanpa clone)

Hanya butuh [uv](https://docs.astral.sh/uv/) terinstall di komputer.

```bash
# Install permanen ke PATH
uv tool install git+https://github.com/USERNAME/PY_PLOT_KONTUR_PLATE_MIDAS

# Lalu jalankan dari folder yang berisi input/
fea-plot --method average-nodal --no-mesh
fea-report --comb --master
```

Atau jalankan sekali tanpa install:
```bash
# Plot
uvx --from git+https://github.com/USERNAME/PY_PLOT_KONTUR_PLATE_MIDAS fea-plot \
  --method all --no-mesh --comb input/kombinasi_beban.csv

# Report
uvx --from git+https://github.com/USERNAME/PY_PLOT_KONTUR_PLATE_MIDAS fea-report \
  --comb --master --thickness 0.5
```

### Cara 2: Clone dan jalankan lokal

```bash
git clone https://github.com/USERNAME/PY_PLOT_KONTUR_PLATE_MIDAS.git
cd PY_PLOT_KONTUR_PLATE_MIDAS

# Jalankan via uv (otomatis install dependencies)
uv run fea-plot --method average-nodal --no-mesh
uv run fea-report --comb --master

# Atau cara tradisional
uv run python plot_contur_fea.py --method all --no-mesh
uv run python generate_reports.py --comb --master
```

> **Note:** Ganti `USERNAME` dengan username GitHub Anda.

---

## 📋 Table of Contents
1. [Input Data Structure](#-input-data-structure)
2. [Commands Reference](#-commands-reference)
3. [Contour Methods](#-contour-methods)
4. [Output Structure](#-output-structure)
5. [Mathematical Context](#-mathematical-context)
6. [Architecture](#-architecture)
7. [Reporting & Master Summary](#-reporting--master-summary)
8. [Troubleshooting](#-troubleshooting)

---

## 📂 Input Data Structure

Siapkan file CSV di folder `input/` pada working directory:

| File | Deskripsi | Kolom Utama |
|------|-----------|-------------|
| `kordinat_node.csv` | Koordinat node | ID, X, Y, Z |
| `connectivity_data.csv` | Konektivitas elemen | iEL, 1, 2, 3, 4 |
| `gaya_elemen_per_load_case.csv` | Gaya/momen per elemen | Elem, Load, Node, Forces... |
| `kombinasi_beban.csv` | Definisi kombinasi beban | Name, Active, Case 1, Factor 1, ... |

---

## 🛠️ Commands Reference

### `fea-plot` — Generate Contour Plots

```bash
fea-plot [OPTIONS]
```

| Argument | Deskripsi | Default |
|----------|-----------|---------|
| `--method` | `average-nodal`, `element-nodal`, `element-center`, `all` | `average-nodal` |
| `--comb` | Path ke file CSV kombinasi beban | *(none)* |
| `--no-mesh` | Sembunyikan wireframe mesh | `False` |
| `--thickness` | Tebal pelat dalam meter | `0.400` |
| `--kordinat` | Path ke CSV koordinat | *(auto-detect)* |
| `--connectivity` | Path ke CSV konektivitas | *(auto-detect)* |
| `--gaya` | Path ke CSV gaya/momen | *(auto-detect)* |
| `--output` | Folder output | `output` |

**Contoh:**
```bash
# Semua metode + kombinasi + tanpa mesh
fea-plot --method all --comb input/kombinasi_beban.csv --no-mesh

# Satu metode dengan tebal custom
fea-plot --method element-nodal --thickness 0.5

# Input file manual
fea-plot --kordinat data/nodes.csv --connectivity data/conn.csv --gaya data/forces.csv
```

### `fea-report` — Generate Reports

```bash
fea-report [OPTIONS]
```

| Argument | Deskripsi | Default |
|----------|-----------|---------|
| `--comb` | Sertakan kombinasi beban | `False` |
| `--master` | Generate Master Summary | `False` |
| `--thickness` | Tebal pelat dalam meter | `0.400` |
| `--gaya` | Path ke CSV gaya/momen | `input/gaya_elemen_per_load_case.csv` |
| `--kombinasi` | Path ke CSV kombinasi | `input/kombinasi_beban.csv` |
| `--output` | Folder output | `output` |

**Contoh:**
```bash
# Full report dengan kombinasi + master summary
fea-report --comb --master

# Custom thickness
fea-report --comb --master --thickness 0.5
```

---

## 🎨 Contour Methods

| Method | Deskripsi | Tampilan | Use Case |
|--------|-----------|----------|----------|
| `average-nodal` | Rata-rata nodal di shared nodes | Smooth gradient | Presentasi, publikasi |
| `element-nodal` | Nilai mentah per elemen | Diskontinyu, stepped | Analisis detail |
| `element-center` | Nilai centroid per elemen | Blocky, seragam | Overview cepat |

---

## 📁 Output Structure

Setiap eksekusi membuat folder ber-timestamp:

```
output/
└── 20260406_143000/
    ├── Method_average-nodal/          # Jika --method all
    │   ├── Load_MS/
    │   │   ├── contour_Fxx_kN_per_m_.png
    │   │   ├── contour_Sig-xx_Top_kPa_Top_Fiber.png
    │   │   └── ...
    │   ├── Combination_K_1_1/
    │   └── ...
    ├── Method_element-nodal/
    ├── Method_element-center/
    └── MASTER_SUMMARY.md              # Jika fea-report --master
```

---

## 🧮 Mathematical Context

### Rumus Tegangan
$$\sigma = \frac{N}{A} - \frac{M \cdot y}{I}$$

| Parameter | Rumus |
|-----------|-------|
| Area (A) | `t × 1.0 m²` |
| Inertia (I) | `(1.0 × t³) / 12 m⁴` |
| y_top | `+t/2` |
| y_bottom | `−t/2` |

### Sign Convention (Midas Civil)

| Parameter | Tanda | Arti |
|-----------|-------|------|
| Axial Force (N) | (+) | Tarik |
| | (−) | Tekan |
| Moment (M) | (+) | Serat Atas Tekan (−), Serat Bawah Tarik (+) |
| | (−) | Serat Atas Tarik (+), Serat Bawah Tekan (−) |

---

## 🏗️ Architecture

### Package Structure

```
src/fea_contour/
├── config.py          # Semua konstanta terpusat
├── math_utils.py      # Perhitungan tegangan + helpers
├── combination.py     # Parsing & validasi kombinasi beban
├── io_utils.py        # CSV loading & auto-detect
├── mesh.py            # MeshTopology class
├── values.py          # ValueMapper class (Z-Array caching)
├── plotting.py        # Plot worker + figure recycling
├── reporting.py       # Report & master summary generation
├── cli_plot.py        # CLI: fea-plot
└── cli_report.py      # CLI: fea-report
```

### Key Optimizations
- **Z-Array Pre-Caching**: Perhitungan berat dijalankan SEKALI per load case, bukan per plot
- **Figure Recycling**: Satu Matplotlib figure per CPU core, di-recycle untuk semua plot
- **MeshTopology Singleton**: Mesh dibangun sekali per metode, digunakan ulang untuk semua load case

---

## 📊 Reporting & Master Summary

### Per-Load Case Report
Markdown report berisi:
- Section properties (A, I)
- Force summary (max/min/mean per kolom)
- Stress summary dengan contributing forces
- Critical elements analysis

### Enriched Master Summary
Aggregasi global dari semua load case dan kombinasi:
- **Global Stress Envelope**: Top 20 nilai tegangan tertinggi
- **Force & Moment Envelopes**: Ranking per parameter
- **Critical Element Identification**: Elemen yang paling sering muncul di extremes

---

## 🔍 Troubleshooting

| Masalah | Solusi |
|---------|--------|
| `ERROR: Missing input files` | Pastikan file CSV ada di folder `input/` |
| Plot lambat di `[1/3]` | Normal untuk `element-nodal` — Z-Array caching berjalan |
| Kombinasi tidak ditemukan | Periksa nama load case di CSV cocok dengan output FEA |
| `ModuleNotFoundError` | Jalankan via `uv run` atau install package dulu |

---

## 📚 References

1. **Zienkiewicz, O.C. & Taylor, R.L.** (2000). *The Finite Element Method*. Butterworth-Heinemann.
2. **MIDAS Civil User Manual** (2023). *Post-Processing: Plate/Shell Element Results*.

---

**License:** MIT  
**Version:** 1.0.0