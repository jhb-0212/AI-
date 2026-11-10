# Stop local frontend/backend: find listeners by port and kill the processes.
# Usage: powershell -ExecutionPolicy Bypass -File .\dev-stop.ps1

$ports = 4321, 8000
foreach ($port in $ports) {
  $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  foreach ($c in $conns) {
    Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
  }
}

Start-Sleep -Milliseconds 500
$left = @()
foreach ($port in $ports) {
  if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    $left += $port
  }
}

if ($left.Count -eq 0) {
  "Stopped frontend 4321 and backend 8000."
} else {
  "Still listening on: " + ($left -join ", ")
}
