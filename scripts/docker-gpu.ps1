# Start MinaTalker with NVIDIA GPU (Docker Desktop + WSL2).
# Usage (PowerShell, from repo root):
#   .\scripts\docker-gpu.ps1
#   .\scripts\docker-gpu.ps1 -Build   # rebuild image first

param(
    [switch]$Build,
    [switch]$Logs
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$EnvFile = Join-Path $Root "docker.env"
if (-not (Test-Path $EnvFile)) {
    Write-Error "Missing docker.env - copy from docker.env.example"
}

$ComposeArgs = @(
    "compose",
    "--env-file", $EnvFile,
    "-f", "docker-compose.yml",
    "-f", "docker-compose.gpu.yml"
)

if ($Build) {
    docker @ComposeArgs build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

docker @ComposeArgs up -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Container started. Health (wait for model load):"
Write-Host "  curl -k https://localhost:8010/health"
Write-Host ""
Write-Host "Logs: docker logs -f minatalker"
Write-Host "GPU:  docker exec minatalker nvidia-smi"

if ($Logs) {
    docker logs -f minatalker
}
