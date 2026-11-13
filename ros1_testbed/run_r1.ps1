# ROS 1 (Noetic) testbed, conditions R1_C0 .. R1_C3. Run from this folder in PowerShell, e.g.:
#   powershell -ExecutionPolicy Bypass -File .\run_r1.ps1 -Cond R1_C0 -Runs 5
#   powershell -ExecutionPolicy Bypass -File .\run_r1.ps1 -Cond R1_C1 -Runs 5
#   powershell -ExecutionPolicy Bypass -File .\run_r1.ps1 -Cond R1_C3 -Attack dos -Runs 5
# R1_C0 = baseline, R1_C1 = IDS only, R1_C2 = attack only, R1_C3 = attack + IDS.
# Attack: dos | pub | sub | subflood. The attack starts 60 s into each run so the IDS has a benign period first.
# About 6.5 min per run. Keeps the PC awake while running.
param([string]$Cond = "R1_C0", [string]$Attack = "dos", [int]$Runs = 5, [int]$Duration = 300, [string]$Dataset = "rosids", [int]$AttackDelay = 60)
$useIds = ($Cond -eq "R1_C1" -or $Cond -eq "R1_C3"); $useAtk = ($Cond -eq "R1_C2" -or $Cond -eq "R1_C3")
$tagBase = if ($useAtk) { "${Cond}_${Attack}" } else { $Cond }

Add-Type -Namespace Win32 -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
[Win32.Power]::SetThreadExecutionState([uint32]2147483649) | Out-Null

$log = "runs\${tagBase}_log_$(Get-Date -Format yyyyMMdd_HHmm).txt"
Start-Transcript -Path $log | Out-Null
$t0 = Get-Date
$profiles = @(); if ($useIds) { $profiles += "--profile"; $profiles += "ids" }; if ($useAtk) { $profiles += "--profile"; $profiles += "attack" }
docker compose @profiles down 2>$null | Out-Null
docker compose @profiles build
$span = 20 + $Duration + 10
for ($k = 1; $k -le $Runs; $k++) {
  $tag = "${tagBase}_run$k"
  Write-Host "=== $tag  ($(Get-Date -Format HH:mm:ss)) ==="
  docker compose up -d sim teleop
  Start-Sleep -Seconds 45                      # Gazebo Classic + controllers start-up
  if ($useIds) { docker compose @profiles up -d ids; docker compose @profiles exec -d ids python /app/ids_runtime.py --dataset $Dataset --tag $tag --seconds $span --iface eth0 }
  if ($useAtk) { docker compose @profiles up -d attacker; docker compose @profiles exec -d attacker /opt/testbed/attack.sh $Attack $AttackDelay $span $tag }
  docker compose exec teleop /opt/testbed/entrypoint.sh python3 /opt/testbed/recorder.py --cond $tagBase --run $k --duration $Duration
  Start-Sleep -Seconds 15
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
  Write-Host ""; Write-Host "IDS (detection is meaningful here: TCPROS traffic matches ROSIDS23):"
  Get-ChildItem "runs\${tagBase}_run*_ids_summary.json" | ForEach-Object { Get-Content $_ -Raw | ConvertFrom-Json } |
    Format-Table tag, packets, flows, cpu_percent, infer_p50_us, infer_p99_us, first_alert_s -AutoSize
}
Stop-Transcript | Out-Null
[Win32.Power]::SetThreadExecutionState([uint32]2147483648) | Out-Null
Write-Host "Results in .\runs   (log: $log)"
Write-Host "Detection delay: run  python analyze_detection.py  after R1_C3 runs."
