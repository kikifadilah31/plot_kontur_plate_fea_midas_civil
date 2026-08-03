# shell-kit
**Versi 3.3.0 | Post-processing pelat/shell Midas Civil**

Alat baris perintah untuk mengolah hasil elemen pelat/shell dari Midas Civil (atau solver sejenis): kontur gaya dalam, desain tulangan menurut SNI 2847:2019, dan laporan teknis **PDF** lengkap dengan diagram.

```bash
shell-kit plot  --method all --no-mesh
shell-kit rebar --fc 30 --fy 420 --spacing 150 --report --format pdf
```

---

## 🖥️ Baru di 3.3.0 — Antarmuka grafis (opsional)

Untuk yang tidak terbiasa dengan baris perintah:

```bash
shell-kit ui
```

Membuka formulir di browser untuk mengisi opsi lalu menjalankannya. **Hasilnya mendarat di folder kerja tempat perintah dipanggil, persis seperti menjalankan CLI langsung** — folder `output/` yang sama, isi yang sama.

Yang perlu dipahami soal rancangannya: **UI tidak menghitung apa pun sendiri.** Ia menyusun perintah lalu memanggil CLI sebagai subprocess. Perhitungan, pemeriksaan code, dan penulisan berkas seluruhnya lewat jalur kode yang sama. Konsekuensinya UI tidak bisa melenceng dari CLI — setiap opsi dan setiap perbaikan otomatis ikut.

> Repo ini pernah punya UI Streamlit yang meng-import potongan engine lalu menulis ulang orkestrasinya sendiri. UI itu akhirnya dihapus karena jadi implementasi kedua yang harus dijaga sinkron. Rancangan sekarang sengaja menghindari itu.

Formulir juga menampilkan **perintah setara** yang bisa disalin ke terminal atau dikirim ke rekan:

```bash
shell-kit rebar --fc 35 --no-as-min --shear --report --format pdf
```

### Memasang

Streamlit bersifat **opsional** — pengguna CLI tidak menanggung unduhannya.

| Cara | Perintah |
|------|----------|
| Pasang permanen | `uv tool install "shell-kit[ui] @ git+https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil"` |
| Pasang permanen, tanpa git | `uv tool install "shell-kit[ui] @ https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil/archive/refs/heads/main.zip"` |
| Sekali jalan | `uvx --with streamlit --from git+https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil shell-kit ui` |
| Sekali jalan, tanpa git | `uvx --with streamlit --from https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil/archive/refs/heads/main.zip shell-kit ui` |
| Dari clone lokal | `uv sync --extra ui` |

- Jangan tulis `--from <url>` berdampingan dengan `"shell-kit[ui]"` sebagai dua argumen terpisah — `uv` membacanya sebagai dua permintaan paket berbeda dan menolak dengan pesan *"conflicts with install request"*. Gabungkan keduanya sebagai satu spesifikasi PEP 508, seperti pada baris "Pasang permanen".
- Prefiks `git+https://...` memerintahkan `git clone`, jadi butuh git terpasang. Kalau PC tujuan tidak punya git, pakai salah satu baris "tanpa git" — itu unduhan arsip zip biasa, tidak menyentuh git sama sekali.
- `main.zip` selalu berisi commit terbaru, bukan versi terkunci, jadi `uv tool upgrade` tidak bisa diandalkan mendeteksi rilis baru lewat jalur ini. Untuk PC yang jarang di-upgrade ulang ini tidak masalah; kalau butuh upgrade rutin, jalur `git+` lebih cocok.
- Menjalankan `shell-kit ui` tanpa streamlit terpasang akan menampilkan petunjuk pasang ini, bukan error.

---

## ⚠️ Baru di 3.2.0 — Koreksi dasar tulangan minimum

**Hasil tulangan minimum berubah. Zona yang selama ini dikendalikan $A_{s,min}$ kini kira-kira separuhnya.**

$\rho_{min} \cdot b \cdot h$ adalah jumlah **total satu arah menembus seluruh tebal**, bukan jatah satu muka. Versi sebelumnya menerapkannya penuh ke keempat lapis — memasang $0{,}0072 A_g$ padahal yang diminta $0{,}0036 A_g$, yaitu **dua kali lipat per arah**. Sekarang jumlah itu dibagi antara muka atas dan bawah.

