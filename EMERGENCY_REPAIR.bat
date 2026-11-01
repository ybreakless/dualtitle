@echo off
chcp 65001 >nul
title DualTitle - 1-Click Repair & Anti-Cheat Folder Cleaner
cls
echo ==============================================================================
echo       DUALTITLE — 1-CLICK REPAIR & ANTI-CHEAT CLEANER FOR ALL GAMES
echo ==============================================================================
echo.
echo Cleaning any synthetic containers, restoring original configurations,
echo and verifying backed-up saves across your installed applications...
echo.

if exist "%~dp0DualTitle_Native.exe" (
    "%~dp0DualTitle_Native.exe" --repair
) else (
    python "%~dp0universal_dualsub.py" --emergency-repair
)

echo.
pause
