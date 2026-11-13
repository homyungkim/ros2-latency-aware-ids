# Latency benchmark on the lab PC (PowerShell). Run from this folder:
#   powershell -ExecutionPolicy Bypass -File .\run_latency.ps1 -Dataset edge
param([string]$Dataset = "edge", [int]$N = 100000, [string]$Folder = "")
if ($Folder -eq "") { $Folder = $Dataset }   # e.g. -Folder rosids_v8 to test with earlier results
$Root = "D:\IIoT 원격 제어 NW IDS"
$Res  = Join-Path $Root "06_결과\$Folder"
if (-not (Test-Path (Join-Path $Res "models"))) { Write-Error "models folder not found: $Res\models"; exit 1 }

docker build -t ids-latency .
# 1 CPU core pinned (cpuset 2); 6 GB RAM only so the large baseline RF can load (latency is CPU-bound,
# so the cap does not affect the timings). The 2 GB edge budget is reported separately via each model's size.
docker run --rm --cpus=1 --cpuset-cpus=2 --memory=6g --memory-swap=6g --network none `
  -v "${Res}:/work" ids-latency --models /work/models --dataset $Dataset --n $N --out /work
Write-Host "Result: $Res\latency_$Dataset.csv"
