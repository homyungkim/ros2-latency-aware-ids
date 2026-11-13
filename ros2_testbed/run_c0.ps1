# Condition C0 (no IDS, no attack): N runs x 5 min each (manuscript Section V-E).
# Run from this folder in PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\run_c0.ps1 -Runs 10
# Total time is about 6 min per run (40 s start-up + 20 s warm-up + 300 s recording + shutdown),
# i.e. about 1 hour for 10 runs. The PC is kept awake while the script runs.
param([int]$Runs = 10, [int]$Duration = 300, [string]$Cond = "C0")

# keep Windows from sleeping while this script runs (released automatically when it ends)
Add-Type -Namespace Win32 -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
[Win32.Power]::SetThreadExecutionState([uint32]2147483649) | Out-Null   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED

$log = "runs\${Cond}_log_$(Get-Date -Format yyyyMMdd_HHmm).txt"
Start-Transcript -Path $log | Out-Null
$t0 = Get-Date
docker compose down 2>$null | Out-Null
docker compose build
for ($k = 1; $k -le $Runs; $k++) {
  Write-Host "=== $Cond run $k / $Runs  ($(Get-Date -Format HH:mm:ss)) ==="
  docker compose up -d sim teleop
  Start-Sleep -Seconds 40                      # Gazebo + controllers start-up
  docker compose exec teleop /opt/testbed/entrypoint.sh python3 /opt/testbed/recorder.py --cond $Cond --run $k --duration $Duration
  docker compose down
  Start-Sleep -Seconds 10
}

# summary over all runs (valid runs only: RTF >= 0.99)
$rows = Get-ChildItem "runs\${Cond}_run*_summary.json" | ForEach-Object { Get-Content $_ -Raw | ConvertFrom-Json }
$valid = $rows | Where-Object { $_.valid -eq $true }
Write-Host ""
Write-Host "=== $Cond summary: $($valid.Count) valid of $($rows.Count) runs, elapsed $([int]((Get-Date)-$t0).TotalMinutes) min ==="
$rows | Sort-Object run | Format-Table run, mean_ms, sigma_J_ms, p99_ms, misses_per_min, rmse_rad, rtf, valid -AutoSize
foreach ($m in "sigma_J_ms","p99_ms","misses_per_min","rmse_rad","rtf") {
  $v = $valid | ForEach-Object { [double]$_.$m }
  if ($v.Count -gt 0) {
    $mean = ($v | Measure-Object -Average).Average
    $sd = if ($v.Count -gt 1) { [math]::Sqrt((($v | ForEach-Object { ($_ - $mean) * ($_ - $mean) }) | Measure-Object -Sum).Sum / ($v.Count - 1)) } else { 0 }
    Write-Host ("{0,-15} mean {1,10:N4}   sd {2,10:N4}" -f $m, $mean, $sd)
  }
}
Stop-Transcript | Out-Null
[Win32.Power]::SetThreadExecutionState([uint32]2147483648) | Out-Null
Write-Host "Results in .\runs   (log: $log)"
