# LEX school host — AMP keeps :8080, so LEX uses :8090
$ErrorActionPreference = "Stop"
Set-Location "C:\Users\csh_server\Desktop\Laurin\LEX"

$py = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Missing .venv — run: python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt" }

Remove-Item "data\host.main.lock" -ErrorAction SilentlyContinue

& $py -m host.main `
  --host 0.0.0.0 `
  --port 8090 `
  --udp-port 5005 `
  --calibrate 0 `
  --ruview-http-port 3000 `
  --ruview-ws-port 3001
