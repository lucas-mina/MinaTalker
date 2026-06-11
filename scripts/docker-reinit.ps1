# Stop and recreate MinaTalker GPU container (fresh process, keep volumes).
# Usage:
#   .\scripts\docker-reinit.ps1           # recreate container
#   .\scripts\docker-reinit.ps1 -Rebuild  # rebuild image + recreate
#   .\scripts\docker-reinit.ps1 -Purge    # also remove model cache volume

param(
    [switch]$Rebuild,
    [switch]$Purge,
    [switch]$Logs
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$EnvFile = Join-Path $Root "docker.env"
if (-not (Test-Path $EnvFile)) {
    Write-Error "Missing docker.env — copy from docker.env.example"
}

$ComposeArgs = @(
    "compose",
    "--env-file", $EnvFile,
    "-f", "docker-compose.yml",
    "-f", "docker-compose.gpu.yml"
)

Write-Host "Stopping minatalker..."
docker @ComposeArgs down
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Purge) {
    Write-Host "Removing volume minatalker_minatalker_model_cache..."
    docker volume rm minatalker_minatalker_model_cache 2>$null
}

if ($Rebuild) {
    Write-Host "Rebuilding image..."
    docker @ComposeArgs build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Starting minatalker (GPU)..."
docker @ComposeArgs up -d --force-recreate
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Reinit done. Wait for avatar preload, then:"
Write-Host "  curl -k https://localhost:8010/health"
Write-Host "  docker logs -f minatalker"

if ($Logs) {
    docker logs -f minatalker
}
