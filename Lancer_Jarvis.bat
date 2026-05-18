@echo off
title Lancer Jarvis
cd /d "%~dp0"

echo.
echo ========================================
echo   JARVIS - Demarrage
echo ========================================
echo.

REM --- Ollama (si installe) ---
where ollama >nul 2>&1
if %ERRORLEVEL%==0 (
  powershell -NoProfile -Command "try { Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
  if errorlevel 1 (
    echo [..] Demarrage Ollama...
    start "Ollama" /min cmd /c "ollama serve"
    timeout /t 3 /nobreak >nul
  ) else (
    echo [OK] Ollama deja actif
  )
)

REM --- API Jarvis (port 8000) — modeles dans .env (ne pas ecraser ici) ---
set JARVIS_TTS_ENGINE=piper
set JARVIS_PIPER_VOICE=fr_FR-siwis-medium

powershell -NoProfile -Command ^
  "$l = Get-NetTCPConnection -LocalPort 8000 -State Listen -EA 0 | Select-Object -First 1; " ^
  "if (-not $l) { exit 0 }; " ^
  "$c = (Get-CimInstance Win32_Process -Filter ('ProcessId=' + $l.OwningProcess)).CommandLine; " ^
  "if ($c -match 'main_fast_WINDOWS_ULTRA') { exit 2 } else { exit 1 }"
if %ERRORLEVEL%==2 (
  echo [OK] API Jarvis deja active : http://127.0.0.1:8000/
) else if %ERRORLEVEL%==1 (
  echo [!] Port 8000 occupe par un autre programme. Fermez-le ou changez JARVIS_PORT.
  pause
  exit /b 1
) else (
  echo [..] Demarrage API Jarvis...
  start "Jarvis API" /min cmd /k "cd /d "%~dp0" && call venv\Scripts\activate.bat && python main_fast_WINDOWS_ULTRA.py"
  echo [..] Attente de l API...
  powershell -NoProfile -Command ^
    "$n = 0; while ($n -lt 45) { try { Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep 1; $n++ } }; exit 1"
  if errorlevel 1 (
    echo [!] API lente — ouvre http://127.0.0.1:8000/ dans quelques secondes
  ) else (
    echo [OK] API prete
  )
)

REM --- Mode vocal "Salut Jarvis" ---
powershell -NoProfile -Command ^
  "$w = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'jarvis_wake' }; if ($w) { exit 2 } else { exit 0 }"
if %ERRORLEVEL%==2 (
  echo [OK] Mode vocal deja actif
) else (
  echo [..] Demarrage mode vocal...
  start "Jarvis Wake" /min cmd /k "cd /d "%~dp0" && call venv\Scripts\activate.bat && python jarvis_wake.py"
)

echo.
echo [..] Ouverture du chat dans le navigateur...
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8000/"

echo.
echo ========================================
echo   Jarvis est pret
echo ========================================
echo   Chat web : http://127.0.0.1:8000/
echo   Voix     : dis "Salut Jarvis" puis ta question
echo   Arreter  : double-clic sur Arreter_Jarvis.bat
echo ========================================
echo.
pause
