<#
.SYNOPSIS
    One-click EHG Refresh Token capture for the HYMER Connect integration.

.DESCRIPTION
    Starts a minimal HTTPS proxy that watches for the EHG Remote Access
    Refresh Token when the Hymer Connect app connects.  The token is saved
    to captured_ehg_token.txt and printed on screen.

    Prerequisites:
    - Python 3.10+ with mitmproxy: pip install mitmproxy
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

# Get local IP addresses
$ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.InterfaceAlias -match 'Wi-Fi|WLAN|Ethernet' -and $_.IPAddress -ne '127.0.0.1' } |
    Select-Object -ExpandProperty IPAddress

$ip = $ips | Select-Object -First 1

Write-Host ''
Write-Host '╔══════════════════════════════════════════════════════════════╗' -ForegroundColor Cyan
Write-Host '║   HYMER Connect — EHG Refresh Token Capture                 ║' -ForegroundColor Cyan
Write-Host '╠══════════════════════════════════════════════════════════════╣' -ForegroundColor Cyan
Write-Host '║                                                              ║' -ForegroundColor Cyan
Write-Host "║   Your PC's IP: $($ip.PadRight(42))║" -ForegroundColor Cyan
Write-Host "║   Proxy port:   $($Port.ToString().PadRight(42))║" -ForegroundColor Cyan
Write-Host '║                                                              ║' -ForegroundColor Cyan
Write-Host '║   SETUP (one-time):                                          ║' -ForegroundColor Cyan
Write-Host '║   1. Install patched APK on phone (cert pinning disabled)    ║' -ForegroundColor Cyan
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
