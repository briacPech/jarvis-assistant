@echo off

REM Jarvis API — demarrage + verifications (GTX 1650 / edge app)

cd /d "%~dp0"
chcp 65001 >nul

powershell -NoProfile -Command ^

  "$l = Get-NetTCPConnection -LocalPort 8000 -State Listen -EA 0 | Select-Object -First 1; " ^

  "if (-not $l) { exit 0 }; " ^

  "$cmd = (Get-CimInstance Win32_Process -Filter ('ProcessId=' + $l.OwningProcess)).CommandLine; " ^

  "Write-Host ''; " ^

  "Write-Host 'Port 8000 deja utilise (PID' $l.OwningProcess ')'; " ^

  "if ($cmd -match 'main_fast_WINDOWS_ULTRA|app\.main|uvicorn') { " ^

  "  Write-Host 'Jarvis API est DEJA active : http://127.0.0.1:8000/'; " ^

  "  Write-Host 'Test : python scripts\test_chat.py'; " ^

  "  exit 2 " ^

  "} else { Write-Host 'Autre programme :' $cmd; exit 3 }"

if %ERRORLEVEL%==2 (

  echo.

  pause

  exit /b 0

)

if %ERRORLEVEL%==3 (

  echo Fermez l autre programme ou changez JARVIS_PORT dans config.py

  pause

  exit /b 1

)



call venv\Scripts\activate.bat

echo.

echo === Dependances ===

pip install -q -r requirements.txt

pip install -q -r requirements-stt.txt

pip install -q httpx "pydantic>=2.5"



echo.

echo === Preflight ===

python scripts\preflight.py

if %ERRORLEVEL% neq 0 (

  echo.

  echo Corrigez les erreurs ci-dessus puis relancez.

  pause

  exit /b 1

)



set JARVIS_TTS_ENGINE=piper

set JARVIS_PIPER_VOICE=fr_FR-siwis-medium

set JARVIS_USE_APP_PROMPTS=true
set OLLAMA_KEEP_ALIVE=5m
set JARVIS_SINGLE_LOCAL_MODEL=true

echo.
echo VRAM : un seul modele local 3B + keep_alive 5m
python -c "from local_model_policy import evict_non_local_models; evict_non_local_models()"

echo.

echo Liberation modeles lourds si charges...

ollama stop gemma4:e4b >nul 2>nul

ollama stop mistral >nul 2>nul

echo.

echo Demarrage : http://127.0.0.1:8000/

echo Test auto dans une autre console : python scripts\test_chat.py

echo.

python main_fast_WINDOWS_ULTRA.py

pause

