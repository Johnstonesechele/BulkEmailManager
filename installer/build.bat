@echo off
setlocal enabledelayedexpansion

echo ================================================
echo   Bulk Email Manager - Build Script
echo ================================================
echo.

cd /d "%~dp0.."

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

:: Check PyInstaller
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

:: Clean previous builds
echo [1/5] Cleaning previous builds...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

:: Build with PyInstaller
echo [2/5] Building with PyInstaller...
python -m PyInstaller BulkEmail.spec --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller build failed!
    pause
    exit /b 1
)

:: Verify build
if not exist "dist\BulkEmailManager\BulkEmailManager.exe" (
    echo ERROR: Build output not found!
    pause
    exit /b 1
)

echo [3/5] Build complete: dist\BulkEmailManager\BulkEmailManager.exe
echo.

:: Try to build MSI with cx_Freeze
echo [4/5] Attempting MSI build with cx_Freeze...
python setup_cx.py bdist_msi >nul 2>&1
if errorlevel 1 (
    echo   MSI build skipped (cx_Freeze bdist_msi not available for this platform)
    echo   Use the Inno Setup script instead for a professional installer.
) else (
    echo   MSI built successfully!
)

:: Check for Inno Setup
echo [5/5] Checking for Inno Setup...
set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
)

if defined ISCC (
    echo   Building installer with Inno Setup...
    "%ISCC%" "installer\setup.iss"
    if errorlevel 1 (
        echo   Inno Setup build failed.
    ) else (
        echo   Installer built: installer\output\BulkEmailManager-Setup.exe
    )
) else (
    echo   Inno Setup not found. To create a professional installer:
    echo   1. Download Inno Setup: https://jrsoftware.org/isinfo.php
    echo   2. Install it
    echo   3. Open installer\setup.iss in Inno Setup
    echo   4. Click Build ^> Compile
)

echo.
echo ================================================
echo   Build Summary
echo ================================================
echo   Portable app: dist\BulkEmailManager\BulkEmailManager.exe
echo.

if exist "installer\output\BulkEmailManager-*-Setup.exe" (
    echo   Installer:   installer\output\BulkEmailManager-Setup.exe
) else (
    echo   Installer:   Not built (see instructions above)
)

echo.
echo   To run the portable app:
echo     dist\BulkEmailManager\BulkEmailManager.exe
echo.
echo ================================================
pause
