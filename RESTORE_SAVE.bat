@echo off
chcp 65001 >nul
title DualTitle - 1-Click Restore Save & Profile Settings
cls
echo ==============================================================================
echo         DUALTITLE — 1-CLICK RESTORE SAVE (RESTORES SAVED PROGRESS)
echo ==============================================================================
echo.
echo Restoring backed-up save files and profile configurations...
echo.

if exist "%~dp0DualTitle_Native.exe" (
    "%~dp0DualTitle_Native.exe" --restore-save
) else (
    python "%~dp0universal_dualsub.py" --restore-save
)

echo.
pause
