@echo off
title Arreter Jarvis
cd /d "%~dp0"

echo.
echo Arret de Jarvis...
echo.

REM API (port 8000)
call stop_jarvis_api.bat 2>nul
if %ERRORLEVEL% neq 0 (
  echo [.] Pas d API Jarvis sur le port 8000
)

REM Mode vocal
powershell -NoProfile -Command ^
  "$procs = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'jarvis_wake' }; " ^
  "foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -EA 0; Write-Host ('Wake arrete PID ' + $p.ProcessId) }; " ^
  "if (-not $procs) { exit 1 }"
if %ERRORLEVEL%==1 (
  echo [.] Pas de mode vocal Jarvis actif
)

echo.
echo Jarvis arrete.
echo (Ollama n'est pas ferme — fermez-le a la main si besoin.)
echo.
pause
