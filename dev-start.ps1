# Local dev launcher: backend FastAPI (8000) + frontend Astro (4321)
# Usage: powershell -ExecutionPolicy Bypass -File .\dev-start.ps1
# Secrets (admin password, netease cookie) live in server\.env (gitignored), not here.

$root = $PSScriptRoot
$serverDir = Join-Path $root "server"

# On Windows, --user installed packages are not on the import path by default;
# add the user site-packages manually. Adjust for your Python version on another machine.
$env:PYTHONPATH = "C:\Users\9527\AppData\Roaming\Python\Python313\site-packages"
$python = "C:\Program Files\Python313\python.exe"

# Backend: uvicorn app.main:app, working dir server/ (so app imports as a package)
Start-Process -FilePath $python `
  -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
  -WorkingDirectory $serverDir -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $root "backend.log") `
  -RedirectStandardError  (Join-Path $root "backend.err.log")

# Frontend: npm run dev (astro dev)
Start-Process -FilePath "npm.cmd" `
  -ArgumentList "run", "dev" `
  -WorkingDirectory $root -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $root "frontend.log") `
  -RedirectStandardError  (Join-Path $root "frontend.err.log")

function Test-Port($port) {
  [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

# Wait until both ports are ready (up to ~25s)
$deadline = (Get-Date).AddSeconds(25)
while ((Get-Date) -lt $deadline -and (-not (Test-Port 4321) -or -not (Test-Port 8000))) {
  Start-Sleep -Milliseconds 800
}

$backend = if (Test-Port 8000) { "LISTEN" } else { "not ready, check backend.err.log" }
$frontend = if (Test-Port 4321) { "LISTEN" } else { "not ready, check frontend.err.log" }

"Backend  8000: $backend"
"Frontend 4321: $frontend"
""
"Home:     http://localhost:4321/AI-/"
"Music:    http://localhost:4321/AI-/music/"
"Admin:    http://127.0.0.1:8000/admin"
