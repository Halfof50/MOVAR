# Starts the recommendation server (rag-api: hybrid retrieval + Qwen via Ollama) on <BindHost>:<Port>.
# Usage (from anywhere):  .\run_rag_server.ps1                       -> 0.0.0.0:8002 (reachable from other machines)
#                         .\run_rag_server.ps1 -BindHost 127.0.0.1   -> this PC only
#                         .\run_rag_server.ps1 -Port 8003
# Needs Ollama running with the model pulled:  ollama pull qwen2.5:14b
# Stop with Ctrl+C. Keep this terminal open while the backend uses the server.
# This server has NO authentication. Do not forward its port on the router; the backend reaches it locally.
param([int]$Port = 8002, [string]$BindHost = '0.0.0.0')

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$ragDir = Join-Path $repo 'rag-api'
$python = Join-Path $ragDir '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) { throw "Python of the rag-api venv not found: $python" }

# Ollama must be reachable, otherwise every recommendation fails at the LLM step.
try { Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 | Out-Null }
catch { Write-Warning "Ollama is not responding on 127.0.0.1:11434. Start it (ollama serve) before requesting recommendations." }

Push-Location $ragDir
try {
    Write-Host "Starting recommendation server on http://${BindHost}:$Port (health: /health) ..."
    & $python -m uvicorn app.main:app --host $BindHost --port $Port
}
finally {
    Pop-Location
}
