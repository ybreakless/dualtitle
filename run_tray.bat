@echo off
chcp 65001 >nul
title DualTitle — Windows System Tray & Dark Control Panel
where pythonw >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    start "" pythonw "%~dp0universal_dualsub.py" --tray
) else (
    python "%~dp0universal_dualsub.py" --tray
)
