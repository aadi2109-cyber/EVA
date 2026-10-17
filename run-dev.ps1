# Start the EVA backend (uvicorn) and frontend (vite) together.
#   .\run-dev.ps1
#   $env:BACKEND_PORT = 9000; $env:FRONTEND_PORT = 3000; .\run-dev.ps1
# Ctrl+C stops both; if either dies the other is stopped too.
# If blocked: Set-ExecutionPolicy -Scope Process Bypass
$ErrorActionPreference = 'Stop'

$Root = $PSScriptRoot
$BackendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { '8000' }
$FrontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { '5173' }
$BackendDir = Join-Path $Root 'agent\backend'
$FrontendDir = Join-Path $Root 'agent\frontend'

function Fail($msg) { Write-Host "error: $msg" -ForegroundColor Red; exit 1 }

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { Fail "'npm' not found on PATH" }

# Prefer a project virtualenv's python, else whatever is on PATH
$Py = $null
foreach ($c in @((Join-Path $BackendDir '.venv\Scripts\python.exe'), (Join-Path $Root '.venv\Scripts\python.exe'))) {
    if (Test-Path $c) { $Py = $c; break }
}
if (-not $Py) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { Fail 'python not found on PATH' }
    $Py = $cmd.Source
}
& $Py -c 'import uvicorn, alembic' 2>$null
if ($LASTEXITCODE -ne 0) { Fail "backend deps missing: cd agent\backend; pip install -e '.[dev]'" }

$paths = @($BackendDir, $Root, (Join-Path $Root 'contracts'), (Join-Path $Root 'guard'))
if ($env:PYTHONPATH) { $paths += $env:PYTHONPATH }
$env:PYTHONPATH = $paths -join ';'
if (-not $env:VITE_API_BASE) { $env:VITE_API_BASE = "http://localhost:$BackendPort" }

$procs = @()
try {
    Write-Host '>> migrating database'
    Push-Location $BackendDir
    try { & $Py -m alembic upgrade head; if ($LASTEXITCODE -ne 0) { Fail 'alembic upgrade failed' } }
    finally { Pop-Location }

    Write-Host ">> starting backend on :$BackendPort"
    $procs += Start-Process -PassThru -NoNewWindow -WorkingDirectory $BackendDir -FilePath $Py `
        -ArgumentList '-m', 'uvicorn', 'app.main:app', '--reload', '--port', $BackendPort

    if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
        Write-Host '>> installing frontend dependencies'
        Push-Location $FrontendDir
        try { npm.cmd install; if ($LASTEXITCODE -ne 0) { Fail 'npm install failed' } }
        finally { Pop-Location }
    }

    Write-Host ">> starting frontend on :$FrontendPort"
    $procs += Start-Process -PassThru -NoNewWindow -WorkingDirectory $FrontendDir -FilePath 'npm.cmd' `
        -ArgumentList 'run', 'dev', '--', '--port', $FrontendPort, '--strictPort'

    Write-Host ''
    Write-Host "Backend:  http://localhost:$BackendPort  (health: /api/health)"
    Write-Host "Frontend: http://localhost:$FrontendPort"
    Write-Host 'Ctrl+C to stop.'

    while (-not ($procs | Where-Object { $_.HasExited })) { Start-Sleep -Seconds 1 }
}
finally {
    foreach ($p in $procs) {
        if ($p -and -not $p.HasExited) { taskkill /PID $p.Id /T /F 2>$null | Out-Null }
    }
}
