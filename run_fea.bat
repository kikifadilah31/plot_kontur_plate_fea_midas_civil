@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   FEA Contour Plotter - CLI Launcher Wizard
echo ============================================
echo.

:: Check for uv
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] uv is not installed!
    echo Please install from: https://docs.astral.sh/uv/
    echo.
    pause
    exit /b 1
)

echo --------------------------------------------
echo PENGATURAN VERSI SISTEM
echo --------------------------------------------
echo [1] Jalankan Versi Terbaru (Normal)
echo [2] Update Paksa (Refresh Cache)
echo [3] Pilih Versi Spesifik (Contoh: v1.8.0)
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
    set /p ver="Masukkan versi (Tags, misal v1.8.0): "
    set REMOTE_URL=https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil/archive/refs/tags/!ver!.zip
    set EXTRA_FLAGS=--refresh
) else (
    echo [WARN] Pilihan tidak valid, menggunakan mode 1.
    set REMOTE_URL=https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil/archive/refs/heads/main.zip
    set EXTRA_FLAGS=
)

echo.
echo --------------------------------------------
echo PILIH ALAT ANALISIS UTAMA
echo --------------------------------------------
echo [1] fea-rebar  (Analisis & Plot Kebutuhan Tulangan Pelat)
echo [2] fea-plot   (Plot Kontur Gaya Dalam Mentah Midas)
echo [3] fea-report (Automasi Generate Dokumen Laporan)
echo.
set /p tool_choice="Masukkan pilihan alat (1-3) [Default: 1]: "
if "%tool_choice%"=="" set tool_choice=1

if "%tool_choice%"=="1" set TOOL=fea-rebar
if "%tool_choice%"=="2" set TOOL=fea-plot
if "%tool_choice%"=="3" set TOOL=fea-report

echo.
echo --------------------------------------------
echo PARAMETER CLI (OPSIONAL)
echo --------------------------------------------
if "!TOOL!"=="fea-rebar" (
    echo [Hint] Contoh argumen: --fc 35 --fy 420 --thickness 3 --spacing 300 --shear
) else if "!TOOL!"=="fea-plot" (
    echo [Hint] Contoh argumen: --theme dark --no-mesh
) else (
    echo [Hint] Contoh argumen: --format typst --master
)
echo Tekan ENTER langsung untuk menggunakan setelan bawaan.
set /p user_args="Masukkan Argumen: "

echo.
echo ============================================
echo   MENGEKSEKUSI: !TOOL! !user_args!
echo ============================================
uvx !EXTRA_FLAGS! --from !REMOTE_URL! !TOOL! !user_args!

echo.
pause
