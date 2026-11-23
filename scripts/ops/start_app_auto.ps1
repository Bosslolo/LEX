$ErrorActionPreference = "Continue"
$ProjectRoot = "C:\Users\csh_server\Desktop\Laurin\LEX"
$logDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$py = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { exit 1 }

function Test-LexListening {
  # Ignore ::1-only listeners (Windows portproxy); require a real IPv4 bind.
  $listeners = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalAddress -ne '::1' }
  if ($listeners) { return $true }
  $proc = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'host\.main' }
  return [bool]$proc
}

if (Test-LexListening) { exit 0 }
Remove-Item (Join-Path $ProjectRoot "data\host.main.lock") -ErrorAction SilentlyContinue
Start-Sleep -Seconds 5
if (Test-LexListening) { exit 0 }
Start-Process -FilePath $py -ArgumentList "-m","host.main","--host","0.0.0.0","--port","8090","--udp-port","5005","--calibrate","0","--ruview-http-port","3000","--ruview-ws-port","3001" -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "school-host.log") -RedirectStandardError (Join-Path $logDir "school-host.err.log")
