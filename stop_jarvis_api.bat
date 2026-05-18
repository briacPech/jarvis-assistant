@echo off

REM Arrete le serveur Jarvis sur le port 8000

cd /d "%~dp0"

powershell -NoProfile -Command ^

  "$p = Get-NetTCPConnection -LocalPort 8000 -State Listen -EA 0 | Select-Object -First 1; " ^

  "if (-not $p) { Write-Host 'Aucun service sur le port 8000.'; exit 0 }; " ^

  "$pid = $p.OwningProcess; " ^

  "$cmd = (Get-CimInstance Win32_Process -Filter ('ProcessId=' + $pid)).CommandLine; " ^

  "Write-Host 'Arret PID' $pid ':' $cmd; " ^

  "Stop-Process -Id $pid -Force -EA Stop; " ^

  "Write-Host 'Jarvis arrete.'"

pause

