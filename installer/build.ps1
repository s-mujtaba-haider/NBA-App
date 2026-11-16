<#
Builds the Windows installer in one step.

  powershell -ExecutionPolicy Bypass -File installer\build.ps1 -LicenseServer https://your-server.example.com

Steps: web build (npm), clean build virtualenv, writes installer\app.env (settings shipped with the app),
PyInstaller, then Inno Setup (installed with winget if missing).
Output: installer\Output\Baseline_Setup_<version>.exe

-LicenseServer  the owner's hosted Baseline server; installs must activate against it. Leave empty for an
                unlicensed developer build.
-OddsBase/-OddsToken  odds feed for local live picks (optional; without them the app shows the record and
                any picks it can grade, but cannot make new ones).
#>
param(
    [string]$LicenseServer = "",
    [string]$OddsBase = "",
    [string]$OddsToken = "",
    [string]$Version = "1.0.0",
    [switch]$SkipInnoSetup
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "== Web build"
Push-Location web
npm ci
if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
npm run build
if ($LASTEXITCODE -ne 0) { throw "web build failed" }
Pop-Location

$Venv = Join-Path $Root "buildenv"
if (-not (Test-Path "$Venv\Scripts\python.exe")) {
    Write-Host "== Creating build virtualenv"
    python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
}
$Py = "$Venv\Scripts\python.exe"
Write-Host "== Installing build requirements"
& $Py -m pip install --quiet --upgrade pip
& $Py -m pip install --quiet -r requirements.txt pywebview pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

if ($LicenseServer -and -not (Test-Path "desktop\license_public_key.pem")) {
    throw "desktop\license_public_key.pem missing. On the license server run: python -m backend.app.cli public-key --out desktop\license_public_key.pem"
}

Write-Host "== Writing installer\app.env"
$lines = @("LICENSE_SERVER_URL=$LicenseServer", "ODDS_API_BASE=$OddsBase", "ODDS_PROXY_TOKEN=$OddsToken", "AUTO_PICKS=false", "AUTO_RESULTS=true")
Set-Content -Path "installer\app.env" -Value ($lines -join "`r`n") -Encoding utf8

Write-Host "== PyInstaller"
& $Py -m PyInstaller installer\Baseline.spec --noconfirm --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Copy-Item "installer\app.env" "dist\Baseline\.env" -Force

if ($SkipInnoSetup) { Write-Host "Skipped Inno Setup. App folder: dist\Baseline"; exit 0 }

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Write-Host "== Installing Inno Setup (winget)"
    winget install --id JRSoftware.InnoSetup -e --silent --accept-package-agreements --accept-source-agreements
    $iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
              "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { throw "Inno Setup not found after install" }
}
Write-Host "== Inno Setup"
& $iscc "/DAppVersion=$Version" "installer\setup.iss"
if ($LASTEXITCODE -ne 0) { throw "ISCC failed" }
Get-ChildItem "installer\Output\*.exe" | ForEach-Object { Write-Host "Installer: $($_.FullName)" }
