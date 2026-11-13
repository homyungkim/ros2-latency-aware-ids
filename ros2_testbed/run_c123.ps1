# Conditions C1-C3 (manuscript Section V-E). Run from this folder in PowerShell, for example:
#   powershell -ExecutionPolicy Bypass -File .\run_c123.ps1 -Cond C1 -Runs 10
#   powershell -ExecutionPolicy Bypass -File .\run_c123.ps1 -Cond C2 -Attack dos -Runs 5
#   powershell -ExecutionPolicy Bypass -File .\run_c123.ps1 -Cond C3 -Attack dos -Runs 5
# C1 = IDS only, C2 = attack only, C3 = attack + IDS.  Attack: dos | pub | subflood.
# About 6.5 min per run. The PC is kept awake while the script runs.
param([string]$Cond = "C1", [string]$Attack = "dos", [int]$Runs = 10, [int]$Duration = 300, [string]$Dataset = "rosids")
$useIds = ($Cond -eq "C1" -or $Cond -eq "C3"); $useAtk = ($Cond -eq "C2" -or $Cond -eq "C3")
$tagBase = if ($useAtk) { "${Cond}_${Attack}" } else { $Cond }

Add-Type -Namespace Win32 -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
[Win32.Power]::SetThreadExecutionState([uint32]2147483649) | Out-Null

$log = "runs\${tagBase}_log_$(Get-Date -Format yyyyMMdd_HHmm).txt"
Start-Transcript -Path $log | Out-Null
$t0 = Get-Date
$profiles = @(); if ($useIds) { $profiles += "--profile"; $profiles += "ids" }; if ($useAtk) { $profiles += "--profile"; $profiles += "attack" }
docker compose @profiles down 2>$null | Out-Null
docker compose @profiles build
$warm = 20; $span = $warm + $Duration + 10
for ($k = 1; $k -le $Runs; $k++) {
  $tag = "${tagBase}_run$k"
  Write-Host "=== $tag  ($(Get-Date -Format HH:mm:ss)) ==="
  docker compose up -d sim teleop
  Start-Sleep -Seconds 40
  if ($useIds) { docker compose @profiles up -d ids; docker compose @profiles exec -d ids python /app/ids_runtime.py --dataset $Dataset --tag $tag --seconds $span }
  if ($useAtk) { docker compose @profiles up -d attacker; docker compose @profiles exec -d attacker /opt/testbed/attack.sh $Attack $span }
  docker compose exec teleop /opt/testbed/entrypoint.sh python3 /opt/testbed/recorder.py --cond $tagBase --run $k --duration $Duration
  Start-Sleep -Seconds 15                      # let the IDS write its summary
  docker compose @profiles down
  Start-Sleep -Seconds 10
}

$rows = Get-ChildItem "runs\${tagBase}_run*_summary.json" | Where-Object { $_.Name -notlike "*_ids_summary.json" } | ForEach-Object { Get-Content $_ -Raw | ConvertFrom-Json }
$valid = $rows | Where-Object { $_.valid -eq $true }
Write-Host ""
Write-Host "=== $tagBase summary: $($valid.Count) valid of $($rows.Count) runs, elapsed $([int]((Get-Date)-$t0).TotalMinutes) min ==="
$rows | Sort-Object run | Format-Table run, sigma_J_ms, p99_ms, misses_per_min, rmse_rad, rtf, valid -AutoSize
foreach ($m in "sigma_J_ms","p99_ms","misses_per_min","rmse_rad","rtf") {
  $v = $valid | ForEach-Object { [double]$_.$m }
  if ($v.Count -gt 0) {
    $mean = ($v | Measure-Object -Average).Average
    $sd = if ($v.Count -gt 1) { [math]::Sqrt((($v | ForEach-Object { ($_ - $mean) * ($_ - $mean) }) | Measure-Object -Sum).Sum / ($v.Count - 1)) } else { 0 }
    Write-Host ("{0,-15} mean {1,10:N4}   sd {2,10:N4}" -f $m, $mean, $sd)
  }
}
if ($useIds) {
  Write-Host ""; Write-Host "IDS:"
  Get-ChildItem "runs\${tagBase}_run*_ids_summary.json" | ForEach-Object { Get-Content $_ -Raw | ConvertFrom-Json } |
    Format-Table tag, packets, flows, cpu_percent, infer_p50_us, infer_p99_us, first_alert_s -AutoSize
}
Stop-Transcript | Out-Null
[Win32.Power]::SetThreadExecutionState([uint32]2147483648) | Out-Null
Write-Host "Results in .\runs   (log: $log)"
