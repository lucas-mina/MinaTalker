# Deploy MinaTalker (Docker Desktop + NVIDIA GPU)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$EnvFile = "docker.env"
if (-not (Test-Path $EnvFile)) {
    Write-Error "Missing docker.env in repo root"
}

Write-Host "==> Optional: export ONNX on host (faster first container start if backend=tensorrt)"
if ((Test-Path "models\wav2lip.pth") -and -not (Test-Path "models\wav2lip_b4_s256.onnx")) {
    if (Test-Path ".venv\Scripts\python.exe") {
        .venv\Scripts\python.exe scripts/export_wav2lip_onnx.py --checkpoint models/wav2lip.pth --batch-size 4
    } else {
        Write-Host "    Skip ONNX export (no .venv); container entrypoint will export on first start."
    }
}

$env:DOCKER_BUILDKIT = "1"
$ComposeArgs = @(
    "compose",
    "--env-file", $EnvFile,
    "-f", "docker-compose.yml",
    "-f", "docker-compose.gpu.yml"
)

Write-Host "==> docker compose build (first build may take 15-30 min)"
docker @ComposeArgs build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> docker compose up -d --force-recreate"
docker @ComposeArgs up -d --force-recreate
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> Waiting for health..."
Start-Sleep -Seconds 25
curl.exe -k https://localhost:8010/health

Write-Host ""
Write-Host "Verify startup:"
Write-Host "  docker logs minatalker 2>&1 | Select-String 'FP16|GFPGAN|TensorRT|模型加载'"
Write-Host "Verify GPU:"
Write-Host "  docker exec minatalker uv run python -c `"import torch; print('cuda', torch.cuda.is_available())`""
