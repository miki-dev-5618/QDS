@echo off
title HEDWIG V2 - Teleportation QDS & Threat Detection System
echo ===============================================================================
echo                HEDWIG V2: TELEPORTATION QDS SECURE COMM SUITE
echo                 Team ATHENA - Smart India Hackathon (SIH 2026)
echo ===============================================================================
echo.
echo [1/3] Activating environment & launching FastAPI server on http://127.0.0.1:8000...

cd /d "%~dp0"
start "HEDWIG Server" python -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload

echo [2/3] Waiting for server initialization...
timeout /t 3 /nobreak >nul

echo [3/3] Opening multi-party terminals in browser...
start http://127.0.0.1:8000/admin
start http://127.0.0.1:8000/bob
start http://127.0.0.1:8000/charlie

echo.
echo ===============================================================================
echo [SUCCESS] HEDWIG V2 is running!
echo - Alice / Admin Console : http://127.0.0.1:8000/admin
echo - Bob Verifier Terminal  : http://127.0.0.1:8000/bob
echo - Charlie Auditor        : http://127.0.0.1:8000/charlie
echo - Main Login Portal      : http://127.0.0.1:8000/login
echo.
echo Hardcoded Credentials:
echo   - Admin / Alice : admin   / admin2026  (or alice / quantum2026)
echo   - Bob           : bob     / quantum2026
echo   - Charlie       : charlie / quantum2026
echo ===============================================================================
pause
