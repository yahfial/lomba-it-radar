# D:\alfa\Documents\Antigravity\lomba-it-radar\install_24h_autostart.ps1
# Skrip untuk mendaftarkan Lomba IT Radar agar otomatis berjalan di background
# setiap kali laptop menyala / login Windows (tanpa memunculkan jendela hitam CMD).

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$PythonwExe = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
$MainScript = Join-Path $ProjectDir "main.py"
$StartupFolder = [Environment]::GetFolderPath("Startup")
$VbsPath = Join-Path $StartupFolder "LombaITRadar_24h.vbs"

if (-not (Test-Path $PythonwExe)) {
    Write-Error "Virtual environment tidak ditemukan di $PythonwExe"
}

$VbsContent = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "$ProjectDir"
WshShell.Run """$PythonwExe"" ""$MainScript"" --daemon", 0, False
"@

Set-Content -Path $VbsPath -Value $VbsContent -Encoding ASCII
Write-Host "[OK] Auto-start background launcher berhasil dipasang di: $VbsPath" -ForegroundColor Green

# Jalankan langsung di background sekarang jika belum berjalan
$existing = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "main\.py.*--daemon" }
if (-not $existing) {
    Start-Process -FilePath "wscript.exe" -ArgumentList "`"$VbsPath`""
    Write-Host "[OK] Daemon Lomba IT Radar 24/7 sekarang sudah berjalan di background!" -ForegroundColor Cyan
} else {
    Write-Host "[INFO] Daemon Lomba IT Radar sudah aktif di background (PID: $($existing.ProcessId))." -ForegroundColor Yellow
}
