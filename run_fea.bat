@echo off
echo ============================================
echo   FEA Contour Plotter - Web UI
echo ============================================
echo.
echo Checking uv installation...
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] uv is not installed!
    echo Please install from: https://docs.astral.sh/uv/
    echo.
    pause
    exit /b 1
)
echo.
echo Launching FEA UI (first run may take a moment)...
echo Close this window to stop the server.
echo.
uvx --from git+https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil fea-ui
pause
