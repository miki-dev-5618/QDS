@echo off
title HEDWIG V2 - Teleportation QDS & Threat Detection System
echo ===============================================================================
echo                HEDWIG V2: TELEPORTATION QDS SECURE COMM SUITE
echo                 Team ATHENA - Smart India Hackathon (SIH 2026)
echo ===============================================================================
echo.
cd /d "%~dp0"

echo [1/4] Checking Python dependencies...
python -m pip install -q -r requirements.txt

echo [2/4] Launching FastAPI server on http://127.0.0.1:8000 ...
start "HEDWIG Server" python -m uvicorn server:app --host 127.0.0.1 --port 8000

echo [3/4] Waiting for server initialization...
timeout /t 4 /nobreak >nul

echo [4/4] Opening terminals (each role logs in separately)...
start http://127.0.0.1:8000/admin
start http://127.0.0.1:8000/bob
start http://127.0.0.1:8000/charlie

echo.
echo ===============================================================================
echo  Alice / Admin console : http://127.0.0.1:8000/admin
echo  Bob verifier          : http://127.0.0.1:8000/bob
echo  Charlie verifier      : http://127.0.0.1:8000/charlie
echo.
echo  Built-in DEMO credentials (localhost only; set HEDWIG_USERS_FILE otherwise):
echo    admin / admin2026   alice / quantum2026   bob / quantum2026   charlie / quantum2026
echo  Create real users with:  python auth.py add-user users.json ^<name^> ^<admin^|bob^|charlie^>
echo ===============================================================================
pause
