@echo off
title Quantum Distributed Network Cluster
cd /d "e:\2026-2\sih 2026"
set PYTHONPATH=e:\2026-2\sih 2026\src;%PYTHONPATH%

echo ============================================================================
echo   LAUNCHING MULTI-TERMINAL DISTRIBUTED QUANTUM NETWORK (PORTS 8000-8004)
echo ============================================================================

REM 1. Launch Central Channel Router (Port 8000)
start "Quantum Channel Router (Port 8000)" cmd /k "cd /d "e:\2026-2\sih 2026" && set PYTHONPATH=e:\2026-2\sih 2026\src && python src\quantum_sim\network\run_node.py router --port 8000"

REM 2. Launch Alice Signer Daemon (Port 8001)
start "Alice Signer Daemon (Port 8001)" cmd /k "cd /d "e:\2026-2\sih 2026" && set PYTHONPATH=e:\2026-2\sih 2026\src && python src\quantum_sim\network\run_node.py alice --port 8001"

REM 3. Launch Bob Verifier Daemon (Port 8002)
start "Bob Verifier Daemon (Port 8002)" cmd /k "cd /d "e:\2026-2\sih 2026" && set PYTHONPATH=e:\2026-2\sih 2026\src && python src\quantum_sim\network\run_node.py bob --port 8002"

REM 4. Launch Charlie Verifier Daemon (Port 8003)
start "Charlie Verifier Daemon (Port 8003)" cmd /k "cd /d "e:\2026-2\sih 2026" && set PYTHONPATH=e:\2026-2\sih 2026\src && python src\quantum_sim\network\run_node.py charlie --port 8003"

REM 5. Launch Threat Detector Daemon (Port 8004)
start "Threat Detection Daemon (Port 8004)" cmd /k "cd /d "e:\2026-2\sih 2026" && set PYTHONPATH=e:\2026-2\sih 2026\src && python src\quantum_sim\network\run_node.py detector --port 8004"

echo.
echo [SUCCESS] All 5 node daemons have been launched in separate terminal windows!
echo.
pause
