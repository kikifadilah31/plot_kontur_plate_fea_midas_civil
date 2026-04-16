# FEA 2D Contour Plot Generator
**Version 1.6.0 | Professional FEA Visualization & Reporting**

High-performance Python tool for generating FEA contour plots and comprehensive technical reports from Midas Civil (or similar) plate/shell results.

---

## 🚀 Quick Start

### Cara 1: Jalankan langsung dari GitHub (tanpa clone)

Hanya butuh [uv](https://docs.astral.sh/uv/) terinstall di komputer.

```bash
# Install permanen ke PATH
uv tool install git+https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil

# Lalu jalankan dari folder yang berisi input/
fea-plot --method average-nodal --no-mesh
fea-report --master --comb input/kombinasi_beban.csv
```

Atau jalankan sekali tanpa install:
```bash
# Plot
uvx --from git+https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil fea-plot \
  --method all --no-mesh --comb input/kombinasi_beban.csv

# Report
uvx --from git+https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil fea-report \
  --master --comb input/kombinasi_beban.csv --thickness 0.5
```

> **💡 TIPS (Untuk PC Tanpa Git):**
> Jika komputer Anda (atau rekan Anda) tidak memiliki `git` yang ter-install, ganti sumber ke file `.zip` agar tetap bisa dijalankan:
> ```bash
> uvx --from https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil/archive/refs/heads/main.zip fea-plot --help
> ```

### Cara 2: Clone dan jalankan lokal

```bash
git clone https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil.git
cd plot_kontur_plate_fea_midas_civil

# Jalankan via uv (otomatis install dependencies)
uv run fea-plot --method average-nodal --no-mesh
uv run fea-report --master --comb input/kombinasi_beban.csv

# Atau cara tradisional
uv run python plot_contur_fea.py --method all --no-mesh
uv run python generate_reports.py --master --comb input/kombinasi_beban.csv
```

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

Siapkan file CSV di folder `input/` pada working directory (atau copy dari salah satu case di folder `example_data_input/` jika Anda ingin melakukan test):

| File | Deskripsi | Kolom Utama |
|------|-----------|-------------|
| `kordinat_node.csv` | Koordinat node | ID, X, Y, Z |
| `connectivity_data.csv` | Konektivitas elemen | iEL, 1, 2, 3, 4 |
| `gaya_elemen_per_load_case.csv` | Gaya/momen per elemen | Elem, Load, Node, Forces... |
| `kombinasi_beban.csv` | Definisi kombinasi beban | Name, Active, Case 1, Factor 1, ... |

> **💡 Note:** Folder `example_data_input/` disertakan dalam repository ini agar Anda dapat langsung melakukan test drive. Cukup copy CSV dari subfolder yang ada (misal `example_1`) lalu upload di UI atau letakkan di `input/` untuk penggunaan CLI.

---

## 🛠️ Commands Reference

### `fea-plot` — Generate Contour Plots

```bash
fea-plot [OPTIONS]
```

| Argument | Deskripsi | Default |
|----------|-----------|---------|
| `--method` | `average-nodal`, `element-nodal`, `element-center`, `all` | `average-nodal` |
| `--theme` | Tema visual plot (`light` atau `dark`) | `light` |
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
| `--method` | `average-nodal`, `element-nodal`, `element-center`, `all` | `average-nodal` |
| `--format` | Format output (`md` atau `typst`) | `md` |
| `--comb` | Path ke CSV kombinasi beban | *(none)* |
| `--comb-select` | Wildcard filter untuk kombinasi (cth: `K_1*`) | `*` |
| `--master` | Generate Master Summary | `False` |
| `--thickness` | Tebal pelat dalam meter | `0.400` |
| `--kordinat` | Path ke CSV koordinat | *(auto-detect)* |
| `--connectivity` | Path ke CSV konektivitas | *(auto-detect)* |
| `--gaya` | Path ke CSV gaya/momen | *(auto-detect)* |
| `--output` | Folder output | `output` |

**Contoh:**
```bash
# Markdown (default) — konsisten dengan interpolasi mesh
fea-report --master --comb input/kombinasi_beban.csv

# Typst output — siap di-compile
fea-report --master --comb input/kombinasi_beban.csv --format typst

# Filter kombinasi & method tertentu
fea-report --method element-center --comb input/kombinasi_beban.csv --comb-select "K_1*" --format typst
```

### `fea-rebar` — Generate Rebar Analysis Plots

Menghitung kebutuhan luas tulangan utama pelat (lentur) berdasarkan momen hasil FEM, lalu menghasilkan *contour plot* untuk *Spasi Tulangan* atau *Diameter Tulangan*. Sangat berguna untuk melakukan zonasi pembesian.

```bash
fea-rebar [OPTIONS]
```

| Argument | Deskripsi | Default |
|----------|-----------|---------|
| `--fc` | Kuat tekan beton (MPa) | `30` |
| `--fy` | Kuat leleh baja (MPa) | `420` |
| `--thickness` | Tebal pelat dalam meter | `0.400` |
| `--cover` | Selimut beton bersih (mm) | `40` |
| `--diameter` | Diameter tulangan (mm). Jika diset, output = plot **Spasi** | *(none)* |
| `--spacing` | Spasi tulangan (mm). Jika diset, output = plot **Diameter** | `150` |
| `--shear` | Mengaktifkan perhitungan **tulangan geser** (Av/s dan diameter dari Vxx/Vyy) | `False` |
| `--shear-spacing-long` | Spasi sengkang arah memanjang (longitudinal) dalam mm | `150` |
| `--shear-spacing-trans` | Spasi sengkang melintang (transversal) dalam mm | `150` |
| `--method` | `average-nodal`, `element-nodal`, `element-center`, `all` | `average-nodal` |
| `--comb` | Path ke file CSV kombinasi beban | *(none)* |
| `--comb-select` | Wildcard filter untuk memproses kombinasi tertentu (cth: `K_1*`) | `*` |
| `--theme` | Tema visual plot (`light` atau `dark`) | `light` |

> **Perilaku Superposisi:**
> - Jika `--comb` **tidak** diatur: Program menghitung tulangan untuk setiap Load Case Tunggal (berguna untuk beban ultimate yang sudah tergabung seperti *pilecap*).
> - Jika `--comb` diatur: Program **hanya** menghitung tulangan untuk Kombinasi Beban yang sesuai filter.
> - Program otomatis menghasilkan folder **Envelope_Rebar** yang berisi nilai maksimal dari seluruh load case/kombinasi yang diproses.

**Contoh:**
```bash
# Mode Output Diameter (cari diameter tulangan terdekat jika dipasang jarak 150mm)
fea-rebar --fc 30 --fy 420 --spacing 150 --comb input/kombinasi_beban.csv --no-mesh

# Mode Output Spasi (cari jarak spasi pakai jika kita menggunakan besi D16)
fea-rebar --fc 30 --fy 420 --diameter 16 --comb input/kombinasi_beban.csv --no-mesh --comb-select "K_1*"

# Analisis Geser (Shear) dengan spasi sengkang 150x150 mm
fea-rebar --shear --shear-spacing-long 150 --shear-spacing-trans 150 --comb input/kombinasi_beban.csv --no-mesh
```
### `fea-ui` — Interactive Web UI (Dashboard)

Antarmuka grafis berbasis browser. User cukup **drag-drop CSV** — tidak perlu mengetik perintah CLI. Menggunakan **Plotly** interaktif (zoom, pan, hover) untuk display, dan **Matplotlib** untuk save PNG.

```bash
fea-ui    # Membuka browser otomatis ke http://localhost:8501
```

Atau tanpa install, download `run_fea.bat` dari [GitHub Releases](https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil/releases), lalu double-click di folder kerja.

**Fitur UI (v1.6.0):**
- **📊 Contour Plot** — Display Only / Save Only / Display & Save. Kini dengan **Symmetric Colorbar** (skala seimbang nilai +/-).
- **📋 Report** — Generate MD atau Typst, preview langsung di browser.
- **🧮 Rebar Analysis** — Zonasi interaktif untuk tulangan lentur & tulangan geser (baru!) sekaligus mendeteksi penampang tipis otomatis (SECTION INADEQUATE).
- **🛡️ Secure Sequential Save** — Mesin penyimpanan gambar yang telah dioptimalkan untuk Windows agar tidak crash/error saat export masal.

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

### Perhitungan Tulangan Lentur (ACI/SNI)

1. **Tinggi Efektif ($d$)**
   Bergantung pada lapisan tulangan. Secara standar, arah **X** diletakkan pada lapis terluar.
   - **Arah X (Bottom/Top):** $d_x = h - t_{cc} - 0.5D$
   - **Arah Y (Bottom/Top):** $d_y = h - t_{cc} - D - 0.5D$

2. **Luas Tulangan Perlu ($A_{s,perlu}$)**
   $$A_{s,perlu} = \frac{0.85 \cdot f'_c \cdot b \cdot d}{f_y} \left( 1 - \sqrt{1 - \frac{2 \cdot M_u}{\phi \cdot 0.85 \cdot f'_c \cdot b \cdot d^2}} \right)$$
   *(di mana $\phi = 0.9$ untuk lentur, $b = 1000$ mm)*
   > **Peringatan Sistem (v1.5.0):** Jika nilai di dalam akar negatif atau diameter perlu > D32, program akan memberikan label **SECTION INADEQUATE** (Warna Magenta/Ungu) pada plot untuk mempermudah identifikasi zona gagal.

3. **Kalkulasi Spasi dari Kuota Diameter ($D$)**
   $$s_{calc} = \frac{(0.25 \cdot \pi \cdot D^2) \cdot 1000}{A_{s,perlu}}$$

4. **Kalkulasi Diameter dari Spasi Target ($s$)**
   $$D_{req} = \sqrt{\frac{4 \cdot (A_{s,perlu} \cdot s / 1000)}{\pi}}$$
   *Program kemudian memilih diameter aktual terbesar berikutnya dari standar pasaran: [13, 16, 19, 22, 25, 32].*

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
**Version:** 1.5.0