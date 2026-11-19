# D:\alfa\Documents\Antigravity\lomba-it-radar\install_24h_autostart.ps1
# Skrip untuk mendaftarkan dan menjalankan Lomba IT Radar 24/7 via Windows Task Scheduler
# agar berjalan terpisah (independen) di background dan otomatis aktif saat laptop dinyalakan.

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$PythonwExe = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
$MainScript = Join-Path $ProjectDir "main.py"
$TaskName = "LombaITRadar24h"

if (-not (Test-Path $PythonwExe)) {
    Write-Error "Virtual environment tidak ditemukan di $PythonwExe"
}

# Hapus proses lama jika ada
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "main\.py.*--daemon" } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

# Daftarkan Windows Scheduled Task agar berjalan terlepas dari terminal & auto-start saat login
$Action = New-ScheduledTaskAction -Execute $PythonwExe -Argument "`"$MainScript`" --daemon" -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Start-Sleep -Seconds 2
$running = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "main\.py.*--daemon" }
if ($running) {
    Write-Host "[OK] Windows Scheduled Task '$TaskName' aktif & berjalan di background (PID: $($running.ProcessId -join ', '))" -ForegroundColor Green
} else {
    Write-Warning "Task terdaftar, namun proses belum terdeteksi berjalan. Periksa data\radar.log."
}