Ditambah `--as-min-surface-zone` untuk penampang tebal: pada pilecap 3 m, dasar lama menuntut 5400 mm²/m per lapis (sekitar D25–90 di keempat lapis, semata-mata sebagai minimum). Dengan `--as-min-surface-zone 300` turun ke 540 mm²/m. Rinciannya di [Tulangan Minimum](#-mathematical-context).

Perubahan lain: muka yang tidak bermomen sama sekali kini **tetap** mendapat lapis berisi $A_{s,min}$ — sebelumnya dilewati sepenuhnya, padahal susut & suhu tetap menuntut tulangan di situ.

---

## 🆕 Baru di 3.1.0 — Laporan PDF

`--format pdf` menghasilkan PDF siap lampir, dikompilasi **langsung di dalam Python**. Tidak perlu meng-install Typst, LaTeX, atau tool lain — kompilatornya ikut terbawa paket.

```bash
shell-kit rebar --spacing 150 --shear --report --format pdf
```

Yang dihasilkan:

| Berkas | Isi |
|--------|-----|
| `Laporan_Tulangan_<sumber>.pdf` | Laporan per load case/kombinasi — sekitar 5–6 MB, 14 halaman |
| `LAPORAN_LENGKAP.pdf` | **Satu dokumen untuk seluruh run** — halaman judul, daftar isi, dan setiap sumber sebagai bab terpisah |
| `*.typ` | Sumber Typst tetap disimpan, bisa disunting lalu di-compile ulang |
| `_figur_pdf/` | Salinan gambar yang diperkecil untuk cetak (lihat di bawah) |

**Soal ukuran berkas.** Plot disimpan pada resolusi tinggi (~620 DPI pada lebar A4). Menyematkannya apa adanya menghasilkan PDF 16 MB per laporan dan 178 MB untuk dokumen gabungan — terlalu besar untuk dikirim. Karena itu gambar diperkecil ke 1600 px (~240 DPI, tetap tajam untuk cetak) khusus untuk PDF. **File PNG asli tidak diubah sama sekali** dan tetap tersedia pada resolusi penuh.

> `--format typst` tidak melakukan penyusutan — bila Anda mengompilasi sendiri dan menginginkan resolusi penuh, gunakan format itu.

Bila kompilasi gagal, diagnostik Typst dicetak apa adanya, berkas `.typ` dipertahankan untuk ditelusuri, dan program keluar dengan kode 1.

---

## ⚠️ Catatan Upgrade ke 3.0.0

**Nama dan struktur perintah berubah total.** Tiga perintah lama digabung menjadi satu:

| Dulu | Sekarang |
|------|----------|
| `fea-plot [OPSI]` | `shell-kit plot [OPSI]` |
| `fea-rebar [OPSI]` | `shell-kit rebar [OPSI]` |
| `fea-report [OPSI]` | opsi `--report` pada `plot` maupun `rebar` |

Perintah lama **dihapus sepenuhnya** — tidak ada alias. Nama paket juga berubah dari `fea-contour-plotter` menjadi `shell-kit`, sehingga instalasi lama perlu diganti:

```bash
uv tool uninstall fea-contour-plotter
uv tool install git+https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil
```

**Mengapa berubah:** "fea" menyesatkan — alat ini bukan solver FEA melainkan post-processor untuk desain pelat beton bertulang. Nama `shell-kit` merujuk elemen *shell* yang diolahnya. Menyatukan tiga perintah juga menghapus inkonsistensi lama: `--comb-select` dulu hanya ada di dua perintah, `--no-annotation` hanya di satu. Sekarang seluruh opsi bersama didefinisikan sekali dan berlaku di mana-mana.

### Laporan kini menjadi opsi, bukan perintah

Tambahkan `--report` pada perintah apa pun. Dokumen ditulis berdampingan dengan plot yang bersangkutan, **dengan diagramnya tersemat langsung** sebagai figure:

```bash
shell-kit plot  --report                    # ringkasan gaya/tegangan + kontur
shell-kit rebar --report --format typst     # laporan tulangan siap compile
```

| Perintah | Dokumen yang dihasilkan | Isi |
|----------|------------------------|-----|
| `plot --report` | `Summary_<sumber>.md` + `MASTER_SUMMARY.md` | Properti penampang, envelope gaya/momen/tegangan beserta lokasinya, seluruh plot kontur tersemat |
| `rebar --report` | `Laporan_Tulangan_<sumber>.md` | Parameter desain & batas code yang dipakai, As perlu dan tulangan terpilih per lapis, **daftar koordinat titik SECTION INADEQUATE**, seluruh plot tulangan tersemat |

> Diagram ditautkan secara relatif terhadap lokasi dokumen, jadi seluruh folder output bisa dipindah atau di-zip tanpa merusak gambar. Plot yang gagal dirender tidak akan ditautkan — laporan tidak pernah menunjuk gambar rusak.

---

## ⚠️ Catatan Upgrade ke 2.0.0 (pemeriksaan code SNI)

Versi 2.0.0 menambahkan pemeriksaan SNI 2847:2019 yang sebelumnya tidak ada. **Hasil hitungan tulangan berbeda dari v1.x** pada model yang sama:

| Perubahan | Dampak |
|-----------|--------|
| Tulangan minimum susut & suhu (Pasal 24.4.3.2) | Zona bermomen kecil kini terisi tulangan minimum, bukan mendekati nol |
| Verifikasi daktilitas $\rho_{max}$ (Tabel 21.2.2) | Penampang yang tidak *tension-controlled* ditandai **SECTION INADEQUATE** |
| Spasi di bawah batas minimum (Pasal 25.2.1) | Dulu di-*clamp* agar terlihat wajar, sekarang ditandai gagal |
| Batas hancur badan geser (Pasal 22.5.1.2) | Zona geser ekstrem ditandai gagal, bukan diberi sengkang lebih besar |
| Tinggi efektif Mode B iteratif | $A_s$ naik di zona bertulangan besar (dulu *underestimate* karena asumsi D16 tetap) |
| $V_c$ disatukan ke bentuk SNI $0{,}17\lambda\sqrt{f'_c}b_w d$ | Selisih <2,5% dari rumus AASHTO yang dipakai v1.x |

> **Membandingkan dengan hasil lama:** jalankan `shell-kit rebar --no-as-min` untuk menonaktifkan tulangan minimum, sehingga selisihnya bisa Anda telusuri satu per satu sebelum dipakai untuk desain.

**Perbaikan bug yang menyertai:**

- `rebar --method all` tidak lagi crash (envelope antar-metode punya panjang array berbeda)
- **`--method element-center` kini benar-benar menghasilkan plot** — sebelumnya 100% gagal di kedua perintah
- Zona *inadequate* pada `element-center` kini berwarna abu-abu; dulu putih, tidak bisa dibedakan dari "tidak butuh tulangan"
- **Envelope kini mewarisi kegagalan**: dulu memakai `np.fmax` yang membuang NaN, sehingga satu titik hanya ditandai gagal bila *seluruh* load case gagal di situ
- `--rebar-select` dengan daftar panjang tidak lagi menggagalkan seluruh plot konfigurasi
- Resolusi nama load case kini deterministik dan memberi peringatan bila ambigu
- Elemen dengan node hilang tidak lagi mencemari hasil (dulu membaca memori tak terinisialisasi)
- **Exit code kini mencerminkan kenyataan**: dulu program mencetak `[SUCCESS]` dan keluar dengan kode 0 walaupun seluruh plot gagal

---

## 🚀 Quick Start

### Cara 1: Jalankan langsung dari GitHub (tanpa clone)

Hanya butuh [uv](https://docs.astral.sh/uv/) terinstall di komputer.

```bash
uv tool install git+https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil
```

Perbarui bila ada update di GitHub:

```bash
uv tool upgrade shell-kit
```

Lalu jalankan dari terminal (pastikan berada di folder yang berisi folder `input/`):

```bash
shell-kit rebar --fc 30 --fy 420 --spacing 150 --report
```

Atau jalankan sekali tanpa install:

```bash
uvx --from git+https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil shell-kit plot --method all --no-mesh
```

> **💡 TIPS (untuk PC tanpa Git):**
> Ganti sumber ke file `.zip` agar tetap bisa dijalankan:
> ```bash
> uvx --from https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil/archive/refs/heads/main.zip shell-kit --help
> ```

### Cara 2: Clone dan jalankan lokal

```bash
git clone https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil.git
```

```bash
uv run shell-kit plot --method average-nodal --no-mesh
```

```bash
uv run shell-kit rebar --comb input/kombinasi_beban.csv --report
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

> **💡 Note:** Folder `example_data_input/` disertakan dalam repository ini agar Anda dapat langsung melakukan test drive. Cukup copy CSV dari subfolder yang ada (misal `example_1`) ke folder `input/`.

---

## 🛠️ Commands Reference

```bash
shell-kit <perintah> [OPSI]
```

| Perintah | Fungsi |
|----------|--------|
| `plot` | Kontur gaya dalam, momen, dan tegangan serat atas/bawah |
| `rebar` | Kebutuhan tulangan lentur & geser menurut SNI 2847:2019 |

### Opsi bersama (berlaku di kedua perintah)

**Input & output**

| Argumen | Deskripsi | Default |
|---------|-----------|---------|
| `--kordinat` | Path ke CSV koordinat | *(auto-detect di `input/`)* |
| `--connectivity` | Path ke CSV konektivitas | *(auto-detect)* |
| `--gaya` | Path ke CSV gaya/momen | *(auto-detect)* |
| `--thickness` | Tebal pelat dalam meter | `0.400` |
| `--output` | Folder output | `output` |

**Metode & kombinasi**

| Argumen | Deskripsi | Default |
|---------|-----------|---------|
| `--method` | `average-nodal`, `element-nodal`, `element-center`, `all` | `average-nodal` |
| `--comb` | Path ke CSV kombinasi beban | *(none)* |
| `--comb-select` | Filter nama kombinasi dengan wildcard (cth: `K_1*`) | `*` |

**Tampilan**

| Argumen | Deskripsi | Default |
|---------|-----------|---------|
| `--theme` | Tema visual (`light` atau `dark`) | `light` |
| `--no-mesh` | Sembunyikan wireframe mesh | `False` |
| `--no-annotation` | Sembunyikan marker MAX/MIN dan badge SECTION INADEQUATE | `False` |

**Laporan**

| Argumen | Deskripsi | Default |
|---------|-----------|---------|
| `--report` | Hasilkan dokumen ringkasan dengan diagram tersemat | `False` |
| `--format` | Format laporan: `md`, `typst`, atau `pdf` | `md` |

---

### `shell-kit plot`

Menghasilkan contour plot gaya dalam, momen, dan tegangan serat atas/bawah.

```bash
# Semua metode + kombinasi + tanpa mesh
shell-kit plot --method all --comb input/kombinasi_beban.csv --no-mesh
```

```bash
# Satu metode dengan tebal custom, sekalian laporannya
shell-kit plot --method element-nodal --thickness 0.5 --report
```

```bash
# Laporan Typst untuk kombinasi tertentu saja
shell-kit plot --comb input/kombinasi_beban.csv --comb-select "K_1*" --report --format typst
```

---

### `shell-kit rebar`

Menghitung kebutuhan tulangan pelat dari momen dan geser hasil FEM, lalu memetakannya sebagai contour plot untuk keperluan zonasi pembesian.

**Opsi khusus — material & tulangan**

| Argumen | Deskripsi | Default |
|---------|-----------|---------|
| `--fc` | Kuat tekan beton f'c (MPa) | `30` |
| `--fy` | Kuat leleh baja fy (MPa) | `420` |
| `--cover` | Selimut beton bersih (mm) | `40` |
| `--diameter` | **Mode A** — tulangan terpasang, output = **spasi**. Contoh: `16`, `2D25` | *(none)* |
| `--spacing` | **Mode B** — spasi terpasang (mm), output = **tulangan** | `150` |
| `--rebar-select` | Batasi pilihan konfigurasi untuk Mode B (cth: `16 22 2D25 2D32`) | *(D13–D32)* |
| `--no-as-min` | Nonaktifkan tulangan minimum SNI 24.4.3.2 | `False` |
| `--as-min-surface-zone` | Batasi tebal per muka untuk tulangan minimum (mm), mis. `300`. Untuk rakit/pilecap tebal | *(tanpa batas)* |

**Opsi khusus — geser**

| Argumen | Deskripsi | Default |
|---------|-----------|---------|
| `--shear` | Aktifkan analisis tulangan geser (Av/s dari Vxx, Vyy) | `False` |
| `--shear-spacing-long` | Spasi sengkang arah memanjang (mm) | `150` |
| `--shear-spacing-trans` | Spasi sengkang melintang (mm) | `150` |
| `--shear-select` | Batasi diameter sengkang yang tersedia (cth: `10 13 16`) | *(D10–D25)* |

> **Konfigurasi Tulangan Kustom:**
> Sistem mendukung 24 variasi tulangan (D13–4D32) termasuk *bundle* (misal 2D25, 3D32). Gunakan `--rebar-select` untuk membatasi opsi yang dimunculkan pada kontur — ini menghilangkan peringatan *Section Inadequate* palsu akibat batas default D32.

> **Perilaku Superposisi:**
> - Tanpa `--comb`: tulangan dihitung untuk setiap Load Case tunggal (berguna bila beban sudah ultimate, misal pilecap).
> - Dengan `--comb`: **hanya** kombinasi beban yang sesuai filter yang dihitung.
> - Folder **Envelope_Rebar** (dan **Envelope_Shear** bila `--shear`) otomatis dibuat, berisi nilai maksimal dari seluruh kasus yang diproses. Titik yang gagal pada kasus mana pun ikut tertandai gagal di envelope.
> - Dengan `--report`, envelope mendapat laporannya sendiri (`Laporan_Tulangan_ENVELOPE`) dan ikut masuk ke `LAPORAN_LENGKAP`.

**Contoh:**

```bash
# Mode B — cari konfigurasi dari daftar pilihan bila dipasang jarak 150mm
shell-kit rebar --fc 30 --fy 420 --spacing 150 --rebar-select 16 22 25 2D25 2D32 --comb input/kombinasi_beban.csv --no-mesh
```

```bash
# Mode A — cari jarak spasi aman bila memakai besi bundle 2D25
shell-kit rebar --fc 30 --fy 420 --diameter 2D25 --comb input/kombinasi_beban.csv --no-mesh
```

```bash
# Analisis geser dengan pembatasan diameter sengkang, plus laporan Typst
shell-kit rebar --shear --shear-select 10 13 16 --comb input/kombinasi_beban.csv --no-mesh --report --format typst
```

```bash
# Menonaktifkan anotasi untuk keperluan presentasi
shell-kit rebar --spacing 150 --no-annotation
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

**`shell-kit plot`**

```
output/
└── 20260406_143000/
    ├── Method_average-nodal/              # Hanya jika --method all
    │   ├── Load_MS/
    │   │   ├── contour_Fxx_kN_per_m_.png
    │   │   ├── contour_Sig-xx_Top_kPa_Top_Fiber.png
    │   │   └── Summary_MS.md              # Jika --report
    │   ├── Combination_K_1_1/
    │   └── MASTER_SUMMARY.md              # Jika --report
    ├── Method_element-nodal/
    └── Method_element-center/
```

**`shell-kit rebar`**

```
output/
└── rebar_20260406_143000/
    ├── Load_MS/
    │   ├── rebar_As_Mxx_Bottom_X.png
    │   ├── rebar_diameter_s150_Mxx_Bottom_X.png
    │   ├── rebar_Avs_Vxx_Shear_X.png              # Jika --shear
    │   └── Laporan_Tulangan_MS.md                 # Jika --report
    ├── Combination_K_1_1/
    ├── Envelope_Rebar/                            # Maksimum seluruh kasus
    └── Envelope_Shear/                            # Jika --shear
```

> Laporan ditulis di dalam folder sumbernya masing-masing, sehingga tautan gambarnya tetap valid bila folder dipindahkan.

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

3. **Tulangan Minimum** — SNI 2847:2019 Pasal 24.4.3.2 (susut & suhu)
   $$A_{s,min} = \rho_{min} \cdot b \cdot h, \qquad \rho_{min} = \begin{cases} 0{,}0020 & f_y < 420 \text{ MPa} \\[4pt] \max\left(0{,}0018 \cdot \dfrac{420}{f_y},\; 0{,}0014\right) & f_y \geq 420 \text{ MPa} \end{cases}$$

   **Mengapa pelat memakai pasal susut & suhu, bukan pasal lentur.** Pada balok, tulangan minimum (Pasal 9.6.1.2) mencegah keruntuhan mendadak saat beton retak. Pada pelat, yang justru mengatur adalah **susut beton dan perubahan suhu** — retak akibat keduanya terjadi bahkan tanpa beban sama sekali. Karena itu pelat memakai Pasal 24.4.3.2, dan nilainya berlaku di **kedua arah**.

   **Mengapa dikali $h$, bukan $d$.** Susut dan suhu bekerja pada **seluruh** tebal penampang, bukan hanya pada bagian tertekan seperti pada lentur. Jadi acuannya penampang **bruto** ($b \times h$). Ini beda dari $A_{s,min}$ balok yang memakai $b \times d$ — memakai $d$ di sini akan menghasilkan angka terlalu kecil.

   **Mengapa rasionya turun saat $f_y$ naik.** Yang perlu dijaga adalah **gaya** tarik yang mampu ditahan tulangan, bukan luasnya. Baja bermutu lebih tinggi memberi gaya yang sama dengan luas lebih kecil, sehingga rasionya diskalakan dengan $420/f_y$. Batas bawah $0{,}0014$ mencegah rasio jatuh terlalu jauh pada baja bermutu sangat tinggi.

   **Ini jumlah TOTAL satu arah, bukan jatah satu muka.** Nilai di atas berlaku untuk penampang menembus seluruh tebal. Pelat yang bertulangan di dua muka **membagi** jumlah itu:

   $$A_{s,min}^{\text{per lapis}} = \rho_{min} \cdot b \cdot \frac{h}{2}$$

   Menerapkan jumlah penuh ke setiap lapis akan memasang $4 \times \rho_{min} A_g = 0{,}0072 A_g$, padahal yang diminta hanya $2 \times \rho_{min} A_g$ untuk arah X dan Y — **dua kali lipat per arah**.

   **Contoh** — pelat $h = 400$ mm, $b = 1000$ mm, $f_y = 420$ MPa:
   $$\rho_{min} = \max\left(0{,}0018 \cdot \tfrac{420}{420},\; 0{,}0014\right) = 0{,}0018$$
   $$A_{s,min}^{\text{penampang}} = 0{,}0018 \times 1000 \times 400 = 720 \text{ mm}^2\text{/m}$$
   $$A_{s,min}^{\text{per lapis}} = 720 / 2 = \mathbf{360 \text{ mm}^2\text{/m}}$$
   Setara D10–215 atau D13–370 di tiap muka, tiap arah.

4. **Batas Zona Permukaan untuk penampang tebal** — `--as-min-surface-zone`

   $\rho_{min}$ ditulis untuk pelat lantai biasa (150–300 mm). Menskalakannya linear terhadap rakit atau pilecap 3 m menghasilkan tulangan yang tidak masuk akal — **5400 mm²/m per lapis**, sekitar D25–90 di keempat lapis semata-mata sebagai minimum.

   Sebabnya fisis: retak susut & suhu adalah gejala **permukaan**. Inti penampang tebal tertahan oleh dirinya sendiri dan tidak berperilaku seperti pelat tipis. ACI 350-06 §7.12.2.1 membatasi tebal yang dipakai jadi 300 mm per muka untuk komponen >600 mm:

   $$A_{s,min}^{\text{per lapis}} = \rho_{min} \cdot b \cdot \min\left(\frac{h}{2},\; t_{zona}\right)$$

   | $h$ | Penampang | Per lapis | Dengan `--as-min-surface-zone 300` |
   |-----|-----------|-----------|-----------------------------------|
   | 200 mm | 360 | 180 (D10–435) | 180 — cap tidak berlaku |
   | 400 mm | 720 | 360 (D10–215) | 360 — cap tidak berlaku |
   | 1000 mm | 1800 | 900 (D10–85) | **540** (D10–145) |
   | 3000 mm | 5400 | 2700 (D19–105) | **540** (D10–145) |

   > **SNI 2847:2019 tidak memuat batas ini.** Opsi ini meminjam ACI 350-06 dan praktik umum rakit/pilecap, jadi sengaja dibuat **opt-in** — tidak aktif otomatis — dan selalu dicatat pada tabel Parameter Desain di laporan bila dipakai. Keputusan memakainya ada pada Anda.

   > **Cara `shell-kit` memakainya:** $A_s$ akhir $= \max(A_{s,perlu},\, A_{s,min}^{\text{per lapis}})$, per lapis per arah. Muka yang tidak bermomen sama sekali **tetap** dibuatkan lapisnya berisi $A_{s,min}$ saja — susut & suhu tetap menuntut tulangan di situ. Titik yang sudah ditandai *SECTION INADEQUATE* **tidak** diselamatkan oleh minimum ini. Nonaktifkan seluruhnya dengan `--no-as-min`.

   Kode: [`calc_as_min()`](src/shell_kit/rebar.py) (total penampang), [`calc_as_min_per_face()`](src/shell_kit/rebar.py) (jatah per lapis), [`apply_as_min()`](src/shell_kit/rebar.py).

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
src/shell_kit/
├── cli.py              # Satu-satunya entry point; pemilik seluruh argumen
├── cli_plot.py         # Alur `shell-kit plot`
├── cli_rebar.py        # Alur `shell-kit rebar`
│
├── config.py           # Semua konstanta terpusat (termasuk konstanta material SNI)
├── math_utils.py       # Perhitungan tegangan + helpers
├── combination.py      # Parsing kombinasi + resolusi nama load case bertingkat
├── io_utils.py         # CSV loading & auto-detect
├── mesh.py             # MeshTopology class (+ valid_mask)
├── values.py           # ValueMapper class (Z-Array caching)
├── rebar.py            # Engine tulangan: lentur, geser, cek code SNI
│
├── plotting.py         # Plot worker kontur gaya + figure recycling
├── plotting_rebar.py   # Plot worker tulangan (colormap kategorikal)
│
├── report_writer.py    # Path figure relatif + penulisan dokumen (dipakai bersama)
├── reporting.py        # Ringkasan gaya/tegangan (Markdown)
├── reporting_typst.py  # Ringkasan gaya/tegangan (Typst)
└── reporting_rebar.py  # Laporan tulangan (Markdown + Typst)

tests/                  # pytest — regresi bug + unit test engine perhitungan
```

Argumen bersama didefinisikan **sekali** di `cli.py` lalu dipasang ke setiap subcommand. Struktur lama — tiap perintah punya parser sendiri — adalah penyebab `--comb-select` hanya ada di dua perintah dan `--no-annotation` hanya di satu.

### Key Optimizations
- **Z-Array Pre-Caching**: Perhitungan berat dijalankan SEKALI per load case, bukan per plot
- **Figure Recycling**: Satu Matplotlib figure per CPU core, di-recycle untuk semua plot
- **MeshTopology Singleton**: Mesh dibangun sekali per metode, digunakan ulang untuk semua load case

---

## 📊 Reporting & Master Summary

Aktifkan dengan `--report` pada perintah mana pun. Format diatur lewat `--format md` (default) atau `--format typst`.

### `plot --report`

**Per sumber** (`Summary_<nama>.md`):
- Properti penampang (A, I)
- Ringkasan gaya & momen: maks/min/rata-rata beserta lokasinya
- Ringkasan tegangan berikut gaya dan momen penyumbangnya
- **Seluruh plot kontur tersemat sebagai figure bernomor**

**Master Summary** (`MASTER_SUMMARY.md`), agregasi seluruh load case dan kombinasi:
- Top 20 tegangan absolut tertinggi lintas sumber
- Envelope gaya & momen, peringkat per parameter
- Global max/min per jenis tegangan

### `rebar --report`

Per sumber (`Laporan_Tulangan_<nama>.md`), **plus `Laporan_Tulangan_ENVELOPE`** yang meringkas nilai maksimum seluruh kasus — inilah yang dipakai untuk desain menentukan:

- **Parameter desain** — h, selimut, f'c, fy, mode perhitungan, serta batas code yang benar-benar dipakai ($A_{s,min}$, $\rho_{max}$, $\beta_1$)
- **Ringkasan per lapis** — rentang $d_{eff}$, $A_s$ maksimum dan lokasinya, tulangan terpilih di titik terkritis
- **Ringkasan tulangan geser** — $d_v$, $A_v/s$ maksimum, sengkang terpilih, jumlah titik yang butuh sengkang, dan zona hancur badan
- **Zona SECTION INADEQUATE** — daftar koordinat titik yang gagal, beserta penjelasan penyebab dan tindakan yang relevan. Bila tidak ada yang gagal, dinyatakan eksplisit
- **Seluruh plot tulangan tersemat sebagai figure**

### Dua jenis kegagalan yang dibedakan

Tabel ringkasan memisahkan dua hal yang sering tertukar, karena penanganannya berbeda:

| Kolom | Arti | Tindakan |
|-------|------|----------|
| **Penampang gagal** | Momen melampaui kapasitas lentur, atau $\rho > \rho_{max}$ sehingga penampang tidak daktail | Tebalkan pelat atau naikkan mutu beton |
| **Tulangan tak muat** | $A_s$ terpenuhi secara teori, tapi tidak ada diameter/konfigurasi tersedia yang cukup pada spasi ini | Perlebar pilihan lewat `--rebar-select`, atau rapatkan spasi |
| **Hancur badan** (geser) | $V_s > 0{,}66\sqrt{f'_c}\,b_w d$ (SNI 22.5.1.2) | Tebalkan pelat — sengkang lebih besar tidak menolong |

> Daftar titik gagal dibatasi 15 baris per lapis agar dokumen tetap terbaca; jumlah sebenarnya tetap dicantumkan dan sebaran lengkapnya terlihat pada diagram.

### Dokumen gabungan & PDF

`--format typst` dan `--format pdf` menghasilkan **`LAPORAN_LENGKAP`** di akar folder metode: halaman judul berisi parameter run, daftar isi otomatis, lalu setiap sumber sebagai bab terpisah. Untuk `rebar`, halaman judulnya juga mencantumkan total titik SECTION INADEQUATE seluruh run.

Dengan `--format pdf`, kompilasi berjalan otomatis. Bila Anda menyunting `.typ`-nya sendiri, compile ulang dengan:

```bash
typst compile --root . LAPORAN_LENGKAP.typ
```

> `--root .` diperlukan karena laporan per-sumber menautkan gambar di folder `_figur_pdf/` yang berada di atasnya.

---

## 🔍 Troubleshooting

| Masalah | Solusi |
|---------|--------|
| `ERROR: Missing input files` | Pastikan file CSV ada di folder `input/` |
| Plot lambat di `[1/3]` | Normal untuk `element-nodal` — Z-Array caching berjalan |
| Kombinasi tidak ditemukan | Periksa nama load case di CSV cocok dengan output FEA |
| `ModuleNotFoundError` | Jalankan via `uv run` atau install package dulu |
| `fea-plot: command not found` (atau `fea-rebar`/`fea-report`) | Perintah lama dihapus di v3.0.0. Gunakan `shell-kit plot` / `shell-kit rebar`; laporan kini opsi `--report`. Lihat [Catatan Upgrade ke 3.0.0](#️-catatan-upgrade-ke-300) |
| `--format ... diabaikan` | `--format` hanya berlaku bersama `--report`. Tambahkan `--report` |
| Gambar tidak muncul di laporan | Path gambar relatif terhadap dokumen — pindahkan seluruh folder output, bukan file laporannya saja |
| `gagal mengompilasi ...typ` | Diagnostik Typst tercetak di bawahnya dan file `.typ` dipertahankan. Buka file itu pada baris yang disebut |
| `Paket 'typst' tidak ditemukan` | Instalasi Anda dibuat sebelum fitur PDF ada. Jalankan `uv tool upgrade shell-kit`, atau `uv sync` bila dari clone |
| PDF terasa besar | Wajar: tiap laporan memuat 12+ diagram kontur. Gambar sudah diperkecil ke ~240 DPI. Untuk berbagi cepat, kirim PDF per sumber, bukan `LAPORAN_LENGKAP.pdf` |
| Ingin resolusi gambar penuh di dokumen | Pakai `--format typst` lalu compile sendiri — format itu tidak memperkecil gambar |
| `[WARN] ... elemen dilewati` | Ada elemen di `connectivity_data.csv` yang node-nya tidak ada di `kordinat_node.csv`. Elemen tersebut dibuang dari mesh |
| `[WARN] Nama load case tidak cocok persis` | Program menyesuaikan nama secara otomatis. Periksa hasil penyesuaian yang dicetak — bila ditandai `AMBIGUOUS`, samakan penamaan di CSV kombinasi |
| Banyak zona **SECTION INADEQUATE** setelah upgrade ke 2.0.0 | Ini hasil pemeriksaan code yang baru, bukan bug. Bandingkan dengan `--no-as-min`, lalu tinjau tebal pelat / mutu beton / batasan diameter (`--rebar-select`) |
| Tulangan minimum terasa berlebih pada pelat tebal | Wajar: $\rho_{min} \cdot h$ ditulis untuk pelat 150–300 mm. Pakai `--as-min-surface-zone 300` (lihat catatan 3.2.0) |
| Hasil $A_{s,min}$ separuh dari versi sebelumnya | Itu koreksi di 3.2.0 — jumlah kode dibagi antara dua muka. Yang sebelumnya 2× lipat per arah |
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
**Version:** 3.3.0