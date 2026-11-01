@echo off
chcp 65001 >nul
title DualTitle — Pre-Game Numbered Terminal Controller
cls

if "%~1"=="--tray" (
    start "" pythonw "%~dp0universal_dualsub.py" --tray
    goto END
)

if "%~1"=="--gui" (
    start "" pythonw "%~dp0universal_dualsub.py" --gui
    goto END
)

if "%~1"=="--restore-save" (
    python "%~dp0universal_dualsub.py" --restore-save
    goto FINISH
)

if not "%~1"=="" (
    echo Drag and Drop detected: %~1
    python "%~dp0universal_dualsub.py" "%~1"
    goto FINISH
)

python "%~dp0universal_dualsub.py"

:FINISH
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Something went wrong. Make sure Python 3.8+ is installed or run EMERGENCY_REPAIR.bat.
    pause
)
:END
