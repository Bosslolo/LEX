#Requires -Version 5.1
# Soft start: do not kill a healthy floor locator (logon used to always restart).
$ErrorActionPreference = 'Stop'
$Root = 'C:\Users\csh_server\Desktop\Laurin\LEX-floor-locator'
Set-Location $Root

function Test-FloorUp {
    $listening = $false
    foreach ($l in @(Get-NetTCPConnection -LocalPort 5190 -State Listen -ErrorAction SilentlyContinue)) {
        if ($l.LocalAddress -eq '::1') { continue }
        $proc = Get-Process -Id $l.OwningProcess -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -eq 'svchost') { continue }
        $listening = $true
        break
    }
    if (-not $listening) { return $false }
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5190/api/health' -UseBasicParsing -TimeoutSec 3
        return ($r.StatusCode -eq 200 -and $r.Content -match '"ok"\s*:\s*true')
    }
    catch { return $false }
}

if (Test-FloorUp) { exit 0 }

Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'LEX-floor-locator\\dist|floor-locator.*dist\\index' } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $k, $v = $_.Split('=', 2)
    Set-Item -Path "Env:$($k.Trim())" -Value $v.Trim()
}
$env:NODE_ENV = 'production'
New-Item -ItemType Directory -Force -Path logs | Out-Null
Start-Process -FilePath 'C:\Program Files\nodejs\node.exe' -ArgumentList 'dist\index.js' `
    -WorkingDirectory $Root -WindowStyle Hidden `
    -RedirectStandardOutput 'logs\floor.out.log' `
    -RedirectStandardError 'logs\floor.err.log'
