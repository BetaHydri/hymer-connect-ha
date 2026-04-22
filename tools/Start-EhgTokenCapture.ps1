<#
.SYNOPSIS
    One-click EHG Refresh Token capture for the HYMER Connect integration.

.DESCRIPTION
    Checks for and installs all prerequisites (Python, mitmproxy, Node.js,
    apk-mitm), then starts a minimal HTTPS proxy that watches for the EHG
    Remote Access Refresh Token when the Hymer Connect app connects.
    The token is saved to captured_ehg_token.txt and printed on screen.

    Prerequisites (auto-installed if missing):
    - Python 3.10+ with mitmproxy
    - Node.js 16+ with apk-mitm
    - Patched Hymer Connect APK (cert pinning disabled) on your phone
    - Phone and PC on the same Wi-Fi network

.AUTHOR Jan Tiedemann
.DATE 2026
#>

[CmdletBinding()]
param(
    [int]$Port = 8080
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$captureScript = Join-Path $scriptDir 'capture_ehg_token.py'

# ── Prerequisite checks ──────────────────────────────────────────────
function Test-Prerequisite {
    param([string]$Command, [string]$Name)
    $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
}

$missingTools = @()

Write-Host ''
Write-Host 'Checking prerequisites...' -ForegroundColor Yellow

# Python
if (Test-Prerequisite 'python' 'Python') {
    $pyVer = & python --version 2>&1
    Write-Host "  [OK] $pyVer" -ForegroundColor Green
} else {
    Write-Host '  [MISSING] Python 3.10+' -ForegroundColor Red
    $missingTools += 'python'
}

# mitmproxy / mitmdump
if (Test-Prerequisite 'mitmdump' 'mitmdump') {
    Write-Host '  [OK] mitmdump (mitmproxy)' -ForegroundColor Green
} else {
    Write-Host '  [MISSING] mitmproxy' -ForegroundColor Red
    $missingTools += 'mitmproxy'
}

# Node.js
if (Test-Prerequisite 'node' 'Node.js') {
    $nodeVer = & node --version 2>&1
    Write-Host "  [OK] Node.js $nodeVer" -ForegroundColor Green
} else {
    Write-Host '  [MISSING] Node.js 16+' -ForegroundColor Red
    $missingTools += 'nodejs'
}

# apk-mitm
if (Test-Prerequisite 'apk-mitm' 'apk-mitm') {
    Write-Host '  [OK] apk-mitm' -ForegroundColor Green
} else {
    Write-Host '  [MISSING] apk-mitm' -ForegroundColor Red
    $missingTools += 'apk-mitm'
}

Write-Host ''

# ── Auto-install missing tools ───────────────────────────────────────
if ($missingTools.Count -gt 0) {
    Write-Host "Installing missing tools: $($missingTools -join ', ')" -ForegroundColor Yellow
    Write-Host ''

    foreach ($tool in $missingTools) {
        switch ($tool) {
            'python' {
                Write-Host '  Installing Python via winget...' -ForegroundColor Cyan
                & winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
                # Refresh PATH
                $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                            [System.Environment]::GetEnvironmentVariable('Path', 'User')
            }
            'mitmproxy' {
                Write-Host '  Installing mitmproxy via pip...' -ForegroundColor Cyan
                & python -m pip install --quiet mitmproxy
            }
            'nodejs' {
                Write-Host '  Installing Node.js via winget...' -ForegroundColor Cyan
                & winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
                # Refresh PATH
                $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                            [System.Environment]::GetEnvironmentVariable('Path', 'User')
            }
            'apk-mitm' {
                Write-Host '  Installing apk-mitm via npm...' -ForegroundColor Cyan
                & npm install -g apk-mitm
            }
        }
    }

    Write-Host ''
    Write-Host 'Prerequisites installed. Verifying...' -ForegroundColor Yellow

    # Re-check critical tools
    if (-not (Test-Prerequisite 'mitmdump' 'mitmdump')) {
        Write-Host '  [ERROR] mitmdump still not found. Please restart your terminal and try again.' -ForegroundColor Red
        Write-Host '          Or install manually: pip install mitmproxy' -ForegroundColor Red
        exit 1
    }
    Write-Host '  [OK] All prerequisites ready' -ForegroundColor Green
    Write-Host ''
}

# ── Get local IP ─────────────────────────────────────────────────────
$ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.InterfaceAlias -match 'Wi-Fi|WLAN|Ethernet' -and $_.IPAddress -ne '127.0.0.1' -and $_.IPAddress -notmatch '^169\.254\.' } |
    Select-Object -ExpandProperty IPAddress

$ip = $ips | Select-Object -First 1
if (-not $ip) { $ip = 'COULD NOT DETECT — check ipconfig' }

# ── Display instructions ─────────────────────────────────────────────
Write-Host '╔══════════════════════════════════════════════════════════════╗' -ForegroundColor Cyan
Write-Host '║   HYMER Connect — EHG Refresh Token Capture                 ║' -ForegroundColor Cyan
Write-Host '╠══════════════════════════════════════════════════════════════╣' -ForegroundColor Cyan
Write-Host '║                                                              ║' -ForegroundColor Cyan
Write-Host "║   Your PC's IP: $($ip.PadRight(42))║" -ForegroundColor Cyan
Write-Host "║   Proxy port:   $($Port.ToString().PadRight(42))║" -ForegroundColor Cyan
Write-Host '║                                                              ║' -ForegroundColor Cyan
Write-Host '║   SETUP (one-time):                                          ║' -ForegroundColor Cyan
Write-Host '║   1. Patch & install the APK (see README for details)        ║' -ForegroundColor Cyan
Write-Host '║   2. On phone: Wi-Fi settings → Proxy → Manual              ║' -ForegroundColor Cyan
Write-Host "║      Host: $($ip.PadRight(20)) Port: $($Port.ToString().PadRight(18))║" -ForegroundColor Cyan
Write-Host '║   3. Open http://mitm.it on phone → install Android cert     ║' -ForegroundColor Cyan
Write-Host '║                                                              ║' -ForegroundColor Cyan
Write-Host '║   CAPTURE:                                                   ║' -ForegroundColor Cyan
Write-Host '║   4. Force-close the Hymer Connect app                       ║' -ForegroundColor Cyan
Write-Host '║   5. Open the patched Hymer Connect app                      ║' -ForegroundColor Cyan
Write-Host '║   6. Wait — the token will appear here automatically         ║' -ForegroundColor Cyan
Write-Host '║                                                              ║' -ForegroundColor Cyan
Write-Host '║   CLEANUP:                                                   ║' -ForegroundColor Cyan
Write-Host '║   7. Press Ctrl+C to stop                                    ║' -ForegroundColor Cyan
Write-Host '║   8. Remove proxy from phone Wi-Fi settings                  ║' -ForegroundColor Cyan
Write-Host '║                                                              ║' -ForegroundColor Cyan
Write-Host '╚══════════════════════════════════════════════════════════════╝' -ForegroundColor Cyan
Write-Host ''
Write-Host 'Starting proxy... (waiting for Hymer Connect app to connect)' -ForegroundColor Yellow
Write-Host ''

# Launch mitmdump with the capture addon
& mitmdump -s $captureScript --listen-port $Port --set flow_detail=0 --quiet
