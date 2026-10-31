# Starts the vision model server (handoff package in "AI MODEL") on <BindHost>:<Port>.
# Usage (from anywhere):  .\run_ai_server.ps1                       -> 0.0.0.0:8001 (reachable from other machines)
#                         .\run_ai_server.ps1 -BindHost 127.0.0.1   -> this PC only
#                         .\run_ai_server.ps1 -Port 8002
# Stop with Ctrl+C. Keep this terminal open while the backend uses the server.
# This server has NO authentication. Do not forward its port on the router; the backend reaches it locally.
param([int]$Port = 8001, [string]$BindHost = '0.0.0.0')

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$modelDir = Join-Path $repo 'AI MODEL'
$python = Join-Path $repo 'ai\.venv\Scripts\python.exe'

if (-not (Test-Path $python)) { throw "Python of the ai venv not found: $python" }
if (-not (Test-Path (Join-Path $modelDir 'api\main.py'))) { throw "AI MODEL folder not found: $modelDir" }

# api/main.py imports scripts.finetune_eupe_v7, but the package ships finetune_eupe_v7_512.py.
# The module is aliased at run time so the files in "AI MODEL" stay untouched.
$code = "import sys, importlib; sys.modules['scripts.finetune_eupe_v7'] = importlib.import_module('scripts.finetune_eupe_v7_512'); import uvicorn; from api.main import app; uvicorn.run(app, host='$BindHost', port=$Port)"

Push-Location $modelDir
try {
    Write-Host "Starting vision model server on http://${BindHost}:$Port (health: /health) ..."
    & $python -c $code
}
finally {
    Pop-Location
}
