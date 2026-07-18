# Bulk Email Manager - Build Script
# Run this script to build the application and installer

param(
    [switch]$SkipMSI,
    [switch]$SkipInnoSetup,
    [switch]$PortableOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Bulk Email Manager - Build Script" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $ProjectRoot

# ── Step 1: Verify prerequisites ──────────────────────────────────────
Write-Host "[1/6] Checking prerequisites..." -ForegroundColor Yellow

try {
    $pyVer = python --version 2>&1
    Write-Host "  Python: $pyVer" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Python not found. Install Python 3.10+" -ForegroundColor Red
    exit 1
}

try {
    python -c "import PySide6" 2>&1 | Out-Null
    Write-Host "  PySide6: OK" -ForegroundColor Green
} catch {
    Write-Host "  Installing PySide6..." -ForegroundColor Yellow
    pip install PySide6
}

try {
    python -c "import PyInstaller" 2>&1 | Out-Null
    Write-Host "  PyInstaller: OK" -ForegroundColor Green
} catch {
    Write-Host "  Installing PyInstaller..." -ForegroundColor Yellow
    pip install pyinstaller
}

# ── Step 2: Clean previous builds ─────────────────────────────────────
Write-Host "[2/6] Cleaning previous builds..." -ForegroundColor Yellow

$dirs = @("build", "dist")
foreach ($dir in $dirs) {
    if (Test-Path $dir) {
        Remove-Item -Recurse -Force $dir
        Write-Host "  Removed $dir/" -ForegroundColor Gray
    }
}

# ── Step 3: Build with PyInstaller ────────────────────────────────────
Write-Host "[3/6] Building with PyInstaller..." -ForegroundColor Yellow

python -m PyInstaller BulkEmail.spec --noconfirm --clean 2>&1 | ForEach-Object {
    if ($_ -match "ERROR|WARN") { Write-Host "  $_" -ForegroundColor Red }
}

$exePath = "dist\BulkEmailManager\BulkEmailManager.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "  ERROR: Build failed! BulkEmailManager.exe not found." -ForegroundColor Red
    exit 1
}

$size = (Get-Item $exePath).Length / 1MB
Write-Host "  Built: $exePath ($([math]::Round($size, 1)) MB)" -ForegroundColor Green

# ── Step 4: Create portable ZIP ───────────────────────────────────────
Write-Host "[4/6] Creating portable ZIP..." -ForegroundColor Yellow

$zipPath = "installer\output\BulkEmailManager-Portable.zip"
New-Item -ItemType Directory -Force -Path "installer\output" | Out-Null

if (Test-Path $zipPath) { Remove-Item $zipPath }
Compress-Archive -Path "dist\BulkEmailManager\*" -DestinationPath $zipPath -Force
$zipSize = (Get-Item $zipPath).Length / 1MB
Write-Host "  Created: $zipPath ($([math]::Round($zipSize, 1)) MB)" -ForegroundColor Green

# ── Step 5: Try MSI build with cx_Freeze ──────────────────────────────
if (-not $SkipMSI -and -not $PortableOnly) {
    Write-Host "[5/6] Building MSI installer..." -ForegroundColor Yellow

    try {
        python -c "import cx_Freeze" 2>&1 | Out-Null
        python setup_cx.py bdist_msi 2>&1 | ForEach-Object {
            if ($_ -match "error|Error") { Write-Host "  $_" -ForegroundColor Red }
        }

        $msiFiles = Get-ChildItem "dist\*.msi" -ErrorAction SilentlyContinue
        if ($msiFiles) {
            foreach ($msi in $msiFiles) {
                $msiDest = "installer\output\$($msi.Name)"
                Copy-Item $msi.FullName $msiDest -Force
                $msiSize = (Get-Item $msiDest).Length / 1MB
                Write-Host "  Created: $msiDest ($([math]::Round($msiSize, 1)) MB)" -ForegroundColor Green
            }
        } else {
            Write-Host "  MSI build did not produce output. cx_Freeze may not support this platform." -ForegroundColor DarkYellow
        }
    } catch {
        Write-Host "  MSI build skipped: $($_.Exception.Message)" -ForegroundColor DarkYellow
    }
} else {
    Write-Host "[5/6] Skipping MSI build..." -ForegroundColor Gray
}

# ── Step 6: Check for Inno Setup ──────────────────────────────────────
if (-not $SkipInnoSetup -and -not $PortableOnly) {
    Write-Host "[6/6] Checking Inno Setup..." -ForegroundColor Yellow

    $iscc = $null
    $paths = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { $iscc = $p; break }
    }

    if ($iscc) {
        Write-Host "  Building installer with Inno Setup..." -ForegroundColor Yellow
        & $iscc "installer\setup.iss" 2>&1 | ForEach-Object {
            if ($_ -match "Error") { Write-Host "  $_" -ForegroundColor Red }
        }

        $setupFiles = Get-ChildItem "installer\output\*-Setup.exe" -ErrorAction SilentlyContinue
        if ($setupFiles) {
            foreach ($setup in $setupFiles) {
                $setupSize = (Get-Item $setup.FullName).Length / 1MB
                Write-Host "  Created: $($setup.Name) ($([math]::Round($setupSize, 1)) MB)" -ForegroundColor Green
            }
        }
    } else {
        Write-Host "  Inno Setup not found." -ForegroundColor DarkYellow
        Write-Host "  To create a professional .exe installer:" -ForegroundColor White
        Write-Host "    1. Download: https://jrsoftware.org/isinfo.php" -ForegroundColor White
        Write-Host "    2. Install Inno Setup" -ForegroundColor White
        Write-Host "    3. Open installer\setup.iss and click Build > Compile" -ForegroundColor White
    }
} else {
    Write-Host "[6/6] Skipping Inno Setup..." -ForegroundColor Gray
}

# ── Summary ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Build Complete!" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Output files:" -ForegroundColor White
Write-Host "  -------------"

$outputs = @()
$outputs += "  Portable app:  dist\BulkEmailManager\BulkEmailManager.exe"
$outputs += "  Portable ZIP:  $zipPath"

$msiFiles = Get-ChildItem "installer\output\*.msi" -ErrorAction SilentlyContinue
foreach ($msi in $msiFiles) {
    $outputs += "  MSI installer: installer\output\$($msi.Name)"
}

$setupFiles = Get-ChildItem "installer\output\*-Setup.exe" -ErrorAction SilentlyContinue
foreach ($setup in $setupFiles) {
    $outputs += "  EXE installer: installer\output\$($setup.Name)"
}

foreach ($o in $outputs) { Write-Host $o -ForegroundColor White }

Write-Host ""
Write-Host "  To run the app directly:" -ForegroundColor Gray
Write-Host "    dist\BulkEmailManager\BulkEmailManager.exe" -ForegroundColor Gray
Write-Host ""
