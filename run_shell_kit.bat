@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   shell-kit - CLI Launcher Wizard
echo ============================================
echo.

:: Check for uv
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] uv belum ter-install!
    echo Install dari: https://docs.astral.sh/uv/
    echo.
    pause
    exit /b 1
)

echo --------------------------------------------
echo PENGATURAN VERSI SISTEM
echo --------------------------------------------
echo [1] Jalankan Versi Terbaru (Normal)
echo [2] Update Paksa (Refresh Cache)
echo [3] Pilih Versi Spesifik (Contoh: v3.0.0)
echo.
set /p choice="Masukkan pilihan versi (1-3) [Default: 1]: "
if "%choice%"=="" set choice=1

if "%choice%"=="1" (
    set REMOTE_URL=https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil/archive/refs/heads/main.zip
    set EXTRA_FLAGS=
) else if "%choice%"=="2" (
    set REMOTE_URL=https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil/archive/refs/heads/main.zip
    set EXTRA_FLAGS=--refresh
    echo [INFO] Memaksa refresh cache...
) else if "%choice%"=="3" (
    set /p ver="Masukkan versi (Tags, misal v3.0.0): "
    set REMOTE_URL=https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil/archive/refs/tags/!ver!.zip
    set EXTRA_FLAGS=--refresh
) else (
    echo [WARN] Pilihan tidak valid, menggunakan mode 1.
    set REMOTE_URL=https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil/archive/refs/heads/main.zip
    set EXTRA_FLAGS=
)

echo.
echo --------------------------------------------
echo PILIH PERINTAH
echo --------------------------------------------
echo [1] rebar  (Analisis dan plot kebutuhan tulangan pelat)
echo [2] plot   (Plot kontur gaya dalam dan tegangan)
echo [3] ui     (Antarmuka grafis di browser - tanpa mengetik perintah)
echo.
set /p cmd_choice="Masukkan pilihan perintah (1-3) [Default: 1]: "
if "%cmd_choice%"=="" set cmd_choice=1

if "%cmd_choice%"=="3" (
    echo.
    echo ============================================
    echo   MEMBUKA ANTARMUKA GRAFIS
    echo ============================================
    echo   Hasil akan disimpan di folder ini:
    echo   %CD%
    echo.
    uvx !EXTRA_FLAGS! --with streamlit --from !REMOTE_URL! shell-kit ui
    echo.
    pause
    exit /b 0
)

if "%cmd_choice%"=="2" (
    set SUBCMD=plot
) else (
    set SUBCMD=rebar
)

echo.
echo --------------------------------------------
echo LAPORAN
echo --------------------------------------------
echo [1] Tanpa laporan (hanya gambar)
echo [2] Laporan PDF (siap lampir)
echo [3] Laporan Markdown
echo [4] Laporan Typst (sumber, gambar resolusi penuh)
echo.
set /p rep_choice="Masukkan pilihan laporan (1-4) [Default: 1]: "
if "%rep_choice%"=="" set rep_choice=1

if "%rep_choice%"=="2" (
    set REPORT_FLAGS=--report --format pdf
) else if "%rep_choice%"=="3" (
    set REPORT_FLAGS=--report
) else if "%rep_choice%"=="4" (
    set REPORT_FLAGS=--report --format typst
) else (
    set REPORT_FLAGS=
)

echo.
echo --------------------------------------------
echo PARAMETER TAMBAHAN (OPSIONAL)
echo --------------------------------------------
if "!SUBCMD!"=="rebar" (
    echo [Hint] Contoh: --fc 35 --fy 420 --thickness 0.5 --spacing 300 --shear
) else (
    echo [Hint] Contoh: --theme dark --no-mesh --method all
)
echo Tekan ENTER langsung untuk menggunakan setelan bawaan.
set /p user_args="Masukkan Argumen: "

echo.
echo ============================================
echo   MENGEKSEKUSI: shell-kit !SUBCMD! !REPORT_FLAGS! !user_args!
echo ============================================
uvx !EXTRA_FLAGS! --from !REMOTE_URL! shell-kit !SUBCMD! !REPORT_FLAGS! !user_args!

echo.
pause
