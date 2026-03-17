@echo off
REM MRW Lightning pipeline: NexStorm + FlashGate relay.
REM CRITICAL: SIPC is in the CONSOLE session (session 5). You must run this at the PHYSICAL CONSOLE, not RDP.
REM If you use RDP, the relay cannot access SIPC. Log in at the physical machine.
cd /d C:\MRW\lightning

REM Ensure NexStorm runs in THIS session: stop any existing, then start fresh
taskkill /IM NexStorm.exe /F 2>nul
timeout /t 2 /nobreak >nul
start "" "C:\Astrogenic\NexStorm\NexStorm.exe"
timeout /t 45 /nobreak >nul

:loop
flashgate_relay.exe --output-dir C:\MRW\lightning --retry-sec 600
if errorlevel 1 timeout /t 30 /nobreak >nul
goto loop
