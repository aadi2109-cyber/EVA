# Start EVA backend (uvicorn :8000) and frontend (vite :5173) together.
# Ctrl+C stops both. Override with $env:BACKEND_PORT / $env:FRONTEND_PORT.
# If blocked: Set-ExecutionPolicy -Scope Process Bypass
$ErrorActionPreference = 'Stop'

$Root = $PSScriptRoot
$BackendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { '8000' }
$FrontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { '5173' }

$paths = @("$Root\agent\backend", $Root, "$Root\contracts", "$Root\guard")
if ($env:PYTHONPATH) { $paths += $env:PYTHONPATH }
$env:PYTHONPATH = $paths -join ';'
if (-not $env:VITE_API_BASE) { $env:VITE_API_BASE = "http://localhost:$BackendPort" }

# Backend: migrate, then serve (activates .venv if present)
Push-Location "$Root\agent\backend"
if (Test-Path .\.venv\Scripts\Activate.ps1) { . .\.venv\Scripts\Activate.ps1 }
alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'alembic upgrade failed' }
$backend = Start-Process -PassThru -NoNewWindow uvicorn -ArgumentList 'app.main:app', '--reload', '--port', $BackendPort
Pop-Location

# Frontend: install deps on first run
Push-Location "$Root\agent\frontend"
if (-not (Test-Path node_modules)) { npm install; if ($LASTEXITCODE -ne 0) { throw 'npm install failed' } }
$frontend = Start-Process -PassThru -NoNewWindow npm.cmd -ArgumentList 'run', 'dev', '--', '--port', $FrontendPort
Pop-Location

Write-Host "Backend:  http://localhost:$BackendPort  (health: /api/health)"
Write-Host "Frontend: http://localhost:$FrontendPort"

try {
    # Exit as soon as either process dies
    while (-not $backend.HasExited -and -not $frontend.HasExited) { Start-Sleep -Seconds 1 }
}
finally {
    foreach ($p in @($backend, $frontend)) {
        if ($p -and -not $p.HasExited) { taskkill /PID $p.Id /T /F | Out-Null }
    }
}
