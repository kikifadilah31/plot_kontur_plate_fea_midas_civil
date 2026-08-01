# FEA 2D Contour Plot Generator
**Version 2.0.0 | Professional FEA Visualization & Reporting**

High-performance Python tool for generating FEA contour plots and comprehensive technical reports from Midas Civil (or similar) plate/shell results.

---

## ⚠️ Catatan Upgrade ke 2.0.0

Versi ini menambahkan pemeriksaan code SNI 2847:2019 yang sebelumnya tidak ada. **Hasil hitungan tulangan akan berbeda dari v1.x** pada model yang sama:

| Perubahan | Dampak |
|-----------|--------|
| Tulangan minimum susut & suhu (Pasal 24.4.3.2) | Zona bermomen kecil kini terisi tulangan minimum, bukan mendekati nol |
| Verifikasi daktilitas $\rho_{max}$ (Tabel 21.2.2) | Penampang yang tidak *tension-controlled* ditandai **SECTION INADEQUATE** |
| Spasi di bawah batas minimum (Pasal 25.2.1) | Dulu di-*clamp* agar terlihat wajar, sekarang ditandai gagal |
| Batas hancur badan geser (Pasal 22.5.1.2) | Zona geser ekstrem ditandai gagal, bukan diberi sengkang lebih besar |
| Tinggi efektif Mode B iteratif | $A_s$ naik di zona bertulangan besar (dulu *underestimate* karena asumsi D16 tetap) |
| $V_c$ disatukan ke bentuk SNI $0{,}17\lambda\sqrt{f'_c}b_w d$ | Selisih <2,5% dari rumus AASHTO yang dipakai v1.x |

> **Membandingkan dengan hasil lama:** jalankan `fea-rebar --no-as-min` untuk menonaktifkan tulangan minimum, sehingga selisihnya bisa Anda telusuri satu per satu sebelum dipakai untuk desain.

**Perbaikan bug yang menyertai:**

- `fea-rebar --method all` tidak lagi crash (envelope antar-metode punya panjang array berbeda)
- **`--method element-center` kini benar-benar menghasilkan plot** — sebelumnya 100% gagal di `fea-plot` maupun `fea-rebar`
- Zona *inadequate* pada `element-center` kini berwarna abu-abu; dulu putih, tidak bisa dibedakan dari "tidak butuh tulangan"
- `--rebar-select` dengan daftar panjang tidak lagi menggagalkan seluruh plot konfigurasi
- Resolusi nama load case kini deterministik dan memberi peringatan bila ambigu
- Elemen dengan node hilang tidak lagi mencemari hasil (dulu membaca memori tak terinisialisasi)
- **Exit code kini mencerminkan kenyataan**: dulu program mencetak `[SUCCESS]` dan keluar dengan kode 0 walaupun seluruh plot gagal

---

## 🚀 Quick Start

### Cara 1: Jalankan langsung dari GitHub (tanpa clone)

Hanya butuh [uv](https://docs.astral.sh/uv/) terinstall di komputer.

```bash
# Install permanen ke PATH
uv tool install git+https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil

# Jika di masa depan ada update di GitHub, perbarui dengan:
uv tool upgrade fea-contour-plotter

# Lalu jalankan kapan saja dari terminal (pastikan berada di folder yang berisi folder input/)
fea-plot --method average-nodal --no-mesh
fea-report --master --comb input/kombinasi_beban.csv
fea-rebar --fc 30 --fy 420
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
| `--diameter` | Kode/Diameter tulangan (misal: `16`, `2D25`). Jika diset, output = plot **Spasi** | *(none)* |
| `--spacing` | Spasi tulangan (mm). Jika diset, output = plot **Diameter/Konfigurasi** | `150` |
| `--rebar-select`| Pilih daftar konfigurasi tulangan untuk Mode B (misal: `16 22 2D25 2D32`) | *(default: D13-D32)* |
| `--shear` | Mengaktifkan perhitungan **tulangan geser** (Av/s dan diameter dari Vxx/Vyy) | `False` |
| `--shear-spacing-long` | Spasi sengkang arah memanjang (longitudinal) dalam mm | `150` |
| `--shear-spacing-trans` | Spasi sengkang melintang (transversal) dalam mm | `150` |
| `--shear-select` | Pilih daftar diameter sengkang geser kustom (misal: `10 13 16 19 22 25 32`) | *(default: D10-D25)* |
| `--no-annotation` | Sembunyikan anotasi `MAX` marker dan *badge SECTION INADEQUATE* pada plot | `False` |
| `--no-as-min` | Nonaktifkan tulangan minimum SNI 24.4.3.2 (hanya untuk membandingkan dengan hasil v1.x) | `False` |
| `--method` | `average-nodal`, `element-nodal`, `element-center`, `all` | `average-nodal` |
| `--comb` | Path ke file CSV kombinasi beban | *(none)* |
| `--comb-select` | Wildcard filter untuk memproses kombinasi tertentu (cth: `K_1*`) | `*` |
| `--theme` | Tema visual plot (`light` atau `dark`) | `light` |

> **Konfigurasi Tulangan Kustom:**
> Sistem mendukung 24 variasi tulangan (D13–4D32) termasuk *bundle* (misal: 2D25, 3D32). Gunakan argumen `--rebar-select` untuk membatasi opsi mana saja yang dimunculkan pada visualisasi kontur. Hal ini dapat menghilangkan peringatan *Section Inadequate* palsu akibat batas default D32.

> **Perilaku Superposisi:**
> - Jika `--comb` **tidak** diatur: Program menghitung tulangan untuk setiap Load Case Tunggal (berguna untuk beban ultimate yang sudah tergabung seperti *pilecap*).
> - Jika `--comb` diatur: Program **hanya** menghitung tulangan untuk Kombinasi Beban yang sesuai filter.
> - Program otomatis menghasilkan folder **Envelope_Rebar** yang berisi nilai maksimal dari seluruh load case/kombinasi yang diproses.

**Contoh:**
```bash
# Mode Output Konfigurasi: cari konfigurasi tulangan dari list pilihan jika dipasang jarak 150mm
fea-rebar --fc 30 --fy 420 --spacing 150 --rebar-select 16 22 25 2D25 2D32 --comb input/kombinasi_beban.csv --no-mesh

# Mode Output Spasi: cari jarak spasi aman jika kita menggunakan besi bundle 2D25
fea-rebar --fc 30 --fy 420 --diameter 2D25 --comb input/kombinasi_beban.csv --no-mesh

# Mode Default (Backward Compatible): cari diameter tunggal terdekat (D13 - D32 max)
fea-rebar --fc 30 --fy 420 --spacing 150 --comb input/kombinasi_beban.csv --no-mesh

# Analisis Geser (Shear) dengan pembatasan diameter sengkang spesifik (misal: hanya D10, D13, D16)
fea-rebar --shear --shear-spacing-long 150 --shear-spacing-trans 150 --shear-select 10 13 16 --comb input/kombinasi_beban.csv --no-mesh

# Menonaktifkan anotasi MAX dan badge Inadequate untuk pelaporan presentasi estetika
fea-rebar --spacing 150 --no-annotation
```


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

### Perhitungan Tulangan Geser (Sengkang)
Berbasis pias pelat $b_w = 1000$ mm, gaya dalam dihitung sebagai rasio per unit lebar.

**1. Kapasitas Geser Beton ($V_c$)** — SNI 2847:2019 Pasal 22.5.5.1
$$ V_c = 0.17 \cdot \lambda \cdot \sqrt{f'_c} \cdot b_w \cdot d $$
*(Beton normal-weight: $\lambda = 1.0$)*

**2. Rasio Luas Kebutuhan ($A_v/s$)**
$$ V_s = \frac{V_u}{\phi_v} - V_c \qquad (\phi_v = 0.75) $$
$$ \frac{A_v}{s} = \frac{V_s}{f_{yt} \cdot d} $$
Sengkang hanya diperlukan bila $V_u > 0.5 \phi_v V_c$. Bila diperlukan, berlaku batas minimum Pasal 9.6.3.4:
$$ \left(\frac{A_v}{s}\right)_{min} = \max\left(0.062\sqrt{f'_c}\frac{b_w}{f_{yt}},\; 0.35\frac{b_w}{f_{yt}}\right) $$

**3. Batas Hancur Badan** — SNI Pasal 22.5.1.2
$$ V_s \leq 0.66 \sqrt{f'_c} \cdot b_w \cdot d $$
> Bila terlampaui, zona ditandai **SECTION INADEQUATE**. Menambah diameter sengkang **tidak** menyelesaikan kondisi ini — tebal pelat yang harus dinaikkan.

**4. Konversi Diameter Nominal**
$$ D_s = \sqrt{\frac{4 \cdot (A_v/s) \cdot s_{\text{longitudinal}} \cdot s_{\text{transversal}}}{\pi \cdot 1000}} $$

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

   > **Mode B iteratif (v2.0.0):** karena $d$ bergantung pada diameter sedangkan diameter justru yang dicari, program melakukan iterasi: hitung $d$ → hitung $A_s$ → pilih tulangan → hitung ulang $d$, sampai stabil (maks. 5 iterasi). Revisi diameter hanya ke arah membesar, sehingga iterasinya dijamin berhenti dan konservatif. Label `d_eff` pada plot menampilkan rentang bila nilainya bervariasi. Mode A tidak beriterasi karena diameternya sudah diketahui.

2. **Luas Tulangan Perlu ($A_{s,perlu}$)**
   $$A_{s,perlu} = \frac{0.85 \cdot f'_c \cdot b \cdot d}{f_y} \left( 1 - \sqrt{1 - \frac{2 \cdot M_u}{\phi \cdot 0.85 \cdot f'_c \cdot b \cdot d^2}} \right)$$
   *(di mana $\phi = 0.9$ untuk lentur, $b = 1000$ mm)*

3. **Tulangan Minimum** — SNI Pasal 24.4.3.2 (susut & suhu, mengatur pelat)
   $$A_{s,min} = \rho_{min} \cdot b \cdot h, \qquad \rho_{min} = \begin{cases} 0.0020 & f_y < 420 \\ \max\left(0.0018 \cdot \frac{420}{f_y},\, 0.0014\right) & f_y \geq 420 \end{cases}$$
   *Perhatikan: dihitung terhadap penampang **bruto** ($b \times h$), bukan terhadap $d$.*

4. **Batas Daktilitas** — SNI Tabel 21.2.2
   $$\rho_{max} = 0.85 \cdot \beta_1 \cdot \frac{f'_c}{f_y} \cdot \frac{\varepsilon_{cu}}{\varepsilon_{cu} + \varepsilon_{ty} + 0.003}, \qquad \varepsilon_{ty} = \frac{f_y}{E_s}$$
   > $\phi = 0.9$ hanya sah untuk penampang *tension-controlled*. Alih-alih menurunkan $\phi$ diam-diam, penampang yang melampaui $\rho_{max}$ ditandai **SECTION INADEQUATE** — jawaban yang benar untuk pelat adalah menebalkan penampang, bukan mengurangi daktilitas.

**Kondisi yang ditandai SECTION INADEQUATE (warna abu-abu gelap):**
> - Nilai di dalam akar negatif — penampang tidak mampu memikul $M_u$
> - $A_s > \rho_{max} \cdot b \cdot d$ — penampang tidak daktail
> - Spasi hasil hitungan < $s_{min}$ — tulangan tidak mungkin dipasang serapat itu
> - Diameter/konfigurasi perlu melampaui daftar yang tersedia
> - $V_s$ melampaui batas hancur badan
>
> Jumlah titik gagal per kasus juga dicetak di konsol pada akhir proses.

5. **Kalkulasi Spasi dari Kuota Diameter ($D$)**
   $$s_{calc} = \frac{(0.25 \cdot \pi \cdot D^2) \cdot 1000}{A_{s,perlu}}$$
   Dibatasi $s_{max} = \min(2h,\ 450)$ mm (di-*clamp* turun, konservatif) dan $s_{min} = D + \max(25, D)$ mm per Pasal 25.2.1 — jarak **bersih** ditambah satu diameter. Di bawah $s_{min}$ ditandai gagal, tidak di-*clamp* naik.

6. **Kalkulasi Diameter dari Spasi Target ($s$)**
   $$D_{req} = \sqrt{\frac{4 \cdot (A_{s,perlu} \cdot s / 1000)}{\pi}}$$
   *Program kemudian memilih diameter aktual terbesar berikutnya dari standar pasaran: [13, 16, 19, 22, 25, 32].*

---

## 🏗️ Architecture

### Package Structure

```
src/fea_contour/
├── config.py           # Semua konstanta terpusat (termasuk konstanta material SNI)
├── math_utils.py       # Perhitungan tegangan + helpers
├── combination.py      # Parsing kombinasi + resolusi nama load case bertingkat
├── io_utils.py         # CSV loading & auto-detect
├── mesh.py             # MeshTopology class (+ valid_mask)
├── values.py           # ValueMapper class (Z-Array caching)
├── rebar.py            # Engine tulangan: lentur, geser, cek code SNI
├── plotting.py         # Plot worker kontur gaya + figure recycling
├── plotting_rebar.py   # Plot worker tulangan (colormap kategorikal)
├── reporting.py        # Report & master summary (Markdown)
├── reporting_typst.py  # Report & master summary (Typst)
├── cli_plot.py         # CLI: fea-plot
├── cli_report.py       # CLI: fea-report
└── cli_rebar.py        # CLI: fea-rebar

tests/                  # pytest — regresi bug + unit test engine perhitungan
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
| `[WARN] ... elemen dilewati` | Ada elemen di `connectivity_data.csv` yang node-nya tidak ada di `kordinat_node.csv`. Elemen tersebut dibuang dari mesh |
| `[WARN] Nama load case tidak cocok persis` | Program menyesuaikan nama secara otomatis. Periksa hasil penyesuaian yang dicetak — bila ditandai `AMBIGUOUS`, samakan penamaan di CSV kombinasi |
| Banyak zona **SECTION INADEQUATE** setelah upgrade ke 2.0.0 | Ini hasil pemeriksaan code yang baru, bukan bug. Bandingkan dengan `--no-as-min`, lalu tinjau tebal pelat / mutu beton / batasan diameter (`--rebar-select`) |
| `[FAILED] N plot gagal dibuat` | Program kini keluar dengan kode 1 bila ada plot gagal. Baca pesan error yang tercetak di atasnya |

---

## 📚 References

1. **Zienkiewicz, O.C. & Taylor, R.L.** (2000). *The Finite Element Method*. Butterworth-Heinemann.
2. **MIDAS Civil User Manual** (2023). *Post-Processing: Plate/Shell Element Results*.
3. **SNI 2847:2019** — *Persyaratan Beton Struktural untuk Bangunan Gedung*. BSN.
4. **ACI 318-19** — *Building Code Requirements for Structural Concrete*. ACI.

---

## 🧪 Pengembangan

```bash
# Test cepat (unit test engine perhitungan)
uv run pytest -m "not slow"
```

```bash
# Termasuk test end-to-end yang merender plot sungguhan
uv run pytest
```

---

**License:** MIT  
**Version:** 2.0.0