@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   FEA Contour Plotter - Web UI Loader
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

echo Pilih mode jalankan:
echo [1] Jalankan Versi Terbaru (Normal)
echo [2] Update Paksa (Refresh Cache) - Pilih ini jika v1.5.0 belum muncul
echo [3] Pilih Versi Spesifik (Contoh: v1.4.0)
echo.
set /p choice="Masukkan pilihan (1-3) [Default: 1]: "

if "%choice%"=="" set choice=1

if "%choice%"=="1" (
    set REMOTE_URL=https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil/archive/refs/heads/main.zip
    set EXTRA_FLAGS=
) else if "%choice%"=="2" (
    set REMOTE_URL=https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil/archive/refs/heads/main.zip
    set EXTRA_FLAGS=--refresh
    echo [INFO] Memaksa refresh cache...
) else if "%choice%"=="3" (
    set /p ver="Masukkan versi (Tags, misal v1.4.0): "
    set REMOTE_URL=https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil/archive/refs/tags/!ver!.zip
    set EXTRA_FLAGS=--refresh
) else (
    echo [WARN] Pilihan tidak valid, menggunakan mode 1.
    set REMOTE_URL=https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil/archive/refs/heads/main.zip
    set EXTRA_FLAGS=
)

echo.
echo Launching FEA UI...
echo (Tutup jendela ini untuk mematikan server)
echo.

uvx %EXTRA_FLAGS% --from %REMOTE_URL% fea-ui

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Terjadi kesalahan saat menjalankan aplikasi.
    echo Jika menggunakan Mode 3, pastikan Tag Versi benar (ada huruf 'v').
    pause
)
